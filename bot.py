import json
import logging
import os
import re
import urllib.error
import urllib.request

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
    "delivery_prices_58_wilayas": 399,
    "customer_service_numbers": 396,
    "order_confirmation_times": 398,
    "delivery_companies": 400,
    "municipality_home_delivery": 408,
    "product_color_size_notes": 409,
    "exchange_warranty_policy_original": 412,
    "commission_payment_days": 425,
    "delivery_duration_58_wilayas": 436,
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
)
logger = logging.getLogger("mayna-assistant")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

INTRO_TEXTS = {
    "registration": "مرحبا بيك في Mayna. هذا شرح التسجيل وكيفاش تبدا:",
    "new_order_commission": "هذا شرح تسجيل الطلبية واحتساب العمولة:",
    "withdraw_commission": "هذا شرح طريقة سحب العمولة:",
    "order_management_status": "هذا شرح إدارة الطلبات وتعديلها أو إلغائها ومتابعة حالتها:",
    "delivery_tracking": "هذا شرح تتبع الطلبيات:",
    "marketplace_posting": "هذا شرح النشر في Marketplace:",
    "basket_feature": "هذا شرح خاصية السلة في تطبيق Mayna:",
    "google_lens_chatgpt_product_research": "هذا شرح البحث عن المنتجات باستعمال Google Lens وChatGPT:",
    "exchange_warranty_policy": "هذا شرح سياسة الاستبدال والضمان:",
    "mayna_app_download_images_copy_text": "هذا شرح استعمال تطبيق Mayna وتحميل الصور ونسخ المعلومات:",
    "delivery_prices_58_wilayas": "هذا منشور أسعار التوصيل للولايات الـ58:",
    "customer_service_numbers": "هذه أرقام خدمة العملاء:",
    "order_confirmation_times": "هذا شرح أوقات تأكيد الطلبات:",
    "delivery_companies": "هذه معلومات شركات التوصيل:",
    "municipality_home_delivery": "هذا شرح التوصيل للبلديات والتوصيل إلى المنزل:",
    "product_color_size_notes": "هذا شرح ملاحظات الألوان والمقاسات ومعلومات المنتج:",
    "exchange_warranty_policy_original": "هذا المنشور الإضافي الخاص بسياسة الاستبدال والضمان:",
    "commission_payment_days": "هذا شرح أيام دفع العمولات:",
    "delivery_duration_58_wilayas": "هذا شرح مدة التوصيل للولايات الـ58:",
}

CHANNEL_FOOTER = (
    "\n\nلمعلومات وشروحات أخرى، ادخل لقناة Mayna للتسويق:\n"
    "https://t.me/+wyKej2q0oK0zYjI0"
)


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
            "delivery_prices_58_wilayas",
            (
                "اسعار توصيل", "اسعار التوصيل", "سعر توصيل", "سعر التوصيل",
                "ثمن التوصيل", "تكلفة التوصيل", "تكلفه التوصيل",
                "قداه التوصيل", "شحال التوصيل", "قداش التوصيل",
                "التوصيل للولايات", "توصيل الولايات", "توصيل 58 ولاية",
                "اسعار التوصيل 58 ولاية", "سعر التوصيل للولايات",
                "ابعثلي اسعار", "ابعث اسعار التوصيل", "ابعثلي التوصيل",
                "prix livraison", "prix de livraison", "tarif livraison",
                "tarifs de livraison", "frais de livraison", "combien la livraison",
                "livraison 58 wilayas", "prix livraison 58 wilayas", "les prix de livraison",
            ),
            "هذا منشور أسعار التوصيل للولايات الـ58:",
        ),
        (
            "delivery_duration_58_wilayas",
            ("مدة التوصيل", "وقتاش توصل", "قداه تاخذ التوصيل", "شحال تاخذ الطلبية", "وقت التوصيل", "قداه تقعد الطلبية", "شحال يوم باش توصل", "مدة الشحن", "delai de livraison", "délai de livraison", "combien de jours livraison", "quand arrive ma commande"),
            INTRO_TEXTS["delivery_duration_58_wilayas"],
        ),
        (
            "delivery_companies",
            (
                # Direct questions about the delivery providers used by Mayna.
                "شركات التوصيل", "شركة التوصيل", "شركات التوصيل لي نتعاملو معاها",
                "شركات التوصيل التي نتعامل معها", "مع من تتعامل ماينا في التوصيل",
                "مع من تتعامل mayna", "واش من شركة توصيل", "واش هي شركات التوصيل",
                "ما هي شركات التوصيل", "اسماء شركات التوصيل", "أسماء شركات التوصيل",
                "اسم شركة التوصيل", "اعطيني شركات التوصيل", "ابعثلي شركات التوصيل",
                "ابعث شركات التوصيل", "شكون شركات التوصيل", "شكون اللي يوصل الطلبات",
                "شكون يدي الكوموند", "مع من تتعاملو", "الشركات لي تخدمو معاهم",
                "شركات الليفريزون", "شركة الليفريزون", "شركات ليڤريزون",
                "شركات التوصيل المعتمدة", "شركات التوصيل المتعامل معها",
                "الناقلين لي تتعامل معاهم", "transporteur", "transporteurs",
                "societe de livraison", "société de livraison", "societes de livraison",
                "sociétés de livraison", "entreprises de livraison", "compagnie de livraison",
                "quelles sociétés de livraison", "quelles societes de livraison",
                "avec quelles sociétés", "avec quels transporteurs", "les transporteurs de mayna",
                "les sociétés avec lesquelles mayna travaille", "partenaires de livraison",
                "livreurs partenaires", "quelle société livre", "quelle entreprise livre",
                # Provider names mentioned directly should retrieve the provider list.
                "noest", "noest express", "dhd express", "48heures", "48 heures express",
                "48 heures", "yalidine", "yalidine express", "يا ليدين", "ياليدين",
                "نوست", "نوست اكسبراس", "دي اش دي", "دي اتش دي", "48 اور", "48 ساعة اكسبراس",
                "شركات توصيل ماينا", "شركة توصيل ماينا", "شركات التوصيل في ماينا",
                "شركات التوصيل تاع ماينا", "شركات التوصيل تاع mayna",
            ),
            INTRO_TEXTS["delivery_companies"],
        ),
        (
            "municipality_home_delivery",
            ("التوصيل للبلديات", "توصيل للبلدية", "التوصيل للمنزل", "يوصلو للدار", "بلديتي", "livraison a domicile", "livraison à domicile", "commune livraison"),
            INTRO_TEXTS["municipality_home_delivery"],
        ),
        (
            "customer_service_numbers",
            ("رقم خدمة العملاء", "ارقام خدمة العملاء", "رقم الهاتف", "رقم التواصل", "نتصل بخدمة العملاء", "numero service client", "numéro service client", "contact service client"),
            INTRO_TEXTS["customer_service_numbers"],
        ),
        (
            "order_confirmation_times",
            ("وقت تاكيد الطلب", "وقتاش تتاكد الطلبية", "متى يتم تاكيد الطلب", "تأكيد الطلبات", "تأكيد الطلبية", "confirmation commande", "quand la commande est confirmee", "quand la commande est confirmée"),
            INTRO_TEXTS["order_confirmation_times"],
        ),
        (
            "product_color_size_notes",
            ("الالوان والمقاسات", "لون المنتج", "مقاس المنتج", "مقاسات", "القياسات", "ملاحظات المنتج", "couleur et taille", "tailles et couleurs", "couleur disponible"),
            INTRO_TEXTS["product_color_size_notes"],
        ),
        (
            "commission_payment_days",
            ("وقتاش تخلص العمولة", "وقت دفع العمولة", "ايام دفع العمولة", "متى تدفع العمولات", "دفع العمولات", "paiement des commissions", "quand les commissions sont payees", "quand les commissions sont payées"),
            INTRO_TEXTS["commission_payment_days"],
        ),
        (
            "delivery_tracking",
            (
                "تتبع الطلب",
                "تتبع الطلبية",
                "تتبع طلبية",
                "تتبع الطلبيه",
                "تتبع طلبيه",
                "نتبع طلبيتي",
                "كيفاش نتبع",
                "كيف نتبع",
                "كيفاه نتبع",
                "نتبع الطلبية",
                "نتبع الطلب",
                "وين راهي الطلبية",
                "وين راهي الطلبيه",
                "وين وصلت الطلبية",
                "وين وصلت الطلبيه",
                "حالة الطلبية",
                "حاله الطلبيه",
                "موقع تتبع الطلبات",
                "موقع تتبع الطلبية",
                "رابط تتبع الطلبية",
                "تتبع الكوموند",
                "نتبع الكوموند",
                "رقم التتبع",
                "كيفاه نشوف الطلبية وين وصلت", "وين نلقى التتبع", "رابط التتبع", "suivi colis", "suivre colis", "suivi de livraison", "tracker commande",
                "tracking commande",
                "suivi commande",
                "suivre ma commande",
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
                "كيف نسحب العمولة", "وقتاش نسحب", "retirer commission", "retrait commission", "retirer mes gains",
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
                "نلغي الطلب", "نلغي طلبيتي", "نبدل الطلبية", "تعديل الطلب", "suivre ma commande", "annuler commande", "modifier commande", "statut commande",
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
                "حساب العموله", "كيفاش نسجل طلبية جديدة", "طريقة تسجيل طلبية", "طريقه تسجيل طلب", "شرح تسجيل الطلبية", "مسوقين جدد", "تسجيل كوموند جديدة", "enregistrer une commande", "nouvelle commande",
                "عمولتي",
                "العموله تاعي",
                "نحسب العموله",
                "كيفيه تسجيل طلبيه",
                "شرح تسجيل طلبيه",
                "ندخل كوموند", "كيف ندير كوموند", "نزيد طلبية", "commission commande", "ajouter commande", "passer commande",
            ),
            "هذا شرح تسجيل طلبية جديدة وكيفية احتساب العمولة:",
        ),
        (
            "marketplace_posting",
            (
                "marketplace",
                "ماركت بليس", "نشر في ماركت بليس للمبتدئين", "كيفاش نخدم marketplace", "annonce marketplace",
                "ماركتبليس",
                "ننشر في فايسبوك",
                "نشر في فايسبوك",
                "كيفاش ننشر",
                "نشر اعلان",
                "نشر منتج",
                "نحط منتج في فيسبوك",
                "نشر في marketplace", "كيف نحط اعلان", "publier sur marketplace", "publier produit facebook",
            ),
            "هذا شرح طريقة النشر في Marketplace للمبتدئين:",
        ),
        (
            "basket_feature",
            (
                "خاصيه السله",
                "السله", "panier mayna", "fonction panier",
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
                "سياسه الضمان", "سياسة الاستبدال والضمان", "سياسه الاستبدال والضمان", "politique de garantie", "échange produit", "echange produit",
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
                "inscription mayna", "comment s'inscrire", "creer un compte", "créer un compte", "devenir vendeur", "devenir marketeur",
            ),
            "مرحبا بيك في Mayna. هذا فيديو شرح التسجيل وكيفاش تبدا في التسويق بالعمولة:",
        ),
    ]

    for key, phrases, intro in rules:
        if any(phrase in text for phrase in phrases):
            return key, intro
    return None


def classify_with_gemini(text: str):
    """Return a known tutorial key using Gemini, or None when uncertain/unavailable."""
    if not GEMINI_API_KEY:
        return None
    keys = ", ".join(sorted(VIDEOS.keys()))
    prompt = (
        "You classify questions from Algerian affiliate marketers. The question may be in Algerian Darija, "
        "Arabic, French, or mixed. Return exactly one key from this list if the intent clearly matches; "
        "otherwise return NONE. Never answer the question. Keys: " + keys + "\nQuestion: " + text[:1200]
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 40}}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip().strip("` \n")
        result = result.splitlines()[0].strip()
        if result in VIDEOS:
            return result
        return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, IndexError, ValueError) as exc:
        logger.warning("Gemini classification unavailable: %s", exc)
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
            + CHANNEL_FOOTER
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
            + CHANNEL_FOOTER
        )
        return

    match = match_tutorial(text)
    if not match:
        topic_key = None
        # Gemini is optional: if it is not configured or cannot classify confidently,
        # the question is forwarded to the administrator instead of guessing.
        if GEMINI_API_KEY:
            import asyncio
            topic_key = await asyncio.to_thread(classify_with_gemini, text)
        if topic_key in VIDEOS:
            match = (topic_key, INTRO_TEXTS.get(topic_key, "هذا هو الشرح المناسب لسؤالك:"))
        else:
            logger.info("Unmatched group question from user_id=%s: %s", message.from_user.id if message.from_user else "unknown", text[:300])
            admin_chat_id = os.getenv("ADMIN_CHAT_ID", "").strip()
            username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else (message.from_user.first_name if message.from_user else "غير معروف")
            if admin_chat_id:
                try:
                    await context.bot.send_message(
                        chat_id=admin_chat_id,
                        text=("سؤال ما تعرّفش عليه البوت في MaynaGroup\n"
                              f"السؤال: {text[:1000]}\n"
                              f"المجموعة: {chat.title or chat.id}\n"
                              f"مرسل السؤال: {username}"),
                    )
                except TelegramError:
                    logger.exception("Could not notify admin about unmatched question")
            await message.reply_text(
                "ما لقيتش الشرح المناسب لسؤالك حاليا. وصلنا السؤال للمشرفين باش يتابعوه."
                + CHANNEL_FOOTER
            )
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
        await message.reply_text(CHANNEL_FOOTER, reply_to_message_id=message.message_id, disable_web_page_preview=True)
    except TelegramError:
        logger.exception(
            "Could not copy tutorial %s (post %s). Check channel access and message ID.",
            tutorial_key,
            message_id,
        )
        await message.reply_text(
            "ما قدرتش نبعث الشرح تلقائيا حاليا. تأكد أن البوت عنده وصول للقناة، "
            "وإذا بقى المشكل تواصل مع المشرفين."
            + CHANNEL_FOOTER
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
