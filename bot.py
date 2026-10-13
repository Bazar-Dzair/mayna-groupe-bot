import logging
import os
import re
import unicodedata

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("mayna-assistant-bot")

WELCOME_TEMPLATE = (
    "مرحبًا {name}، بيك معانا في مجموعة استفسارات Mayna!\n\n"
    "سعداء بانضمامك لينا. هذي المجموعة مخصّصة لمساعدة المسوّقين "
    "والإجابة على استفساراتهم المتعلقة بالمنتجات والطلبات والخدمات.\n\n"
    "تقدر تطرح سؤالك بكل أريحية، وإن شاء الله نعاونوك ونوجّهوك "
    "للمعلومة الصحيحة.\n\n"
    "نتمنّاو لك تجربة موفّقة مع Mayna."
)

GREETING_REPLY = (
    "وعليكم السلام ورحمة الله وبركاته، مرحبا بيكم خاوتي في مجموعة "
    "استفسارات Mayna. تفضلو بطرح استفساراتكم، رانا هنا باش نعاونوكم."
)

GREETING_PATTERNS = [
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


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def is_greeting(text: str) -> bool:
    normalized = normalize_text(text)
    return any(
        re.search(r"(?<!\w)" + phrase + r"(?!\w)", normalized)
        for phrase in GREETING_PATTERNS
    )


async def handle_greeting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user or user.is_bot:
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


async def welcome_new_members(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat or chat.type not in ("group", "supergroup"):
        return
    if not message.new_chat_members:
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        name = member.first_name or "عضونا الجديد"
        safe_name = (
            name.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        try:
            await message.reply_text(WELCOME_TEMPLATE.format(name=safe_name))
            logger.info("Welcomed new member in group %s", chat.id)
        except Exception:
            logger.exception("Failed to welcome new member")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN. Add it under GitHub "
            "Settings > Secrets and variables > Actions."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            welcome_new_members,
        )
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handle_greeting,
        )
    )

    logger.info("Mayna assistant bot starting with greeting/welcome features.")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
