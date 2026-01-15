import aiosqlite
from datetime import datetime

DB_FILE = "forum_data.db"


async def setup_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT UNIQUE,
                server TEXT,
                section TEXT,
                title TEXT,
                url TEXT,
                author_nick TEXT,
                author_static TEXT,
                violator_nick TEXT,
                violator_static TEXT,
                date TEXT,
                description TEXT,
                raw_content TEXT,
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_author_nick ON complaints(author_nick)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_author_static ON complaints(author_static)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_violator_nick ON complaints(violator_nick)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_violator_static ON complaints(violator_static)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server ON complaints(server)")
        await db.commit()
        print("БД готова")


async def save_batch(items):
    async with aiosqlite.connect(DB_FILE) as db:
        try:
            await db.executemany("""
                INSERT OR REPLACE INTO complaints 
                (thread_id, server, section, title, url, author_nick, author_static, 
                 violator_nick, violator_static, date, description, raw_content, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    c.get('thread_id'), c.get('server'), c.get('section'), c.get('title'),
                    c.get('url'), c.get('author_nick'), c.get('author_static'),
                    c.get('violator_nick'), c.get('violator_static'), c.get('date'),
                    c.get('description'), c.get('raw_content'), datetime.now()
                ) for c in items
            ])
            await db.commit()
            return True
        except Exception as e:
            print(f"err: {e}")
            return False


async def find_by_nick(nick, srv=None, lim=20):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        q = f"%{nick}%"
        if srv:
            cur = await db.execute("""
                SELECT * FROM complaints 
                WHERE server = ? AND (author_nick LIKE ? OR violator_nick LIKE ? OR title LIKE ? OR raw_content LIKE ?)
                ORDER BY parsed_at DESC LIMIT ?
            """, (srv, q, q, q, q, lim))
        else:
            cur = await db.execute("""
                SELECT * FROM complaints 
                WHERE author_nick LIKE ? OR violator_nick LIKE ? OR title LIKE ? OR raw_content LIKE ?
                ORDER BY parsed_at DESC LIMIT ?
            """, (q, q, q, q, lim))
        return [dict(r) for r in await cur.fetchall()]


async def find_by_static(sid, srv=None, lim=20):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        if srv:
            cur = await db.execute("""
                SELECT * FROM complaints 
                WHERE server = ? AND (author_static = ? OR violator_static = ? OR raw_content LIKE ?)
                ORDER BY parsed_at DESC LIMIT ?
            """, (srv, sid, sid, f"%{sid}%", lim))
        else:
            cur = await db.execute("""
                SELECT * FROM complaints 
                WHERE author_static = ? OR violator_static = ? OR raw_content LIKE ?
                ORDER BY parsed_at DESC LIMIT ?
            """, (sid, sid, f"%{sid}%", lim))
        return [dict(r) for r in await cur.fetchall()]


async def db_stats():
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT COUNT(*) FROM complaints")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT server, COUNT(*) FROM complaints GROUP BY server")
        by_srv = await cur.fetchall()
        cur = await db.execute("SELECT MAX(parsed_at) FROM complaints")
        last = (await cur.fetchone())[0]
        return {'total': total, 'by_server': dict(by_srv), 'last_update': last}
