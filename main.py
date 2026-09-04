import os
import re
import io
import logging
from urllib.parse import urljoin

import requests
import uvicorn

from bs4 import BeautifulSoup

from PIL import Image

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse

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
# ПРОВЕРКА ССЫЛКИ
# =========================================================

def is_google_forms_url(url: str) -> bool:

    url = url.strip()

    patterns = [
        r"https?://docs\.google\.com/forms/",
        r"https?://forms\.gle/",
    ]

    return any(
        re.search(pattern, url, re.IGNORECASE)
        for pattern in patterns
    )


# =========================================================
# ПОЛУЧЕНИЕ HTML ФОРМЫ
# =========================================================

def get_form_html(url: str) -> str:

    response = http.get(
        url,
        timeout=30,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


# =========================================================
# ПОИСК ИЗОБРАЖЕНИЙ
# =========================================================

def extract_images(html: str, base_url: str):

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

        full_url = urljoin(
            base_url,
            src
        )

        # Убираем технические/служебные изображения.
        lowered = full_url.lower()

        ignored = [
            "googlelogo",
            "favicon",
            "icon",
            "avatar",
            "profile",
            "captcha",
        ]

        if any(
            item in lowered
            for item in ignored
        ):
            continue

        # Не добавляем дубликаты.
        if full_url not in images:
            images.append(full_url)

    return images


# =========================================================
# СКАЧИВАНИЕ ИЗОБРАЖЕНИЯ В RAM
# =========================================================

def download_image_to_memory(image_url: str):

    response = http.get(
        image_url,
        timeout=30,
    )

    response.raise_for_status()

    image_bytes = response.content

    # Проверяем, что это действительно изображение.
    image = Image.open(
        io.BytesIO(image_bytes)
    )

    image.load()

    return image_bytes, image


# =========================================================
# ПОКА ВРЕМЕННЫЙ OCR
# =========================================================

def recognize_text(image_bytes: bytes) -> str:

    # Здесь пока специально оставляем заглушку.
    #
    # На следующем этапе сюда подключим
    # настоящий OCR.
    #
    # Картинка при этом находится только в RAM.

    return (
        "[OCR пока не подключён]\n"
        "Изображение успешно получено."
    )


# =========================================================
# ОБРАБОТКА GOOGLE FORM
# =========================================================

def process_google_form(url: str):

    logger.info(
        f"Processing Google Form: {url}"
    )

    html = get_form_html(url)

    images = extract_images(
        html,
        url
    )

    logger.info(
        f"Found {len(images)} images"
    )

    results = []

    for index, image_url in enumerate(
        images,
        start=1
    ):

        logger.info(
            f"Processing image #{index}"
        )

        try:

            image_bytes, image = (
                download_image_to_memory(
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

            # Удаляем ссылки на изображение.
            del image
            del image_bytes

        except Exception as e:

            logger.exception(
                f"Failed to process image #{index}"
            )

            results.append({
                "number": index,
                "text": (
                    f"❌ Ошибка обработки: {e}"
                ),
                "width": 0,
                "height": 0,
            })

    return results


# =========================================================
# ФОРМАТИРОВАНИЕ РЕЗУЛЬТАТА
# =========================================================

def format_results(results):

    if not results:

        return (
            "❌ Изображения в форме не найдены."
        )

    parts = []

    parts.append(
        f"🖼 Найдено изображений: {len(results)}\n"
    )

    for item in results:

        number = item["number"]
        text = item["text"]

        parts.append(
            f"{number}. Вопрос:\n"
            f"{text}\n\n"
        )

    return "".join(parts)


# =========================================================
# /START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для обработки Google Forms.\n\n"
        "Отправь мне публичную ссылку "
        "на Google Форму."
    )


# =========================================================
# ОБРАБОТКА ССЫЛКИ
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
            "❌ Не вижу публичную ссылку "
            "на Google Forms.\n\n"
            "Отправь ссылку вида:\n"
            "https://docs.google.com/forms/..."
        )

        return

    processing_message = (
        await update.message.reply_text(
            "🔎 Открываю Google Form...\n\n"
            "Ищу изображения заданий."
        )
    )

    try:

        results = process_google_form(
            text
        )

        answer = format_results(
            results
        )

        # Telegram имеет ограничение длины сообщения.
        if len(answer) > 3900:

            answer = answer[:3800]

            answer += (
                "\n\n⚠️ Результат слишком "
                "большой и был сокращён."
            )

        await processing_message.edit_text(
            answer
        )

    except requests.RequestException as e:

        logger.exception(
            "Network error"
        )

        await processing_message.edit_text(
            "❌ Не удалось открыть Google Form.\n\n"
            f"Ошибка: {e}"
        )

    except Exception as e:

        logger.exception(
            "Form processing error"
        )

        await processing_message.edit_text(
            "❌ Произошла ошибка при обработке формы.\n\n"
            f"Ошибка: {e}"
        )


# =========================================================
# HANDLERS
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
            "Webhook error"
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
# STARLETTE
# =========================================================

app = Starlette(
    routes=[
        (
            "/",
            health
        ),
        (
            "/telegram",
            telegram_webhook
        ),
    ]
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

    if not WEBHOOK_URL:

        raise RuntimeError(
            "WEBHOOK_URL is not set!"
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
