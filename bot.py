import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

import matcher
from matcher import classify, extract_wilaya, normalize

# All links below refer to posts in the Mayna private channel.
# t.me/c/3071373878/<message_id> maps to chat ID -1003071373878.
MAYNA_CHANNEL_ID = -1003071373878
CHANNEL_LINK = "https://t.me/+wyKej2q0oK0zYjI0"

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

# Topics whose answer is more than one channel post (sent in this order).
EXTRA_POSTS = {
    "exchange_warranty_policy": ["exchange_warranty_policy_original"],
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

# Short Arabic labels used when the bot asks the member to clarify.
TOPIC_LABELS = {
    "registration": "التسجيل في Mayna",
    "new_order_commission": "تسجيل طلبية واحتساب العمولة",
    "withdraw_commission": "سحب العمولة",
    "order_management_status": "تعديل/إلغاء الطلبية وحالتها",
    "delivery_tracking": "تتبع الطلبية",
    "marketplace_posting": "النشر في Marketplace",
    "basket_feature": "خاصية السلة",
    "google_lens_chatgpt_product_research": "البحث عن المنتجات بـ Google Lens وChatGPT",
    "exchange_warranty_policy": "الاستبدال والضمان",
    "mayna_app_download_images_copy_text": "تحميل الصور ونسخ النصوص من التطبيق",
    "delivery_prices_58_wilayas": "أسعار التوصيل",
    "customer_service_numbers": "أرقام خدمة العملاء",
    "order_confirmation_times": "أوقات تأكيد الطلبات",
    "delivery_companies": "شركات التوصيل",
    "municipality_home_delivery": "التوصيل للمنزل/البلدية",
    "product_color_size_notes": "الألوان والمقاسات",
    "commission_payment_days": "أيام دفع العمولات",
    "delivery_duration_58_wilayas": "مدة التوصيل",
}
LOCATION_TOPICS = {
    "delivery_prices_58_wilayas",
    "delivery_duration_58_wilayas",
    "municipality_home_delivery",
}

CHANNEL_FOOTER = (
    "\n\nلمعلومات وشروحات أخرى، ادخل لقناة Mayna للتسويق:\n" + CHANNEL_LINK
)


# Prices transcribed from Mayna's supplied "أسعار التوصيل" poster.
# Poster columns: البيت (home delivery), مكتب التوصيل (pickup office).
DELIVERY_PRICES = {
    "أدرار": (1100, 550), "الشلف": (650, 350), "الأغواط": (800, 350),
    "أم البواقي": (650, 350), "باتنة": (650, 350), "بجاية": (600, 350),
    "بسكرة": (700, 350), "بشار": (900, 500), "البليدة": (450, 450),
    "البويرة": (600, 350), "تمنراست": (1500, 700), "تبسة": (700, 350),
    "تلمسان": (650, 350), "تيارت": (700, 350), "تيزي وزو": (600, 350),
    "الجزائر": (300, 300), "الجلفة": (800, 450), "جيجل": (650, 350),
    "سطيف": (650, 350), "سعيدة": (700, 350), "سكيكدة": (650, 350),
    "سيدي بلعباس": (650, 350), "عنابة": (650, 350), "قالمة": (700, 350),
    "قسنطينة": (650, 350), "المدية": (600, 350), "مستغانم": (650, 350),
    "المسيلة": (700, 350), "معسكر": (650, 350), "ورقلة": (900, 450),
    "وهران": (600, 350), "البيض": (1000, 800), "إليزي": (1500, 1500),
    "برج بوعريريج": (650, 350), "بومرداس": (400, 400), "الطارف": (700, 350),
    "تندوف": (1300, 1300), "تيسمسيلت": (650, 350), "الوادي": (900, 500),
    "خنشلة": (700, 350), "سوق أهراس": (750, 400), "تيبازة": (400, 300),
    "ميلة": (700, 400), "عين الدفلى": (650, 350), "النعامة": (900, 450),
    "عين تموشنت": (650, 400), "غرداية": (800, 450), "غليزان": (750, 400),
    "تيميمون": (1200, 750), "برج باجي مختار": (9999, 9999),
    "أولاد جلال": (850, 550), "بني عباس": (1000, 1000), "عين صالح": (1600, 900),
    "عين قزام": (9999, 9999), "تقرت": (850, 450), "جانت": (9999, 9999),
    "المغير": (950, 500), "المنيعة": (950, 550),
}

# Alternate spellings in Arabic/French/transliteration for all 58 wilayas.
PRICE_WILAYA_ALIASES = {
    "adrar": "أدرار", "chlef": "الشلف", "laghouat": "الأغواط",
    "oum el bouaghi": "أم البواقي", "oum bouaghi": "أم البواقي",
    "batna": "باتنة", "bejaia": "بجاية", "béjaïa": "بجاية", "bgayet": "بجاية",
    "biskra": "بسكرة", "bechar": "بشار", "béchar": "بشار", "blida": "البليدة",
    "bouira": "البويرة", "tamanrasset": "تمنراست", "tebessa": "تبسة",
    "tébessa": "تبسة", "tlemcen": "تلمسان", "tiaret": "تيارت",
    "tizi ouzou": "تيزي وزو", "alger": "الجزائر", "algérie": "الجزائر",
    "djelfa": "الجلفة", "jijel": "جيجل", "setif": "سطيف", "sétif": "سطيف",
    "saida": "سعيدة", "saïda": "سعيدة", "skikda": "سكيكدة",
    "sidi bel abbes": "سيدي بلعباس", "annaba": "عنابة", "guelma": "قالمة",
    "constantine": "قسنطينة", "medea": "المدية", "médéa": "المدية",
    "mostaganem": "مستغانم", "msila": "المسيلة", "m'sila": "المسيلة",
    "mascara": "معسكر", "ouargla": "ورقلة", "oran": "وهران",
    "el bayadh": "البيض", "illizi": "إليزي", "bordj bou arreridj": "برج بوعريريج",
    "bba": "برج بوعريريج", "boumerdes": "بومرداس", "boumerdès": "بومرداس",
    "el tarf": "الطارف", "tindouf": "تندوف", "tissemsilt": "تيسمسيلت",
    "el oued": "الوادي", "khenchela": "خنشلة", "souk ahras": "سوق أهراس",
    "tipaza": "تيبازة", "mila": "ميلة", "ain defla": "عين الدفلى",
    "naama": "النعامة", "naâma": "النعامة", "ain temouchent": "عين تموشنت",
    "ghardaia": "غرداية", "relizane": "غليزان", "timimoun": "تيميمون",
    "bordj badji mokhtar": "برج باجي مختار", "ouled djellal": "أولاد جلال",
    "beni abbes": "بني عباس", "ain salah": "عين صالح", "in salah": "عين صالح",
    "ain guezzam": "عين قزام", "in guezzam": "عين قزام", "touggourt": "تقرت",
    "djanet": "جانت", "el mghair": "المغير", "el meniaa": "المنيعة",
}

def find_price_wilaya(text: str):
    """Find a city mentioned in a delivery-price question."""
    normalized = normalize(text)
    # Longest aliases first, to avoid matching a short city inside a longer name.
    for alias in sorted(PRICE_WILAYA_ALIASES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(normalize(alias))}(?!\w)", normalized):
            return PRICE_WILAYA_ALIASES[alias]
    # Arabic names as printed on the poster, including names absent from matcher.WILAYAS.
    for name in sorted(DELIVERY_PRICES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(normalize(name))}(?!\w)", normalized):
            return name
    return None

def format_delivery_price(wilaya: str) -> str:
    home, office = DELIVERY_PRICES[wilaya]
    if home == 9999 and office == 9999:
        return (
            f"أسعار التوصيل إلى {wilaya} حسب جدول Mayna الحالي:\\n"
            "• التوصيل للبيت: 9999 دج\\n• مكتب التوصيل: 9999 دج\\n\\n"
            "ملاحظة: السعر ظاهر هكذا في الصورة المرجعية؛ يُفضّل التأكد من الإدارة قبل تأكيد الطلب."
            + CHANNEL_FOOTER
        )
    return (
        f"أسعار التوصيل إلى {wilaya} حسب جدول Mayna:\\n"
        f"• التوصيل للبيت: {home} دج\\n"
        f"• مكتب التوصيل: {office} دج"
        + CHANNEL_FOOTER
    )


GREETING_REPLY = (
    "وعليكم السلام ورحمة الله وبركاته. مرحبا بيك في مجموعة Mayna، "
    "كيفاش نقدروا نعاونك؟"
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def is_greeting(text: str) -> bool:
    return matcher.is_greeting(text)


def match_tutorial(text: str):
    """Return (tutorial key, intro text) for a confidently recognized question, else None."""
    result = classify(text)
    if result.status == "match" and result.topic in VIDEOS:
        return result.topic, INTRO_TEXTS.get(result.topic, "")
    return None


def _env_chat_id(name: str):
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw  # e.g. @channelusername


class _SeenMessages:
    """Bounded memory of handled messages: one reply per message, no reply loops."""

    def __init__(self, limit: int = 5000):
        self._items = OrderedDict()
        self._limit = limit

    def add_if_new(self, key) -> bool:
        if key in self._items:
            return False
        self._items[key] = time.time()
        while len(self._items) > self._limit:
            self._items.popitem(last=False)
        return True


_SEEN = _SeenMessages()

# Gemini is optional. After a quota/auth error we pause calls for a while.
_GEMINI_PAUSED_UNTIL = 0.0


def classify_with_gemini(text: str, candidates=None):
    """Return a known tutorial key using Gemini, or None when uncertain/unavailable.

    Only the question and the topic list (no answers, no secrets) are sent.
    The key travels in a header, never in the URL, so it cannot leak into logs.
    """
    global _GEMINI_PAUSED_UNTIL
    if not GEMINI_API_KEY or time.time() < _GEMINI_PAUSED_UNTIL:
        return None
    topics = {k: TOPIC_LABELS[k] for k in TOPIC_LABELS}
    topic_lines = "\n".join(f"- {k}: {v}" for k, v in topics.items())
    hint = ""
    if candidates:
        hint = "Most likely candidates (not certain): " + ", ".join(candidates) + "\n"
    prompt = (
        "You classify questions from Algerian affiliate marketers (Darija, Arabic, French or mixed). "
        "Return exactly one topic key from the list if the intent clearly matches; otherwise return NONE. "
        "Never answer the question and never invent information.\n"
        f"Topics:\n{topic_lines}\n{hint}Question: {text[:1200]}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 40},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip().strip("` \n")
        result = result.splitlines()[0].strip() if result else ""
        return result if result in VIDEOS else None
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429):
            _GEMINI_PAUSED_UNTIL = time.time() + 600
        logger.warning("Gemini HTTP error %s (paused=%s)", exc.code, exc.code in (401, 403, 429))
        return None
    except Exception as exc:  # network, timeout, malformed JSON ...
        logger.warning("Gemini classification unavailable: %s", type(exc).__name__)
        return None


def _user_label(message) -> str:
    user = message.from_user
    if not user:
        return "غير معروف"
    if user.username:
        return f"@{user.username}"
    return f"{user.first_name or 'غير معروف'} (id {user.id})"


def _message_link(chat, message) -> str:
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message.message_id}"
    chat_id = str(chat.id)
    if chat_id.startswith("-100"):
        return f"https://t.me/c/{chat_id[4:]}/{message.message_id}"
    return ""


async def _notify_admin(context, message, chat, text, reason, candidates=()):
    """Send the question to the admin chat. Returns True ONLY if Telegram accepted it."""
    admin_chat_id = _env_chat_id("ADMIN_CHAT_ID")
    if admin_chat_id is None:
        logger.error("ADMIN_CHAT_ID is not set: cannot escalate question.")
        return False
    link = _message_link(chat, message)
    body = (
        f"سؤال يحتاج متابعة في MaynaGroup ({reason})\n"
        f"السؤال: {text[:1000] or '(صورة بدون نص)'}\n"
        f"المجموعة: {chat.title or chat.id}\n"
        f"مرسل السؤال: {_user_label(message)}"
    )
    if link:
        body += f"\nرابط الرسالة: {link}"
    if candidates:
        body += "\nمواضيع محتملة: " + "، ".join(TOPIC_LABELS.get(c, c) for c in candidates)
    try:
        await context.bot.send_message(chat_id=admin_chat_id, text=body)
        if getattr(message, "photo", None):
            await context.bot.copy_message(
                chat_id=admin_chat_id,
                from_chat_id=chat.id,
                message_id=message.message_id,
            )
        return True
    except TelegramError:
        logger.exception("Could not notify admin about question")
        return False


async def _send_posts(context, message, chat, topic) -> bool:
    keys = [topic] + EXTRA_POSTS.get(topic, [])
    sent_any = False
    for key in keys:
        message_id = VIDEOS[key]
        try:
            await context.bot.copy_message(
                chat_id=chat.id,
                from_chat_id=MAYNA_CHANNEL_ID,
                message_id=message_id,
                reply_to_message_id=message.message_id,
            )
            sent_any = True
            logger.info("Tutorial %s (post %s) copied to chat_id=%s", key, message_id, chat.id)
        except TelegramError:
            logger.exception(
                "Could not copy tutorial %s (post %s). Check channel access, bot membership and message ID.",
                key,
                message_id,
            )
    return sent_any


async def _answer_topic(update, context, topic, wilaya=""):
    message = update.effective_message
    chat = update.effective_chat
    intro = INTRO_TEXTS.get(topic, "هذا هو الشرح المناسب لسؤالك:")
    if wilaya and topic in LOCATION_TOPICS:
        intro += f"\nولايتك ({wilaya}) لقاها في المنشور."
    await message.reply_text(intro)
    if await _send_posts(context, message, chat, topic):
        # The channel link goes in a separate, later message so it never mixes with the post.
        await message.reply_text(
            "لمعلومات وشروحات أخرى، ادخل لقناة Mayna للتسويق:\n" + CHANNEL_LINK,
            reply_to_message_id=message.message_id,
            disable_web_page_preview=True,
        )
        return
    await _notify_admin(context, message, chat, message.text or message.caption or "", "فشل نسخ المنشور", [topic])
    await message.reply_text(
        "ما قدرتش نبعث الشرح تلقائيا حاليا. إذا بقى المشكل تواصل مع المشرفين."
        + CHANNEL_FOOTER
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


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
            "المجموعة هذه مخصصة لاستفسارات مسوقي Mayna: الشروحات، تسجيل الطلبات، "
            "العمولات والتوصيل وتتبع الطلبيات. "
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
    if getattr(message, "via_bot", None):
        return

    restrict = os.getenv("RESTRICT_TO_GROUP", "").strip() == "1"
    group_id = _env_chat_id("GROUP_CHAT_ID")
    if restrict and group_id is not None and chat.id != group_id:
        logger.info("Ignoring chat_id=%s (GROUP_CHAT_ID=%s, RESTRICT_TO_GROUP=1)", chat.id, group_id)
        return

    text = message.text or message.caption or ""
    has_photo = bool(getattr(message, "photo", None))
    if not text and not has_photo:
        return
    if text.startswith("/"):
        return

    if not _SEEN.add_if_new((chat.id, message.message_id)):
        logger.info("Duplicate update for message %s ignored", message.message_id)
        return

    logger.info(
        "Group message received chat_id=%s message_id=%s len=%s photo=%s",
        chat.id, message.message_id, len(text), has_photo,
    )

    if text and is_greeting(text):
        await message.reply_text(GREETING_REPLY + CHANNEL_FOOTER)
        return

    if not text:
        # A product photo without any question: nothing to answer, do not spam the group.
        return

    result = classify(text)
    topic = result.topic if result.status == "match" else None

    # 1) Local search first. Gemini only when the local engine is not confident.
    if topic is None and GEMINI_API_KEY:
        gemini_topic = await asyncio.to_thread(classify_with_gemini, text, result.candidates)
        if gemini_topic in VIDEOS:
            logger.info("Gemini resolved question to %s", gemini_topic)
            # exchange_warranty_policy_original is delivered through exchange_warranty_policy
            topic = "exchange_warranty_policy" if gemini_topic == "exchange_warranty_policy_original" else gemini_topic

    if topic:
        # For a city-specific delivery-price question, answer with that city's
        # two prices only; do not dump the entire 58-wilaya poster.
        if topic == "delivery_prices_58_wilayas":
            price_wilaya = find_price_wilaya(text)
            if price_wilaya:
                await message.reply_text(format_delivery_price(price_wilaya), quote=True)
                return
            await message.reply_text(
                "باش نعطيك السعر الصحيح، اكتب اسم الولاية. مثال: شحال التوصيل لوهران؟"
                + CHANNEL_FOOTER,
                quote=True,
            )
            return
        await _answer_topic(update, context, topic, result.wilaya or extract_wilaya(normalize(text)) or "")
        return

    # 2) Not sure which topic: short clarification instead of guessing.
    if result.status == "ambiguous" and result.candidates and not has_photo:
        labels = [TOPIC_LABELS[c] for c in result.candidates[:3] if c in TOPIC_LABELS]
        if labels:
            await message.reply_text(
                "باش نوجهك للشرح الصحيح، تقصد واحد من هذه المواضيع؟\n- "
                + "\n- ".join(labels)
                + "\nاكتب سؤالك بتفصيل أكثر شوية."
                + CHANNEL_FOOTER
            )
            return

    # 3) No reliable answer: escalate, and only claim success if the admin message was delivered.
    logger.info(
        "Unmatched group question from user_id=%s: %s",
        message.from_user.id if message.from_user else "unknown",
        text[:300],
    )
    notified = await _notify_admin(
        context, message, chat, text,
        "صورة" if has_photo else "لم يُعثر على شرح مناسب",
        result.candidates,
    )
    if notified:
        await message.reply_text(
            "ما لقيتش الشرح المناسب لسؤالك حاليا. وصلنا السؤال للمشرفين باش يتابعوه."
            + CHANNEL_FOOTER
        )
    else:
        await message.reply_text(
            "ما لقيتش الشرح المناسب لسؤالك، وما قدرتش نوصل السؤال للمشرفين تلقائيا. "
            "ممكن تنادي المشرفين مباشرة هنا في المجموعة."
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


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Make hidden handler/polling errors visible in GitHub Actions logs."""
    logger.error("Unhandled exception while processing update", exc_info=context.error)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN. Add it under GitHub repository Settings "
            "-> Secrets and variables -> Actions -> Repository secrets."
        )

    logger.info(
        "Config: GEMINI_API_KEY=%s ADMIN_CHAT_ID=%s GROUP_CHAT_ID=%s",
        "set" if GEMINI_API_KEY else "missing",
        "set" if os.getenv("ADMIN_CHAT_ID", "").strip() else "missing",
        "set" if os.getenv("GROUP_CHAT_ID", "").strip() else "missing",
    )

    app = Application.builder().token(token).build()
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members)
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & ~filters.StatusUpdate.ALL
            & ~filters.COMMAND
            & (filters.TEXT | filters.CAPTION | filters.PHOTO),
            handle_group_message,
        )
    )
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_posts))
    app.add_error_handler(handle_error)

    logger.info("Mayna assistant bot starting.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
