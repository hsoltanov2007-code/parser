import asyncio
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, SERVERS
from parser import scraper
from database import setup_db, find_by_nick, find_by_static, db_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ✅ ВПИШИ СЮДА СВОЙ TELEGRAM ID (и других админов, если нужно)
ADMINS = {7741423792}


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


bot = Bot(token=BOT_TOKEN)
mem = MemoryStorage()
dp = Dispatcher(storage=mem)


class States(StatesGroup):
    name_input = State()
    static_input = State()


cache = {}


def main_kb(is_admin_user: bool = False):
    rows = [
        [InlineKeyboardButton(text="🔍 Поиск по имени", callback_data="s_name")],
        [InlineKeyboardButton(text="🔢 Поиск по статику", callback_data="s_static")],
        [InlineKeyboardButton(text="📊 Статистика базы", callback_data="stats")],
    ]

    # ✅ админские кнопки показываем только админам
    if is_admin_user:
        rows.append([InlineKeyboardButton(text="🔄 Обновить базу", callback_data="upd")])

    rows.append([InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def srv_kb(act):
    btns = [[InlineKeyboardButton(text=v['name'], callback_data=f"srv_{act}_{k}")] for k, v in SERVERS.items()]
    btns.append([InlineKeyboardButton(text="🌐 Все серверы", callback_data=f"srv_{act}_all")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В меню", callback_data="back")]])


def upd_kb():
    btns = [[InlineKeyboardButton(text=v['name'], callback_data=f"run_{k}")] for k, v in SERVERS.items()]
    btns.append([InlineKeyboardButton(text="🌐 ВСЕ", callback_data="run_all")])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


@dp.message(Command("start"))
async def on_start(msg: types.Message):
    await msg.answer(
        "🎮 <b>Majestic RP Forum Parser</b>\n\nВыберите:",
        parse_mode="HTML",
        reply_markup=main_kb(is_admin(msg.from_user.id))
    )


@dp.message(Command("reload"))
async def reload_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return await msg.answer("⛔ Нет доступа")

    if scraper.busy:
        return await msg.answer("Парсинг уже идёт")

    await setup_db()
    await msg.answer("✅ Reload выполнен")


@dp.callback_query(F.data == "back")
async def go_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "🎮 <b>Majestic RP Forum Parser</b>\n\nВыберите:",
        parse_mode="HTML",
        reply_markup=main_kb(is_admin(cb.from_user.id))
    )


@dp.callback_query(F.data == "help")
async def on_help(cb: CallbackQuery):
    await cb.message.edit_text(
        "📖 <b>Помощь:</b>\n\n🔍 Поиск по имени\n🔢 Поиск по статику\n📊 Статистика\n"
        "🔄 Обновить базу (только админ)\n"
        "/reload (только админ)",
        parse_mode="HTML",
        reply_markup=back_kb()
    )


@dp.callback_query(F.data == "stats")
async def on_stats(cb: CallbackQuery):
    try:
        st = await db_stats()
        txt = f"📊 <b>Статистика</b>\n\nВсего: <b>{st['total']}</b>\n\n"
        for k, c in st['by_server'].items():
            txt += f"• {SERVERS.get(k, {}).get('name', k)}: {c}\n"
        if st['last_update']:
            txt += f"\nОбновлено: {st['last_update']}"
        await cb.message.edit_text(txt, parse_mode="HTML", reply_markup=back_kb())
    except Exception as e:
        await cb.message.edit_text(f"Ошибка: {e}", parse_mode="HTML", reply_markup=back_kb())


@dp.callback_query(F.data == "upd")
async def on_upd(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ только админам", show_alert=True)
        return

    if scraper.busy:
        await cb.answer("Парсинг уже идёт", show_alert=True)
        return

    await cb.message.edit_text(
        "🔄 <b>Обновление</b>\n\nВыберите сервер:",
        parse_mode="HTML",
        reply_markup=upd_kb()
    )


@dp.callback_query(F.data.startswith("run_"))
async def do_update(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Доступ только админам", show_alert=True)
        return

    if scraper.busy:
        await cb.answer("Парсинг идёт", show_alert=True)
        return

    target = cb.data[4:]
    name = "всех серверов" if target == "all" else SERVERS.get(target, {}).get('name', target)
    status = await cb.message.edit_text(f"🔄 <b>Обновление {name}</b>\n\nПодготовка...", parse_mode="HTML")

    async def prog(cur, tot):
        try:
            pct = int(cur / tot * 100) if tot > 0 else 0
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            await status.edit_text(f"🔄 <b>Обновление {name}</b>\n\n{bar} {pct}%\n{cur}/{tot}", parse_mode="HTML")
        except:
            pass

    try:
        if target == "all":
            cnt = await scraper.scan_all(prog)
        else:
            await setup_db()
            if not scraper.auth:
                await scraper.login()
            scraper.done = 0
            scraper.total = 0
            scraper.busy = True
            await scraper.scan_server(target, prog)
            cnt = scraper.done
            scraper.busy = False

        await status.edit_text(
            f"✅ <b>Готово!</b>\n\nЗагружено: {cnt}",
            parse_mode="HTML",
            reply_markup=back_kb()
        )
    except Exception as e:
        scraper.busy = False
        await status.edit_text(f"Ошибка: {str(e)[:200]}", parse_mode="HTML", reply_markup=back_kb())


@dp.callback_query(F.data == "s_name")
async def on_search_name(cb: CallbackQuery):
    await cb.message.edit_text("🔍 <b>Поиск по имени</b>\n\nСервер:", parse_mode="HTML", reply_markup=srv_kb("name"))


@dp.callback_query(F.data.startswith("srv_name_"))
async def pick_srv_name(cb: CallbackQuery, state: FSMContext):
    key = cb.data[9:]
    cache[cb.from_user.id] = key
    name = "всех серверах" if key == "all" else SERVERS[key]['name']
    await state.set_state(States.name_input)
    await cb.message.edit_text(f"🔍 Поиск на {name}\n\nВведите имя:", parse_mode="HTML", reply_markup=back_kb())


@dp.callback_query(F.data == "s_static")
async def on_search_static(cb: CallbackQuery):
    await cb.message.edit_text("🔢 <b>Поиск по статику</b>\n\nСервер:", parse_mode="HTML", reply_markup=srv_kb("static"))


@dp.callback_query(F.data.startswith("srv_static_"))
async def pick_srv_static(cb: CallbackQuery, state: FSMContext):
    key = cb.data[11:]
    cache[cb.from_user.id] = key
    name = "всех серверах" if key == "all" else SERVERS[key]['name']
    await state.set_state(States.static_input)
    await cb.message.edit_text(f"🔢 Поиск на {name}\n\nВведите статик:", parse_mode="HTML", reply_markup=back_kb())


@dp.message(States.name_input)
async def do_name_search(msg: types.Message, state: FSMContext):
    key = cache.get(msg.from_user.id, 'all')
    srv = None if key == 'all' else key
    try:
        res = await find_by_nick(msg.text.strip(), srv)
        await show_res(msg, res, msg.text.strip(), key)
    except Exception as e:
        await msg.answer(f"Ошибка: {str(e)[:100]}", reply_markup=back_kb())
    await state.clear()


@dp.message(States.static_input)
async def do_static_search(msg: types.Message, state: FSMContext):
    if not msg.text.strip().isdigit():
        await msg.answer("Статик должен быть числом", reply_markup=back_kb())
        return
    key = cache.get(msg.from_user.id, 'all')
    srv = None if key == 'all' else key
    try:
        res = await find_by_static(msg.text.strip(), srv)
        await show_res(msg, res, msg.text.strip(), key)
    except Exception as e:
        await msg.answer(f"Ошибка: {str(e)[:100]}", reply_markup=back_kb())
    await state.clear()


async def show_res(msg: types.Message, data, q, key):
    srv = "Все" if key == "all" else SERVERS.get(key, {}).get('name', key)
    if not data:
        await msg.answer(f"❌ Не найдено\n\nЗапрос: {q}\nСервер: {srv}", parse_mode="HTML", reply_markup=back_kb())
        return

    txt = f"✅ Найдено: {len(data)}\nЗапрос: {q}\n\n"
    for i, r in enumerate(data[:10], 1):
        txt += f"<b>{i}. {(r.get('title') or '-')[:50]}</b>\n"
        if r.get('author_nick'):
            txt += f"   👤 {r['author_nick']}"
            if r.get('author_static'):
                txt += f" ({r['author_static']})"
            txt += "\n"
        if r.get('violator_nick'):
            txt += f"   ⚠️ {r['violator_nick']}"
            if r.get('violator_static'):
                txt += f" ({r['violator_static']})"
            txt += "\n"
        elif r.get('violator_static'):
            txt += f"   ⚠️ ID: {r['violator_static']}\n"
        txt += f"   🔗 <a href=\"{r.get('url', '#')}\">ссылка</a>\n\n"

    if len(data) > 10:
        txt += f"...ещё {len(data) - 10}"
    await msg.answer(txt, parse_mode="HTML", reply_markup=back_kb(), disable_web_page_preview=True)


async def run():
    print("запуск бота...")
    await setup_db()
    try:
        print("бот работает")
        await dp.start_polling(bot)
    finally:
        await scraper.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())

