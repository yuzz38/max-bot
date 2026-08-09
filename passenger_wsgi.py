# -*- coding: utf-8 -*-
import sys
import os
import json
import asyncio
import logging
import sqlite3
from collections import defaultdict
import time


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
from maxapi.types.input_media import InputMedia
from datetime import datetime

import aiohttp

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("wsgi_webhook")

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

bot = Bot(TOKEN)
dp = Dispatcher()

CBR_API_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
DB_PATH = os.path.join(os.getcwd(), "bot.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            contact TEXT,
            description TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()  # создаём таблицу один раз при старте процесса
SERVICES = {
    "site": {
        "title": "Разработка сайта",
        "points": [
            "Адаптивная, кроссбраузерная вёрстка сайта, посадка на WordPress",
            "Покупка хостинга, домена, загрузка сайта",
            "Настройка SEO-основ (заголовки, метатеги, скорость загрузки)",
            "Подключение форм обратной связи и аналитики",
            "Обучение работе с сайтом после сдачи проекта",
        ],
    },
    "support": {
        "title": "Техническая поддержка существующего сайта",
        "points": [
            "Исправление багов и вёрстки",
            "Обновление контента и структуры страниц",
            "Мониторинг работоспособности и скорости сайта",
            "Резервное копирование и защита от взлома",
            "Консультации и доработки по запросу",
        ],
    },
    "email": {
        "title": "Рассылка Email писем",
        "points": [
            "Настройка рассылки (Unisender)",
            "Дизайн и вёрстка email-письма",
         
        ],
    },
    "bot": {
        "title": "Создание Чат-бота для вашего бизнеса",
        "points": [
            "Разработка бота под задачи бизнеса (запись, заявки, каталог и т.д.)",
            "Интеграция с внешними сервисами и API",
            "Настройка уведомлений и сбора заявок",
            "Развёртывание на сервере, работа 24/7",
            "Поддержка и доработка после запуска",
        ],
    },
}
PROJECTS = {
    "proj1": {
        "title": "Кому Не Все Равно - Норникель",
        "description": "Верстка и адаптирование программы поддержки изменений компании 'Норникель'",
        "image": "assets/project1.jpg",
        "link": "https://komunevseravno.ru/",
    },
    "proj2": {
        "title": "ИнтекДизайн - студия дизайна интерьера",
        "description": "Редизайн студии дизайна интерьера в Санкт-Петербурге + посадка на Wordpress",
        "image": "assets/project2.jpg",
        "link": "https://design-in.ru/",
    },
    "proj3": {
        "title": "Милый Друг - приют для животных",
        "description": "Верстка и адаптирование приюта для животных + посадка на Wordpress ",
        "image": "assets/project3.jpg",
        "link": "https://m-drug.ru/",
    },
    "proj4": {
        "title": "ПоликаПроф - Российский поставщик упаковочных материалов",
        "description": "Верстка редизайна многостраничного магазина + посадка на MODX",
        "image": "assets/project4.jpg",
        "link": "https://policaprof.ru/",
    },
    "proj5": {
        "title": "CoinDays - онлайн вебинар",
        "description": "Верстка адаптивного лендинга с формой обратной связи",
        "image": "assets/project5.jpg",
        "link": "https://yuzz38.github.io/cryptoLanding/",
    },
}

class ConverterForm(StatesGroup):
    waiting_amount = State()

class LeadForm(StatesGroup):
    waiting_name = State()
    waiting_contact = State()
    waiting_description = State()

class ShortLeadForm(StatesGroup):
    waiting_name = State()
    waiting_contact = State()

def with_back_button(builder: InlineKeyboardBuilder = None) -> InlineKeyboardBuilder:
    if builder is None:
        builder = InlineKeyboardBuilder()
    builder.row(CallbackButton(text="🔙 В главное меню", payload="main_menu"))
    return builder


# ==================== ОБРАБОТЧИКИ БОТА ====================

@dp.bot_started()
async def bot_started(event: BotStarted):
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(text="📋 О боте", payload="about"),
        CallbackButton(text="📞 Контакты", payload="contacts")
    )
    builder.row(
        CallbackButton(text="💱 Конвертер валют", payload="converter")
    )
    builder.row(
        CallbackButton(text="🛠️ Мои услуги", payload="my_services")
    )
    builder.row(
        CallbackButton(text="💼 Мои проекты", payload="my_projects"),
        CallbackButton(text="📄 Резюме", payload="resume")
    )
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="Привет! Меня зовут Лев и я занимаюсь разработкой сайтов с 2021 года \n\nНиже можете ознакомиться со мной, посмотреть мои работы\n\nЕсли нужен персональный сайт о вашем бизнесе/продукте или бот в MAX, смело оставляйте заявку!",
        attachments=[builder.as_markup()]
    )


@dp.message_created(Command("hello"))
async def hello_handler(event: MessageCreated):
    name = event.from_user.first_name
    builder = with_back_button()
    await event.message.answer(
        f"Привет, {name}! 👋",
        attachments=[builder.as_markup()]
    )


@dp.message_created(Command("start"))
async def start_handler(event: MessageCreated):
    name = event.from_user.first_name
    await event.message.answer(f"Привет, {name}! Напиши /menu чтобы узнать кто я и что умею!")


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
    builder.row(
        CallbackButton(text="🛠️ Мои услуги", payload="my_services")
    )
    builder.row(
        CallbackButton(text="💼 Мои проекты", payload="my_projects"),
        CallbackButton(text="📄 Резюме", payload="resume")
    )

    await event.message.answer(
        text="Выберите пункт меню:",
        attachments=[builder.as_markup()]
    )

@dp.message_created(Command("leads"))
async def leads_handler(event: MessageCreated):
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    chat_id, user_id = event.get_ids()

    # доступ только админу
    if str(chat_id) != admin_chat_id:
        return

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT name, contact, description, created_at FROM leads ORDER BY id DESC LIMIT 10"
    ).fetchall()
    conn.close()

    if not rows:
        await event.message.answer("Заявок пока нет.")
        return

    text_lines = ["📋 Последние заявки:\n"]
    for name, contact, description, created_at in rows:
        text_lines.append(
            f"👤 {name} | {contact}\n📝 {description}\n🕐 {created_at}\n"
        )

    await event.message.answer("\n".join(text_lines))

async def show_converter_menu(event: MessageCallback):
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(text="🇺🇸 USD → RUB", payload="conv_USD"),
        CallbackButton(text="🇪🇺 EUR → RUB", payload="conv_EUR"),
    )
    builder.row(
        CallbackButton(text="🇨🇳 CNY → RUB", payload="conv_CNY"),
    )
    builder = with_back_button(builder)
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

    if payload == "main_menu":
        builder = InlineKeyboardBuilder()
        builder.row(
            CallbackButton(text="📋 О боте", payload="about"),
            CallbackButton(text="📞 Контакты", payload="contacts")
        )
        builder.row(
            CallbackButton(text="💱 Конвертер валют", payload="converter")
        )
        builder.row(
            CallbackButton(text="🛠️ Мои услуги", payload="my_services")
        )
        builder.row(
            CallbackButton(text="💼 Мои проекты", payload="my_projects"),
            CallbackButton(text="📄 Резюме", payload="resume")
        )
        await event.message.answer(
            text="Выберите пункт меню:",
            attachments=[builder.as_markup()]
        )

    elif payload == "about":
        builder = with_back_button()
        await event.message.answer(
            'Это тестовый бот для MAX, написанный на Python 🐍\n\n'
            'Если нужен бот — <a href="https://max.ru/u/f9LHodD0cOL1sPfDwcYjosUM5U_wiZi5Da4enWOwRHSDHuYUt5jrHv8lhQI">напишите мне</a>!\n\n'
            'А еще я профессионально занимаюсь разработкой сайтов с 2021 года, буду рад помочь!',
            format=Format.HTML,
            attachments=[builder.as_markup()]
        )

    elif payload == "contacts":
        builder = InlineKeyboardBuilder()
        builder.row(LinkButton(text="💬 Написать в MAX", url="https://max.ru/u/f9LHodD0cOL1sPfDwcYjosUM5U_wiZi5Da4enWOwRHSDHuYUt5jrHv8lhQI"))
        builder.row(LinkButton(text="💻 GitHub", url="https://github.com/yuzz38"))
        builder.row(LinkButton(text="✉️ Telegram", url="https://t.me/skaterchill"))
        builder = with_back_button(builder)
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
        await event.message.answer(
            f"Введите сумму в {currency_code}, которую нужно перевести в рубли:"
        )

    elif payload == "my_projects":
        builder = InlineKeyboardBuilder()
        for key, project in PROJECTS.items():
            builder.row(CallbackButton(text=project["title"], payload=f"show_{key}"))
        builder = with_back_button(builder)
        await event.message.answer(
            text="Вот несколько моих проектов:",
            attachments=[builder.as_markup()]
        )

    elif payload.startswith("show_"):
        key = payload.replace("show_", "")
        project = PROJECTS.get(key)
        if project:
            builder = InlineKeyboardBuilder()
            builder.row(LinkButton(text="🔗 Открыть проект", url=project["link"]))
            builder.row(CallbackButton(text="🔙 К списку проектов", payload="my_projects"))

            image_path = os.path.join(os.getcwd(), project["image"])
            await event.message.answer(
                text=f'{project["title"]}\n\n{project["description"]}',
                attachments=[InputMedia(path=image_path), builder.as_markup()]
            )
    elif payload == "resume":
        resume_path = os.path.join(os.getcwd(), "assets", "resume.pdf")
        builder = with_back_button()
        await event.message.answer(
            text="Вот моё резюме 📄",
            attachments=[InputMedia(path=resume_path), builder.as_markup()]
        )

    elif payload == "my_services":
        builder = InlineKeyboardBuilder()
        builder.row(CallbackButton(text="🌐 Разработка сайта", payload="svc_site"))
        builder.row(CallbackButton(text="🔧 Техподдержка сайта", payload="svc_support"))
        builder.row(CallbackButton(text="✉️ Email-рассылки", payload="svc_email"))
        builder.row(CallbackButton(text="🤖 Чат-бот для бизнеса", payload="svc_bot"))
        builder.row(CallbackButton(text="🤔 Не определился", payload="svc_undecided"))
        builder = with_back_button(builder)
        await event.message.answer(
            text="Выберите, что вас интересует:",
            attachments=[builder.as_markup()]
        )

    elif payload == "svc_undecided":
        await context.set_state(LeadForm.waiting_name)
        await context.update_data(service="Не определился")
        await event.message.answer("Хорошо! Как вас зовут?")

    elif payload.startswith("svc_"):
        key = payload.replace("svc_", "")
        service = SERVICES.get(key)
        if service:
            points_text = "\n".join(f"• {p}" for p in service["points"])
            builder = InlineKeyboardBuilder()
            builder.row(CallbackButton(text="✅ Оставить заявку", payload=f"apply_{key}"))
            builder = with_back_button(builder)
            await event.message.answer(
                text=f'📌 {service["title"]}\n\nЧто входит:\n{points_text}',
                attachments=[builder.as_markup()]
            )

    elif payload.startswith("apply_"):
        key = payload.replace("apply_", "")
        service = SERVICES.get(key)
        if service:
            await context.update_data(service=service["title"])
            await context.set_state(ShortLeadForm.waiting_name)
            await event.message.answer("Отлично! Как вас зовут?")

@dp.message_created(ShortLeadForm.waiting_name)
async def short_lead_name_handler(event: MessageCreated, context: MemoryContext):
    await context.update_data(name=event.message.body.text.strip())
    await context.set_state(ShortLeadForm.waiting_contact)
    await event.message.answer("Укажите номер телефона (или другой удобный контакт):")

@dp.message_created(LeadForm.waiting_name)
async def lead_name_handler(event: MessageCreated, context: MemoryContext):
    await context.update_data(name=event.message.body.text.strip())
    await context.set_state(LeadForm.waiting_contact)
    await event.message.answer("Как с вами связаться? (телефон, почта или ник в MAX, Telegram)")

@dp.message_created(LeadForm.waiting_contact)   
async def lead_contact_handler(event: MessageCreated, context: MemoryContext):
    await context.update_data(contact=event.message.body.text.strip())
    await context.set_state(LeadForm.waiting_description)
    await event.message.answer(
        'Кратко опишите, что нужно (или напишите "перезвоните", если пока не знаете точно):'
    )


@dp.message_created(LeadForm.waiting_description)
async def lead_description_handler(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    name = data.get("name")
    contact = data.get("contact")
    description = event.message.body.text.strip()

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO leads (name, contact, description, created_at) VALUES (?, ?, ?, ?)",
        (name, contact, description, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    notify_text = (
        "Новая заявка!\n\n"
        f"Имя: {name}\n"
        f"Контакт: {contact}\n"
        f"Что нужно: {description}"
    )
    await bot.send_message(chat_id=int(admin_chat_id), text=notify_text)
    builder = with_back_button()
    await event.message.answer(
        "Спасибо! Я свяжусь с вами в течение дня 🙌",
        attachments=[builder.as_markup()]
    )
    await context.clear()

@dp.message_created(ShortLeadForm.waiting_contact)
async def short_lead_contact_handler(event: MessageCreated, context: MemoryContext):
    data = await context.get_data()
    name = data.get("name")
    service = data.get("service")
    contact = event.message.body.text.strip()

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO leads (name, contact, description, created_at) VALUES (?, ?, ?, ?)",
        (name, contact, service, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    notify_text = (
        "Новая заявка!\n\n"
        f"Имя: {name}\n"
        f"Контакт: {contact}\n"
        f"Услуга: {service}"
    )
    await bot.send_message(chat_id=int(admin_chat_id), text=notify_text)
    builder = with_back_button()
    await event.message.answer(
        f'Спасибо! Заявка на «{service}» получена, я свяжусь с вами в течение дня 🙌',
        attachments=[builder.as_markup()]
    )
    await context.clear()


@dp.message_created(ConverterForm.waiting_amount)
async def amount_handler(event: MessageCreated, context: MemoryContext):
    text = event.message.body.text.strip().replace(",", ".")
    builder = with_back_button()

    try:
        amount = float(text)
    except ValueError:
        await event.message.answer(
            "Это не похоже на число 🤔 Введите сумму ещё раз:",
            attachments=[builder.as_markup()]
        )
        return

    data = await context.get_data()
    currency_code = data.get("currency")
    rate = await get_currency_rate(currency_code)

    if rate is None:
        await event.message.answer(
            "Не удалось получить курс валюты 😔 Попробуйте позже.",
            attachments=[builder.as_markup()]
        )
    else:
        result = amount * rate
        await event.message.answer(
            f"💱 {amount} {currency_code} = {result:.2f} RUB\n"
            f"(курс на сегодня: 1 {currency_code} = {rate:.2f} RUB)",
            attachments=[builder.as_markup()]
        )

    await context.clear()


# ==================== WSGI-ОБВЯЗКА ====================

_dispatcher_started = False
_loop = None
# антиспам: user_id -> список временных меток последних действий
_user_activity = defaultdict(list)
_warned_users = set()  # чтобы не спамить предупреждением на каждое лишнее сообщение

RATE_LIMIT_COUNT = 5      # максимум действий
RATE_LIMIT_WINDOW = 10    # за столько секунд        

def is_rate_limited(user_id: int) -> bool:
    
    now = time.time()
    timestamps = _user_activity[user_id]

    # оставляем только те метки, что попадают в окно последних RATE_LIMIT_WINDOW секунд
    timestamps[:] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    timestamps.append(now)

    if len(timestamps) > RATE_LIMIT_COUNT:
        return True

    # если пользователь снова в пределах нормы — снимаем флаг предупреждения
    _warned_users.discard(user_id)
    return False

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

    # антиспам-проверка
    try:
        _, user_id = event_object.get_ids()
    except Exception:
        user_id = None

    if user_id is not None and is_rate_limited(user_id):
        if user_id not in _warned_users:
            _warned_users.add(user_id)
            try:
                await bot.send_message(
                    user_id=user_id,
                    text="Слишком много запросов подряд. Подождите немного и попробуйте снова."
                )
            except Exception:
                logger.exception("Не удалось отправить предупреждение о спаме")
        return False  # игнорируем это событие полностью

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
