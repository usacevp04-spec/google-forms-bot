import os
import io
import re
import logging

import requests
import uvicorn

from bs4 import BeautifulSoup
from PIL import Image

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set!")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set!")


# =========================================================
# ЛОГИРОВАНИЕ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# HTTP SESSION
# =========================================================

http = requests.Session()

http.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
})


# =========================================================
# TELEGRAM
# =========================================================

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для обработки Google Forms.\n\n"
        "Отправь мне публичную ссылку "
        "на Google Форму."
    )


# =========================================================
# ПРОВЕРКА GOOGLE FORMS
# =========================================================

def is_google_forms_url(url: str) -> bool:

    url = url.strip()

    return bool(
        re.match(
            r"^https?://"
            r"(docs\.google\.com/forms/|forms\.gle/)",
            url,
            re.IGNORECASE
        )
    )


# =========================================================
# ПОЛУЧЕНИЕ HTML
# =========================================================

def get_form_html(url: str) -> str:

    logger.info(
        f"Opening Google Form: {url}"
    )

    response = http.get(
        url,
        timeout=30,
        allow_redirects=True,
    )

    response.raise_for_status()

    logger.info(
        f"Google Form HTTP status: {response.status_code}"
    )

    return response.text


# =========================================================
# ПОИСК ИЗОБРАЖЕНИЙ
# =========================================================

def extract_images(
    html: str,
    base_url: str
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    images = []

    for img in soup.find_all("img"):

        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-image-url")
        )

        if not src:
            continue

        src = src.strip()

        if src.startswith("data:"):
            continue

        # Преобразуем относительный URL
        # в полный.
        from urllib.parse import urljoin

        image_url = urljoin(
            base_url,
            src
        )

        lowered = image_url.lower()

        # Отбрасываем технические картинки.
        ignored = [
            "googlelogo",
            "favicon",
            "captcha",
            "avatar",
            "profile",
        ]

        if any(
            word in lowered
            for word in ignored
        ):
            continue

        if image_url not in images:

            images.append(
                image_url
            )

    return images


# =========================================================
# СКАЧИВАНИЕ КАРТИНКИ В ПАМЯТЬ
# =========================================================

def download_image(
    image_url: str
):

    logger.info(
        f"Downloading image: {image_url}"
    )

    response = http.get(
        image_url,
        timeout=30,
    )

    response.raise_for_status()

    image_bytes = response.content

    image = Image.open(
        io.BytesIO(image_bytes)
    )

    image.load()

    return image_bytes, image


# =========================================================
# OCR
# =========================================================

def recognize_text(
    image_bytes: bytes
) -> str:

    # OCR подключим следующим этапом.
    # Сейчас проверяем сам механизм:
    # Google Form → изображение → RAM.

    return (
        "[OCR пока не подключён]\n"
        "Изображение успешно получено."
    )


# =========================================================
# ОБРАБОТКА ФОРМЫ
# =========================================================

def process_google_form(
    url: str
):

    html = get_form_html(url)

    images = extract_images(
        html,
        url
    )

    logger.info(
        f"Found images: {len(images)}"
    )

    results = []

    for index, image_url in enumerate(
        images,
        start=1
    ):

        logger.info(
            f"Processing image #{index}"
        )

        image_bytes = None
        image = None

        try:

            image_bytes, image = (
                download_image(
                    image_url
                )
            )

            width, height = image.size

            text = recognize_text(
                image_bytes
            )

            results.append({
                "number": index,
                "text": text,
                "width": width,
                "height": height,
            })

        except Exception as e:

            logger.exception(
                f"Image #{index} processing error"
            )

            results.append({
                "number": index,
                "text": (
                    f"❌ Ошибка обработки: {e}"
                ),
                "width": 0,
                "height": 0,
            })

        finally:

            # После обработки освобождаем
            # изображение из памяти.
            image = None
            image_bytes = None

    return results


# =========================================================
# ФОРМАТИРОВАНИЕ
# =========================================================

def format_results(
    results
):

    if not results:

        return (
            "❌ В форме изображения не найдены."
        )

    parts = [
        f"🖼 Найдено изображений: "
        f"{len(results)}\n"
    ]

    for item in results:

        number = item["number"]
        text = item["text"]

        parts.append(
            f"\n{number}. Вопрос:\n"
            f"{text}\n"
        )

    return "".join(parts)


# =========================================================
# ОБРАБОТКА СООБЩЕНИЯ
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text

    if not text:
        return

    text = text.strip()

    if not is_google_forms_url(text):

        await update.message.reply_text(
            "❌ Отправь публичную ссылку "
            "на Google Form.\n\n"
            "Например:\n"
            "https://docs.google.com/forms/..."
        )

        return

    processing_message = (
        await update.message.reply_text(
            "🔎 Открываю Google Form...\n\n"
            "Ищу изображения заданий..."
        )
    )

    try:

        results = process_google_form(
            text
        )

        answer = format_results(
            results
        )

        # Telegram ограничивает размер
        # одного сообщения.
        if len(answer) > 3900:

            answer = (
                answer[:3800]
                + "\n\n"
                "⚠️ Результат слишком большой."
            )

        await processing_message.edit_text(
            answer
        )

    except requests.RequestException as e:

        logger.exception(
            "Google Form request error"
        )

        await processing_message.edit_text(
            "❌ Не удалось открыть Google Form.\n\n"
            f"Ошибка: {e}"
        )

    except Exception as e:

        logger.exception(
            "Unexpected processing error"
        )

        await processing_message.edit_text(
            "❌ Произошла ошибка.\n\n"
            f"Ошибка: {e}"
        )


# =========================================================
# TELEGRAM HANDLERS
# =========================================================

telegram_app.add_handler(
    CommandHandler(
        "start",
        start
    )
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)


# =========================================================
# WEBHOOK
# =========================================================

async def telegram_webhook(
    request: Request
):

    try:

        data = await request.json()

        update = Update.de_json(
            data,
            telegram_app.bot
        )

        await telegram_app.update_queue.put(
            update
        )

        return PlainTextResponse(
            "OK"
        )

    except Exception:

        logger.exception(
            "Telegram webhook error"
        )

        return PlainTextResponse(
            "ERROR",
            status_code=500
        )


# =========================================================
# HEALTH CHECK
# =========================================================

async def health(
    request: Request
):

    return PlainTextResponse(
        "Google Forms Bot is running!"
    )


# =========================================================
# ROUTES
# =========================================================

routes = [
    Route(
        "/",
        endpoint=health,
        methods=["GET", "HEAD"],
    ),

    Route(
        "/telegram",
        endpoint=telegram_webhook,
        methods=["POST"],
    ),
]


# =========================================================
# STARLETTE
# =========================================================

app = Starlette(
    routes=routes
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup():

    logger.info(
        "Starting Telegram bot..."
    )

    await telegram_app.initialize()

    await telegram_app.start()

    logger.info(
        "Telegram application started"
    )

    await telegram_app.bot.set_webhook(
        url=WEBHOOK_URL
    )

    logger.info(
        f"Webhook set: {WEBHOOK_URL}"
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown():

    logger.info(
        "Stopping Telegram bot..."
    )

    if telegram_app.running:

        await telegram_app.stop()

    await telegram_app.shutdown()

    logger.info(
        "Telegram bot stopped"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
    )
