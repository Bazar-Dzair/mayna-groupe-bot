import logging
import os
import re
import unicodedata

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # Optional: numeric group ID
MAYNA_CHANNEL_ID = os.getenv("MAYNA_CHANNEL_ID")  # Optional: numeric channel ID
VIDEO_MESSAGE_ID = os.getenv("VIDEO_MESSAGE_ID")  # Optional: channel post ID

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

REGISTRATION_REPLY = (
    "مرحبا بيك في Mayna! باش تبدأ التسويق بالعمولة وتعرض المنتجات "
    "في Marketplace، اتبع فيديو شرح التسجيل للمبتدئين اللي بعثناه لك. "
    "إذا بقات عندك أي خطوة غير واضحة، اكتب سؤالك هنا ونعاونوك."
)

VIDEO_TITLE_HINTS = ("خاص بالمبتدئين", "سجل في mayna", "سجل في مينا",
                      "marketplace", "شرح سريع")
GREETING_PATTERNS = [
    r"السلام عليكم", r"سلام عليكم", r"سلام عليك", r"سلام",
    r"مرحبا بكم", r"مرحبا", r"اهلا وسهلا", r"اهلا", r"اهلين",
]

REGISTRATION_PATTERNS = [
    r"\bانا جديد\b", r"\bراني جديد\b", r"\bجديد\b",
    r"\bكيفاش نسجل\b", r"\bكيف نسجل\b", r"\bطريقة التسجيل\b",
    r"\bحبيت نسجل\b", r"\bحاب نسجل\b", r"\bنحب نسجل\b",
    r"\bحبيت نبدا\b", r"\bحاب نبدا\b", r"\bالتسويق بالعمولة\b",
    r"\bنسجل في التطبيق\b", r"\bنفتح حساب\b", r"\bحساب جديد\b",
    r"\bكيفاش نبدا\b", r"\bكيف نبدا\b", r"\bنخدم مع mayna\b",
]


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text).replace("ى", "ي")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def matches_any(text: str, patterns: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(re.search(pattern, normalized) for pattern in patterns)


def is_greeting(text: str) -> bool:
    return matches_any(text, GREETING_PATTERNS)


def is_registration_question(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    # Avoid treating every occurrence of "جديد" as a registration request.
    if "جديد" in normalized and any(
        word in normalized for word in ("نسجل", "تسجيل", "تطبيق", "خدم", "mayna", "مينا", "حساب")
    ):
        return True
    return matches_any(normalized, REGISTRATION_PATTERNS)


async def handle_greeting(
    update: Update, context: ContextTypes.DEFAULT_TYPE
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
    except Exception:
        logger.exception("Failed to reply to greeting")


async def welcome_new_members(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in ("group", "supergroup"):
        return
    for member in message.new_chat_members or []:
        if member.is_bot:
            continue
        name = member.first_name or "عضونا الجديد"
        safe_name = (
            name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        try:
            await message.reply_text(WELCOME_TEMPLATE.format(name=safe_name))
        except Exception:
            logger.exception("Failed to welcome new member")


def extract_media_file_id(message) -> str | None:
    if message.video:
        return message.video.file_id
    if message.document and (message.document.mime_type or "").startswith("video/"):
        return message.document.file_id
    if message.animation:
        return message.animation.file_id
    return None


async def capture_registration_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Remember the matching channel post while the bot is running."""
    message = update.channel_post
    if not message:
        return

    configured_channel = MAYNA_CHANNEL_ID
    if configured_channel:
        try:
            if str(message.chat.id) != str(int(configured_channel)):
                return
        except ValueError:
            logger.error("MAYNA_CHANNEL_ID must be a numeric Telegram chat ID")
            return

    caption_and_text = " ".join(
        part for part in (message.text or "", message.caption or "") if part
    ).lower()
    if not any(hint in caption_and_text for hint in VIDEO_TITLE_HINTS):
        return

    file_id = extract_media_file_id(message)
    if not file_id:
        logger.info("Matching Mayna post found, but it has no supported video media")
        return

    context.application.bot_data["registration_video"] = {
        "chat_id": message.chat.id,
        "message_id": message.message_id,
        "file_id": file_id,
    }
    logger.info(
        "Captured registration video from channel %s, post %s",
        message.chat.id,
        message.message_id,
    )


async def handle_registration_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or user.is_bot:
        return
    if chat.type not in ("group", "supergroup"):
        return

    text = message.text or message.caption or ""
    if not is_registration_question(text):
        return

    # If configured, restrict responses to the intended group.
    if GROUP_CHAT_ID:
        try:
            if str(chat.id) != str(int(GROUP_CHAT_ID)):
                return
        except ValueError:
            logger.error("GROUP_CHAT_ID must be a numeric Telegram chat ID")
            return

    try:
        await message.reply_text(REGISTRATION_REPLY)
        video = context.application.bot_data.get("registration_video")

        # Optional persistent configuration: numeric channel ID + post ID.
        if not video and MAYNA_CHANNEL_ID and VIDEO_MESSAGE_ID:
            video = {
                "chat_id": int(MAYNA_CHANNEL_ID),
                "message_id": int(VIDEO_MESSAGE_ID),
            }

        if video and video.get("chat_id") and video.get("message_id"):
            await context.bot.copy_message(
                chat_id=chat.id,
                from_chat_id=video["chat_id"],
                message_id=video["message_id"],
                reply_to_message_id=message.message_id,
            )
        elif video and video.get("file_id"):
            await context.bot.send_video(
                chat_id=chat.id,
                video=video["file_id"],
                reply_to_message_id=message.message_id,
            )
        else:
            await message.reply_text(
                "ما قدرتش نحدد فيديو شرح التسجيل تلقائيًا بعد. "
                "المشرف يقدر يعاود ينشر فيديو التسجيل في القناة بعد تشغيل البوت، "
                "مع الاحتفاظ بعنوانه، باش يتعرّف عليه البوت."
            )
            logger.warning("Registration question received but video is not cached")
    except Exception:
        logger.exception("Failed to process registration question")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN. Add it under GitHub "
            "Settings > Secrets and variables > Actions."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handle_registration_question,
        )
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            handle_greeting,
        )
    )
    # Channel posts are a separate update type; the bot must be an admin in the channel.
    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & (filters.VIDEO | filters.Document.VIDEO | filters.ANIMATION),
            capture_registration_video,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL & (filters.TEXT | filters.CAPTION),
            capture_registration_video,
        )
    )

    logger.info("Mayna assistant bot starting.")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
