import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re
from config import FORUM_URL, FORUM_COOKIES, SERVERS
from database import save_batch, setup_db

MAX_WORKERS = 10
CHUNK = 50


class Scraper:
    def __init__(self):
        self.pw = None
        self.br = None
        self.ctx = None
        self.sem = asyncio.Semaphore(MAX_WORKERS)
        self.done = 0
        self.total = 0
        self.busy = False
        self.auth = False
    
    async def setup(self):
        if self.br is None:
            self.pw = await async_playwright().start()
            self.br = await self.pw.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            cks = [{'name': k, 'value': v, 'domain': 'forum.majestic-rp.ru', 'path': '/', 
                   'secure': k.startswith('xf_')} for k, v in FORUM_COOKIES.items()]
            self.ctx = await self.br.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080}, locale='ru-RU'
            )
            await self.ctx.add_cookies(cks)
            print("браузер ок")
    
    async def fetch(self, url, tries=3):
        async with self.sem:
            for i in range(tries):
                pg = None
                try:
                    pg = await self.ctx.new_page()
                    await pg.goto(url, wait_until='domcontentloaded', timeout=30000)
                    await pg.wait_for_timeout(500)
                    html = await pg.content()
                    if 'vddosw3data' in html:
                        await pg.wait_for_timeout(6000)
                        html = await pg.content()
                    await pg.close()
                    return html
                except Exception as e:
                    if pg:
                        try: await pg.close()
                        except: pass
                    if i == tries - 1:
                        print(f"err {url[:50]}: {str(e)[:40]}")
                    await asyncio.sleep(1)
            return None
    
    async def login(self):
        await self.setup()
        html = await self.fetch(FORUM_URL)
        if not html:
            print("форум не грузит")
            return False
        if 'data-logged-in="true"' in html:
            print("залогинен")
            self.auth = True
            return True
        print("продолжаем")
        self.auth = True
        return True
    
    async def pages_count(self, sec):
        html = await self.fetch(f"{FORUM_URL}{sec}")
        if not html:
            return 0
        nums = re.findall(r'page-(\d+)', html)
        return max(int(n) for n in nums) if nums else 1
    
    async def load_threads(self, sec, pg=1):
        url = f"{FORUM_URL}{sec}" if pg == 1 else f"{FORUM_URL}{sec.rstrip('/')}/page-{pg}"
        html = await self.fetch(url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        out, seen = [], set()
        
        for a in soup.select('a[data-tp-primary="on"]'):
            href, title = a.get('href', ''), a.get_text(strip=True)
            if not href or not title or '/threads/' not in href or 'шаблон' in title.lower():
                continue
            href = re.sub(r'/unread$', '', href)
            if not href.startswith('http'):
                href = f"{FORUM_URL}{href}"
            if href in seen:
                continue
            seen.add(href)
            m = re.search(r'\.(\d+)', href)
            out.append({'tid': m.group(1) if m else None, 'title': title, 'url': href})
        return out
    
    def extract(self, html, info, srv, sec):
        soup = BeautifulSoup(html, 'html.parser')
        d = {
            'thread_id': info.get('tid'), 'server': srv, 'section': sec,
            'title': info.get('title'), 'url': info.get('url'), 'raw_content': '',
            'author_nick': None, 'author_static': None, 'violator_nick': None,
            'violator_static': None, 'date': None, 'description': None
        }
        
        for f in soup.select('dl.pairs--customField'):
            dt, dd = f.select_one('dt'), f.select_one('dd')
            if not dt or not dd:
                continue
            lbl, val = dt.get_text(strip=True).lower(), dd.get_text(strip=True)
            if not val:
                continue
            if 'ваш игровой никнейм' in lbl or 'ваш ник' in lbl:
                d['author_nick'] = val
            elif 'ваш статический id' in lbl or 'ваш статик' in lbl:
                d['author_static'] = val
            elif 'id нарушителя' in lbl or ('статик' in lbl and 'нарушител' in lbl):
                ids = re.findall(r'\d{4,}', val)
                if ids:
                    d['violator_static'] = ' '.join(ids)
            elif 'ник' in lbl and 'нарушител' in lbl:
                d['violator_nick'] = val
            elif 'дата' in lbl:
                d['date'] = val
            elif 'описание' in lbl or 'ситуаци' in lbl:
                d['description'] = val
        
        txt = ""
        post = soup.select_one('article.message--post .bbWrapper')
        if post:
            txt = post.get_text('\n', strip=True)
        if not txt:
            w = soup.select_one('.bbWrapper')
            if w:
                txt = w.get_text('\n', strip=True)
        d['raw_content'] = txt[:3000] if txt else ""
        
        if not d['author_nick'] and not d['violator_static'] and txt:
            m = re.search(r'(?:Ваш игровой никнейм|Ваш ник(?:нейм)?)[:\s]*([A-Za-z][A-Za-z0-9_]*[\s_][A-Za-z][A-Za-z0-9_]*)', txt, re.I)
            if m:
                d['author_nick'] = m.group(1).strip().replace('_', ' ')
            m = re.search(r'(?:Ваш статический ID|Ваш статик)[:\s#]*(\d{4,})', txt, re.I)
            if m:
                d['author_static'] = m.group(1)
            m = re.search(r'(?:Статический\s*#?ID\s*нарушителя|Статик\s*нарушителя)[:\s#]*(\d{4,})', txt, re.I)
            if m:
                d['violator_static'] = m.group(1)
        
        if not d.get('description') and txt:
            d['description'] = txt[:200].strip()
        return d
    
    async def proc_thread(self, info, srv, sec):
        html = await self.fetch(info['url'])
        return self.extract(html, info, srv, sec) if html else None
    
    async def scan_section(self, srv, sec, cb=None):
        print(f"\n{sec}")
        pgs = await self.pages_count(sec)
        print(f"   стр: {pgs}")
        if pgs == 0:
            return
        
        threads = []
        for start in range(1, pgs + 1, 5):
            end = min(start + 5, pgs + 1)
            tasks = [self.load_threads(sec, p) for p in range(start, end)]
            res = await asyncio.gather(*tasks, return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    threads.extend(r)
            print(f"   загружено: {len(threads)}")
            if cb:
                try: await cb(len(threads), pgs * 20)
                except: pass
        
        seen = set()
        threads = [t for t in threads if t['url'] not in seen and not seen.add(t['url'])]
        self.total += len(threads)
        print(f"   тем: {len(threads)}")
        
        for i in range(0, len(threads), CHUNK):
            batch = threads[i:i + CHUNK]
            res = await asyncio.gather(*[self.proc_thread(t, srv, sec) for t in batch], return_exceptions=True)
            items = [r for r in res if isinstance(r, dict) and r]
            self.done += len(items)
            if items:
                await save_batch(items)
            print(f"   сохранено: {self.done}/{self.total}")
            if cb:
                try: await cb(self.done, self.total)
                except: pass
    
    async def scan_server(self, key, cb=None):
        if key not in SERVERS:
            return False
        srv = SERVERS[key]
        print(f"\n{'='*40}\n{srv['name']}\n{'='*40}")
        for sec in srv['sections']:
            await self.scan_section(key, sec, cb)
        return True
    
    async def scan_all(self, cb=None):
        self.busy = True
        self.done = 0
        self.total = 0
        await self.login()
        await setup_db()
        print("\nстарт парсинга\n")
        for k in SERVERS:
            await self.scan_server(k, cb)
        print(f"\n{'='*40}\nготово: {self.done}\n{'='*40}")
        self.busy = False
        return self.done
    
    async def close(self):
        if self.ctx: await self.ctx.close()
        if self.br: await self.br.close()
        if self.pw: await self.pw.stop()


scraper = Scraper()
