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

# Telegram channel posts:
# https://t.me/c/3071373878/334 = Mayna registration / getting started
# https://t.me/c/3071373878/335 = recording a new order and calculating commission
MAYNA_CHANNEL_ID = -1003071373878
REGISTRATION_VIDEO_MESSAGE_ID = 334
ORDER_VIDEO_MESSAGE_ID = 335

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("mayna-assistant")


def normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    return re.sub(r"\s+", " ", text)


def is_greeting(text: str) -> bool:
    text = normalize(text)
    return any(
        phrase in text
        for phrase in (
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
    )


def asks_about_registration(text: str) -> bool:
    text = normalize(text)
    phrases = (
        "كيفاش نسجل",
        "كيف نسجل",
        "كيفيه التسجيل",
        "طريقه التسجيل",
        "كيفاش نبدا",
        "كيف نبدا",
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
        "مسوق جديد",
        "مسوقين جدد",
    )
    return any(phrase in text for phrase in phrases)


def asks_about_order(text: str) -> bool:
    text = normalize(text)
    order_terms = (
        "تسجيل طلبيه",
        "نسجل طلبيه",
        "كيفاش نسجل طلبيه",
        "كيف نسجل طلبيه",
        "طلبية جديده",
        "طلبيه جديده",
        "تسجيل طلب",
        "نسجل طلب",
        "كيفاش ندير طلبيه",
        "كيف ندير طلبيه",
        "كيفاش ندخل طلبيه",
        "كيف ندخل طلبيه",
        "احتساب العموله",
        "حساب العموله",
        "عمولتي",
        "العموله تاعي",
        "نحسب العموله",
        "كيفاش نحسب",
        "كيفيه تسجيل طلبيه",
        "شرح تسجيل طلبيه",
        "شرح الطلبات",
        "كيفاش نخدم الطلبات",
    )
    return any(term in text for term in order_terms)


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


async def send_channel_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message_id: int,
    intro: str,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    await message.reply_text(intro)
    try:
        await context.bot.copy_message(
            chat_id=chat.id,
            from_chat_id=MAYNA_CHANNEL_ID,
            message_id=message_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(
            "Copied channel post %s to chat_id=%s",
            message_id,
            chat.id,
        )
    except TelegramError:
        logger.exception(
            "Could not copy channel post %s. Check bot channel access and message ID.",
            message_id,
        )
        await message.reply_text(
            "ما قدرتش نبعث الفيديو تلقائيا حاليا. تأكد أن البوت عنده وصول للقناة، "
            "وإذا بقى المشكل تواصل مع المشرفين."
        )


async def handle_group_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in ("group", "supergroup"):
        return

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

    # Check order questions first, because they may also mention commissions.
    if asks_about_order(text):
        await send_channel_video(
            update,
            context,
            ORDER_VIDEO_MESSAGE_ID,
            "هذا شرح للمسوقين حول كيفية تسجيل طلبية جديدة واحتساب العمولة:",
        )
        return

    if asks_about_registration(text):
        await send_channel_video(
            update,
            context,
            REGISTRATION_VIDEO_MESSAGE_ID,
            "مرحبا بيك في Mayna. هذا فيديو شرح التسجيل وكيفاش تبدا في التسويق بالعمولة:",
        )


async def handle_channel_posts(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
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
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_posts))

    logger.info("Mayna assistant bot starting.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
