import os
import logging

import uvicorn

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


# =========================================================
# ЛОГИРОВАНИЕ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# TELEGRAM APPLICATION
# =========================================================

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set!")

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

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для обработки Google Forms.\n\n"
        "Отправь мне публичную ссылку на Google Форму."
    )


# =========================================================
# ОБРАБОТКА СООБЩЕНИЙ
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

    if "docs.google.com/forms" in text:

        await update.message.reply_text(
            "🔗 Ссылка на Google Форму получена!\n\n"
            "Пока я только принимаю ссылку.\n"
            "Следующим этапом подключим получение "
            "изображений из формы."
        )

    else:

        await update.message.reply_text(
            "❌ Это не похоже на ссылку Google Forms.\n\n"
            "Отправь публичную ссылку вида:\n"
            "https://docs.google.com/forms/..."
        )


# =========================================================
# TELEGRAM HANDLERS
# =========================================================

telegram_app.add_handler(
    CommandHandler("start", start)
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

async def telegram_webhook(request: Request):

    try:

        data = await request.json()

        update = Update.de_json(
            data,
            telegram_app.bot
        )

        await telegram_app.update_queue.put(update)

        return PlainTextResponse("OK")

    except Exception:

        logger.exception(
            "Error while processing Telegram webhook"
        )

        return PlainTextResponse(
            "ERROR",
            status_code=500
        )


# =========================================================
# HEALTH CHECK
# =========================================================

async def health(request: Request):

    return PlainTextResponse(
        "Google Forms Bot is running!"
    )


# =========================================================
# ROUTES
# =========================================================

routes = [
    Route(
        "/",
        health,
        methods=["GET", "HEAD"]
    ),

    Route(
        "/telegram",
        telegram_webhook,
        methods=["POST"]
    ),
]


# =========================================================
# STARLETTE APP
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

    webhook_url = WEBHOOK_URL

    if not webhook_url:

        logger.error(
            "WEBHOOK_URL is not set!"
        )

        return

    try:

        await telegram_app.bot.set_webhook(
            url=webhook_url
        )

        logger.info(
            f"Webhook set: {webhook_url}"
        )

    except Exception:

        logger.exception(
            "Failed to set Telegram webhook"
        )

        raise


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown():

    logger.info(
        "Stopping Telegram bot..."
    )

    try:

        if telegram_app.running:
            await telegram_app.stop()

    finally:

        await telegram_app.shutdown()

        logger.info(
            "Telegram bot stopped"
        )


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
    )
