import logging
import os
import re

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# Required GitHub Actions secret:
# TELEGRAM_BOT_TOKEN
#
# The channel and message IDs below come from:
# https://t.me/c/3071373878/334
# The bot must have access to that private channel/post.
MAYNA_CHANNEL_ID = -1003071373878
VIDEO_MESSAGE_ID = 334

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("mayna-assistant")


def normalize(text: str) -> str:
    """Normalize common Arabic variants for simple phrase matching."""
    text = (text or "").strip().lower()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def is_greeting(text: str) -> bool:
    text = normalize(text)
    greetings = (
        "السلام عليكم",
        "سلام عليكم",
        "سلام",
        "salam",
        "assalamu alaikum",
        "bonjour",
        "bonsoir",
        "صباح الخير",
        "مساء الخير",
    )
    return any(phrase in text for phrase in greetings)


def asks_how_to_register(text: str) -> bool:
    text = normalize(text)
    phrases = (
        "كيفاش نسجل",
        "كيف نسجل",
        "كيفيه التسجيل",
        "طريقة التسجيل",
        "كيفاش نبدا",
        "كيف نبدا",
        "كيفاش نبدأ",
        "حاب نسجل",
        "حبيت نسجل",
        "نحب نسجل",
        "راني جديد",
        "انا جديد",
        "انا جديده",
        "حبيت نخدم تسويق بالعموله",
        "نحب نخدم تسويق بالعموله",
        "كيفاش نخدم مع ماينا",
        "كيف نخدم مع ماينا",
        "التسجيل في ماينا",
        "نسجل في ماينا",
        "نفتح حساب",
        "حساب جديد",
        "نبدا مع ماينا",
        "نبدأ مع ماينا",
    )
    return any(phrase in text for phrase in phrases)


async def handle_new_members(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if not message or not message.new_chat_members:
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        await message.reply_text(
            f"مرحبا بيك {member.first_name or ''} في مجموعة Mayna.\n"
            "هنا تلقى المساعدة حول التسويق بالعمولة والطلبات. "
            "اكتب سؤالك بوضوح، وفريق Mayna يساعدك."
        )


async def handle_group_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in ("group", "supergroup"):
        return

    # Ignore messages sent by bots.
    if message.from_user and message.from_user.is_bot:
        return

    text = message.text or message.caption or ""
    if not text:
        return

    if is_greeting(text):
        await message.reply_text(
            "وعليكم السلام ورحمة الله وبركاته. مرحبا بيك في مجموعة Mayna، "
            "كيفاش نقدروا نعاونك؟"
        )
        return

    if not asks_how_to_register(text):
        return

    await message.reply_text(
        "مرحبا بيك في Mayna. هذا فيديو شرح التسجيل وطريقة البداية في التسويق بالعمولة:"
    )

    try:
        await context.bot.copy_message(
            chat_id=chat.id,
            from_chat_id=MAYNA_CHANNEL_ID,
            message_id=VIDEO_MESSAGE_ID,
            reply_to_message_id=message.message_id,
        )
        logger.info(
            "Registration video copied to chat_id=%s for user_id=%s",
            chat.id,
            message.from_user.id if message.from_user else "unknown",
        )
    except TelegramError:
        logger.exception(
            "Failed to copy registration video. Check channel access and message ID."
        )
        await message.reply_text(
            "ما قدرتش نبعث الفيديو تلقائيا حاليا. تقدر تشوف منشور التسجيل من القناة، "
            "وإذا بقى المشكل ابعث رسالة للمشرفين."
        )


async def handle_channel_posts(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Log channel posts for diagnostics; the registration post is configured above."""
    message = update.channel_post
    if message:
        logger.info(
            "Channel post observed: chat_id=%s message_id=%s",
            message.chat_id,
            message.message_id,
        )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN. Add it under GitHub repository Settings "
            "-> Secrets and variables -> Actions -> Repository secrets."
        )

    app = Application.builder().token(token).build()

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members)
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL,
            handle_group_message,
        )
    )
    app.add_handler(
        MessageHandler(filters.ChatType.CHANNEL, handle_channel_posts)
    )

    logger.info("Mayna assistant bot starting.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
