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


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

PORT = int(os.getenv("PORT", "10000"))


# =========================
# ЛОГИРОВАНИЕ
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# =========================
# TELEGRAM
# =========================

telegram_app = Application.builder().token(BOT_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для обработки Google Forms.\n\n"
        "Отправь мне публичную ссылку на Google Форму."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if not text:
        return

    if "docs.google.com/forms" in text:

        await update.message.reply_text(
            "🔗 Ссылка получена!\n\n"
            "Пока что я нахожусь на стадии разработки.\n"
            "Следующим шагом научимся получать изображения из формы."
        )

    else:

        await update.message.reply_text(
            "❌ Пожалуйста, отправь публичную ссылку на Google Форму."
        )


telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)


# =========================
# WEBHOOK
# =========================

async def telegram_webhook(request: Request):

    data = await request.json()

    update = Update.de_json(
        data,
        telegram_app.bot
    )

    await telegram_app.update_queue.put(update)

    return PlainTextResponse("OK")


async def health(request: Request):

    return PlainTextResponse(
        "Google Forms Bot is running!"
    )


routes = [
    Route("/", health),
    Route("/telegram", telegram_webhook, methods=["POST"]),
]


app = Starlette(routes=routes)


# =========================
# ЗАПУСК TELEGRAM
# =========================

@app.on_event("startup")
async def startup():

    logger.info("Starting Telegram bot...")

    await telegram_app.initialize()

    await telegram_app.start()


@app.on_event("shutdown")
async def shutdown():

    logger.info("Stopping Telegram bot...")

    await telegram_app.stop()

    await telegram_app.shutdown()


# =========================
# LOCAL RUN
# =========================

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT
    )
