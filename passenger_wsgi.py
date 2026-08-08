# -*- coding: utf-8 -*-
import sys
import os
import json
import asyncio
import logging

# Путь к python внутри virtualenv на хостинге
INTERP = os.path.expanduser("/var/www/u3601412/data/botenv/bin/python")
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from maxapi import Bot, Dispatcher
from maxapi.methods.types.getted_updates import process_update_webhook
from maxapi.types import BotStarted, Command, MessageCreated, CallbackButton, MessageCallback, LinkButton
from maxapi.enums.format import Format
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wsgi_webhook")

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

bot = Bot(TOKEN)
dp = Dispatcher()

CBR_API_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


class ConverterForm(StatesGroup):
    waiting_amount = State()


# ==================== ОБРАБОТЧИКИ БОТА ====================

@dp.bot_started()
async def bot_started(event: BotStarted):
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="Привет! Я тестовый бот 🤖\nНапиши /menu, чтобы посмотреть, что я умею."
    )


@dp.message_created(Command("hello"))
async def hello_handler(event: MessageCreated):
    name = event.from_user.first_name
    await event.message.answer(f"Привет, {name}! 👋")


@dp.message_created(Command("menu"))
async def menu_handler(event: MessageCreated):
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(text="📋 О боте", payload="about"),
        CallbackButton(text="📞 Контакты", payload="contacts")
    )
    builder.row(
        CallbackButton(text="💱 Конвертер валют", payload="converter")
    )
    await event.message.answer(
        text="Выберите пункт меню:",
        attachments=[builder.as_markup()]
    )


async def show_converter_menu(event: MessageCallback):
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(text="🇺🇸 USD → RUB", payload="conv_USD"),
        CallbackButton(text="🇪🇺 EUR → RUB", payload="conv_EUR"),
    )
    builder.row(
        CallbackButton(text="🇨🇳 CNY → RUB", payload="conv_CNY"),
    )
    await event.message.answer(
        text="Выберите валюту, которую хотите конвертировать в рубли:",
        attachments=[builder.as_markup()]
    )


async def get_currency_rate(currency_code: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(CBR_API_URL) as response:
            if response.status != 200:
                return None
            data = await response.json(content_type=None)
            valute = data["Valute"].get(currency_code)
            if not valute:
                return None
            return valute["Value"] / valute["Nominal"]


@dp.message_callback()
async def callback_handler(event: MessageCallback, context: MemoryContext):
    payload = event.callback.payload

    if payload == "about":
        await event.message.answer(
            'Это тестовый бот для MAX, написанный на Python 🐍\n\n'
            'Если нужен бот — <a href="https://max.ru/u/f9LHodD0cOL1sPfDwcYjosUM5U_wiZi5Da4enWOwRHSDHuYUt5jrHv8lhQI">напишите мне</a>!\n\n'
            'А еще я профессионально занимаюсь разработкой сайтов с 2021 года, буду рад помочь!',
            format=Format.HTML
        )

    elif payload == "contacts":
        builder = InlineKeyboardBuilder()
        builder.row(LinkButton(text="💬 Написать в MAX", url="https://max.ru/u/f9LHodD0cOL1sPfDwcYjosUM5U_wiZi5Da4enWOwRHSDHuYUt5jrHv8lhQI"))
        builder.row(LinkButton(text="💻 GitHub", url="https://github.com/yuzz38"))
        builder.row(LinkButton(text="✉️ Telegram", url="https://t.me/skaterchill"))
        await event.message.answer(
            text="Свяжитесь со мной удобным способом:",
            attachments=[builder.as_markup()]
        )

    elif payload == "converter":
        await show_converter_menu(event)

    elif payload.startswith("conv_"):
        currency_code = payload.replace("conv_", "")
        await context.update_data(currency=currency_code)
        await context.set_state(ConverterForm.waiting_amount)
        await event.message.answer(f"Введите сумму в {currency_code}, которую нужно перевести в рубли:")


@dp.message_created(ConverterForm.waiting_amount)
async def amount_handler(event: MessageCreated, context: MemoryContext):
    text = event.message.body.text.strip().replace(",", ".")
    try:
        amount = float(text)
    except ValueError:
        await event.message.answer("Это не похоже на число 🤔 Введите сумму ещё раз:")
        return

    data = await context.get_data()
    currency_code = data.get("currency")
    rate = await get_currency_rate(currency_code)

    if rate is None:
        await event.message.answer("Не удалось получить курс валюты 😔 Попробуйте позже.")
    else:
        result = amount * rate
        await event.message.answer(
            f"💱 {amount} {currency_code} = {result:.2f} RUB\n"
            f"(курс на сегодня: 1 {currency_code} = {rate:.2f} RUB)"
        )

    await context.clear()


# ==================== WSGI-ОБВЯЗКА ====================

_dispatcher_started = False
_loop = None


def get_event_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


async def _ensure_startup():
    global _dispatcher_started
    if not _dispatcher_started:
        await dp.startup(bot)
        _dispatcher_started = True


async def _process_update(event_json):
    await _ensure_startup()
    event_object = await process_update_webhook(event_json=event_json, bot=bot)
    if event_object is None:
        logger.warning("Неизвестный тип обновления: %s", event_json.get("update_type"))
        return False
    await dp.handle(event_object)
    return True


def application(environ, start_response):
    if environ.get("REQUEST_METHOD") != "POST":
        start_response("405 Method Not Allowed", [("Content-Type", "text/plain")])
        return [b"Method Not Allowed"]

    if WEBHOOK_SECRET:
        incoming_secret = environ.get("HTTP_X_MAX_BOT_API_SECRET")
        if incoming_secret != WEBHOOK_SECRET:
            start_response("403 Forbidden", [("Content-Type", "text/plain")])
            return [b"Forbidden"]

    try:
        content_length = int(environ.get("CONTENT_LENGTH", 0) or 0)
    except ValueError:
        content_length = 0

    body = environ["wsgi.input"].read(content_length) if content_length > 0 else b"{}"

    try:
        event_json = json.loads(body.decode("utf-8"))
    except Exception:
        logger.exception("Не удалось распарсить тело запроса")
        start_response("400 Bad Request", [("Content-Type", "text/plain")])
        return [b"Bad Request"]

    loop = get_event_loop()
    try:
        loop.run_until_complete(_process_update(event_json))
    except Exception:
        logger.exception("Ошибка при обработке события")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"OK"]

    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"OK"]