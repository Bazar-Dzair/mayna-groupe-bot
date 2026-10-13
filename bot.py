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

# All links below refer to posts in the Mayna private channel.
# t.me/c/3071373878/<message_id> maps to chat ID -1003071373878.
MAYNA_CHANNEL_ID = -1003071373878

VIDEOS = {
    "registration": 334,
    "new_order_commission": 335,
    "withdraw_commission": 15,
    "order_management_status": 16,
    "delivery_tracking": 26,
    "marketplace_posting": 72,
    "basket_feature": 77,
    "google_lens_chatgpt_product_research": 84,
    "exchange_warranty_policy": 216,
    "mayna_app_download_images_copy_text": 17,
}

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


def match_tutorial(text: str):
    """Return (tutorial key, intro text) for a recognized question, else None."""
    text = normalize(text)

    # More specific topics are checked before general order registration.
    rules = [
        (
            "delivery_tracking",
            (
                "تتبع الطلب",
                "تتبع الطلبيه",
                "نتبع طلبيتي",
                "وين راهي الطلبيه",
                "وين وصلت الطلبيه",
                "حاله الطلبيه",
                "رقم التتبع",
                "vitrans",
                "dhd express",
                "dhd",
                "فيترانس",
            ),
            "هذا شرح تتبع الطلبيات عبر Vitrans Express وDHD Express:",
        ),
        (
            "withdraw_commission",
            (
                "سحب العموله",
                "نسحب العموله",
                "كيفاش نسحب",
                "كيف نسحب",
                "سحب الارباح",
                "نسحب دراهمي",
                "نسحب فلوسي",
                "كيفاش نخرج العموله",
                "نخرج الارباح",
                "تحويل العموله",
            ),
            "هذا شرح طريقة سحب العمولة من منصة Mayna:",
        ),
        (
            "order_management_status",
            (
                "تعديل طلبيه",
                "نعدل طلبيه",
                "الغاء طلبيه",
                "سبب الالغاء",
                "سبب الغاء",
                "تم تاكيد الطلبيه",
                "في طور التسليم",
                "طور التسليم",
                "توصيل الطلبيه",
                "حاله الطلب",
                "حاله الطلبيه",
                "مراحل الطلبيه",
                "كيفاش نعرف طلبيتي",
            ),
            "هذا شرح تسجيل وتعديل وإلغاء الطلبية، وكيفاش تعرف حالتها حتى التوصيل:",
        ),
        (
            "new_order_commission",
            (
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
                "كيفيه تسجيل طلبيه",
                "شرح تسجيل طلبيه",
            ),
            "هذا شرح تسجيل طلبية جديدة وكيفية احتساب العمولة:",
        ),
        (
            "marketplace_posting",
            (
                "marketplace",
                "ماركت بليس",
                "ماركتبليس",
                "ننشر في فايسبوك",
                "نشر في فايسبوك",
                "كيفاش ننشر",
                "نشر اعلان",
                "نشر منتج",
                "نحط منتج في فيسبوك",
            ),
            "هذا شرح طريقة النشر في Marketplace للمبتدئين:",
        ),
        (
            "basket_feature",
            (
                "خاصيه السله",
                "السله",
                "سلة المشتريات",
                "كيفاش نستعمل السله",
                "السله في ماينا",
            ),
            "هذا شرح خاصية السلة في تطبيق Mayna:",
        ),
        (
            "google_lens_chatgpt_product_research",
            (
                "google lens",
                "غوغل لينس",
                "جوجل لينس",
                "نبحث عن صوره",
                "البحث عن صوره",
                "chatgpt",
                "شات جي بي تي",
                "شات جي بيتي",
                "اسعار المنتجات",
                "سعر المنتج في الجزائر",
                "نبحث على منتج",
                "البحث عن معلومات منتج",
            ),
            "هذا شرح البحث عن صور المنتجات بـ Google Lens والبحث عن معلومات وأسعارها باستعمال ChatGPT:",
        ),
        (
            "exchange_warranty_policy",
            (
                "سياسه الاستبدال",
                "سياسه الضمان",
                "الاستبدال",
                "نبدل المنتج",
                "استرجاع الاموال",
                "ترجيع الدراهم",
                "الضمان",
                "عيب مصنعي",
                "شروط الاستبدال",
            ),
            "هذه سياسة الاستبدال والضمان المعتمدة:",
        ),
        (
            "mayna_app_download_images_copy_text",
            (
                "تحميل صور",
                "نحمل الصور",
                "نسخ النص",
                "ننسخ النص",
                "كيفاش نستعمل تطبيق ماينا",
                "شرح تطبيق ماينا",
                "كيفاش نخدم بالتطبيق",
                "نحمل صور المنتج",
                "ننسخ معلومات المنتج",
            ),
            "هذا شرح تطبيق Mayna، وكيفاش تحمّل صور المنتجات وتنسخ النصوص:",
        ),
        (
            "registration",
            (
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
                "مسوق جديد",
                "مسوقين جدد",
            ),
            "مرحبا بيك في Mayna. هذا فيديو شرح التسجيل وكيفاش تبدا في التسويق بالعمولة:",
        ),
    ]

    for key, phrases, intro in rules:
        if any(phrase in text for phrase in phrases):
            return key, intro
    return None


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
            "هنا تلقى شروحات التسويق بالعمولة، تسجيل الطلبات، العمولات وتتبع الطلبيات. "
            "اكتب سؤالك ونحاولوا نوجهوك للشرح المناسب."
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

    match = match_tutorial(text)
    if not match:
        return

    tutorial_key, intro = match
    message_id = VIDEOS[tutorial_key]

    await message.reply_text(intro)
    try:
        await context.bot.copy_message(
            chat_id=chat.id,
            from_chat_id=MAYNA_CHANNEL_ID,
            message_id=message_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(
            "Tutorial %s (post %s) copied to chat_id=%s",
            tutorial_key,
            message_id,
            chat.id,
        )
    except TelegramError:
        logger.exception(
            "Could not copy tutorial %s (post %s). Check channel access and message ID.",
            tutorial_key,
            message_id,
        )
        await message.reply_text(
            "ما قدرتش نبعث الشرح تلقائيا حاليا. تأكد أن البوت عنده وصول للقناة، "
            "وإذا بقى المشكل تواصل مع المشرفين."
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
