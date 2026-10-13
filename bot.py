import os
import re
import logging
import unicodedata

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

GREETING_REPLY = (
    "وعليكم السلام ورحمة الله وبركاته، "
    "مرحبا بيكم خاوتي في مجموعة استفسارات Mayna. "
    "تفضلو بطرح استفساراتكم، رانا هنا باش نعاونوكم."
)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def is_greeting(text: str) -> bool:
    normalized = normalize_text(text)

    greetings = [
        r"السلام عليكم",
        r"سلام عليكم",
        r"سلام عليك",
        r"سلام",
        r"مرحبا بكم",
        r"مرحبا",
        r"اهلا وسهلا",
        r"اهلا",
        r"اهلين",
    ]

    return any(
        re.search(r"(?<!\w)" + phrase + r"(?!\w)", normalized)
        for phrase in greetings
    )


async def handle_greeting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if user.is_bot:
        return

    if chat.type not in ("group", "supergroup"):
        return

    text = message.text or message.caption or ""

    if not text or not is_greeting(text):
        return

    try:
        await message.reply_text(GREETING_REPLY)
        logger.info("Replied to greeting in group %s", chat.id)
    except Exception:
        logger.exception("Failed to reply to greeting")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN GitHub Actions secret"
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.CAPTION,
            handle_greeting,
        )
    )

    logger.info("MaynaDzBot is starting...")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
