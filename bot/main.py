"""Telegram-бот: по кнопке выдаёт владельцу настройки WireGuard (.conf и QR)."""
import asyncio
import io
import logging
import os

import qrcode
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from wg import Devices

TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
ENDPOINT = os.environ["WG_ENDPOINT"]  # ip:порт сервера
MAX_DEVICES = int(os.environ.get("MAX_DEVICES", "5"))
DB_PATH = os.environ.get("DB_PATH", "data/devices.json")

devices = Devices(DB_PATH, ENDPOINT, MAX_DEVICES)
owner = Router()
owner.message.filter(F.from_user.id == OWNER_ID)
owner.callback_query.filter(F.from_user.id == OWNER_ID)
stranger = Router()  # всем остальным — отказ

MENU = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔑 Получить VPN", callback_data="new")],
    [InlineKeyboardButton(text="📋 Мои устройства", callback_data="list")],
])


@owner.message(CommandStart())
async def start(m: Message):
    await m.answer("Привет! Нажми кнопку — пришлю настройки VPN для нового устройства.", reply_markup=MENU)


@owner.callback_query(F.data == "new")
async def new(c: CallbackQuery):
    await c.answer("Готовлю…")
    n = len(devices.list()) + 1
    try:
        name, ip, conf = await asyncio.to_thread(devices.add, f"device{n}-{c.from_user.id % 1000}")
    except ValueError as e:
        await c.message.answer(str(e), reply_markup=MENU)
        return
    img = qrcode.make(conf)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    await c.message.answer_photo(BufferedInputFile(buf.getvalue(), "qr.png"), caption=f"QR-код для приложения WireGuard ({name}, {ip})")
    await c.message.answer_document(BufferedInputFile(conf.encode(), f"{name}.conf"), caption="Или файл настроек.", reply_markup=MENU)


@owner.callback_query(F.data == "list")
async def list_(c: CallbackQuery):
    await c.answer()
    items = devices.list()
    if not items:
        await c.message.answer("Устройств пока нет.", reply_markup=MENU)
        return
    kb = [[InlineKeyboardButton(text=f"❌ {d['name']} ({d['ip']})", callback_data=f"del:{d['pub'][:40]}")] for d in items]
    await c.message.answer("Нажми на устройство, чтобы отключить его:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@owner.callback_query(F.data.startswith("del:"))
async def delete(c: CallbackQuery):
    prefix = c.data[4:]
    match = [d for d in devices.list() if d["pub"].startswith(prefix)]
    if match and await asyncio.to_thread(devices.remove, match[0]["pub"]):
        await c.answer("Отключено")
        await c.message.answer(f"Устройство {match[0]['name']} отключено.", reply_markup=MENU)
    else:
        await c.answer("Не нашёл такое устройство", show_alert=True)


@stranger.message()
async def deny_msg(m: Message):
    await m.answer("Доступ закрыт.")


@stranger.callback_query()
async def deny_cb(c: CallbackQuery):
    await c.answer("Доступ закрыт.", show_alert=True)


async def main():
    logging.basicConfig(level=logging.INFO)
    dp = Dispatcher()
    dp.include_routers(owner, stranger)
    await dp.start_polling(Bot(TOKEN))


if __name__ == "__main__":
    asyncio.run(main())
