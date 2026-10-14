import asyncio
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict

from telegram import Update
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

import delivery
import matcher
import product_search
from matcher import classify, extract_wilaya, normalize

# All links below refer to posts in the Mayna private channel.
# t.me/c/3071373878/<message_id> maps to chat ID -1003071373878.
MAYNA_CHANNEL_ID = -1003071373878
CHANNEL_LINK = delivery.CHANNEL_LINK

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


# Delivery prices live in delivery_prices.json and are answered by delivery.py.

GREETING_REPLY = (
    "وعليكم السلام ورحمة الله وبركاته. مرحبا بيك في مجموعة Mayna، "
    "كيفاش نقدروا نعاونك؟"
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def extract_dhd_tracking_number(text: str):
    """Recognize DHD tracking IDs without pretending we can read DHD status."""
    if not text:
        return None
    match = re.search(r"\b(DHDC[A-Z0-9]{10,})\b", text.upper())
    return match.group(1) if match else None


async def _answer_dhd_tracking(message, tracking_number: str) -> bool:
    """Offer the official public tracking page when no authorized DHD API is configured."""
    reply = (
        "📦 تعرّفت على رقم تتبع DHD: " + tracking_number + "\n\n"
        "ما نقدرش نجيب حالة الشحنة آليًا حاليًا لأن ما عندناش وصول مؤكد لواجهة تتبع آلية من DHD.\n"
        "افتح الموقع الرسمي وأدخل الرقم في خانة التتبع ثم اضغط Suivre:\n"
        "https://platform.dhd-dz.com/suivi/"
    )
    return await _safe_reply(message, reply)


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
        if _image_ref(message) is not None:
            await context.bot.copy_message(
                chat_id=admin_chat_id,
                from_chat_id=chat.id,
                message_id=message.message_id,
            )
        return True
    except TelegramError:
        logger.exception("Could not notify admin about question")
        return False


def _image_ref(message):
    """(file_id, mime_type) of the image attached to the message, or None.

    Covers compressed photos and images sent as a file (document with an image/* MIME type).
    """
    photos = getattr(message, "photo", None)
    if photos:
        best = photos[-1]  # Telegram lists sizes ascending; the last one is the largest
        for candidate in reversed(photos):
            size = getattr(candidate, "file_size", None)
            if not size or size <= product_search.MAX_IMAGE_BYTES:
                best = candidate
                break
        return getattr(best, "file_id", None), "image/jpeg"
    document = getattr(message, "document", None)
    mime = getattr(document, "mime_type", None) or ""
    if document is not None and isinstance(mime, str) and mime.startswith("image/"):
        return getattr(document, "file_id", None), mime
    return None


async def _download_image(context, ref):
    """Download the image bytes, or None if Telegram refuses (never raises)."""
    file_id = ref[0] if ref else None
    if not file_id:
        return None
    try:
        tg_file = await context.bot.get_file(file_id)
        return bytes(await tg_file.download_as_bytearray())
    except Exception:
        logger.exception("Could not download the image from Telegram")
        return None


async def _answer_product(update, context, text, ref) -> bool:
    """Product-spec flow. Returns True if the message was fully handled (reply or escalation sent),
    False if it is not a product question and the normal flow must continue."""
    message = update.effective_message
    chat = update.effective_chat
    image = await _download_image(context, ref) if ref else None
    mime = ref[1] if ref else "image/jpeg"
    outcome = await asyncio.to_thread(
        product_search.search_product, text, image, mime, GEMINI_API_KEY, bool(ref)
    )
    logger.info(
        "Product search: kind=%s reason=%s image=%s message_id=%s",
        outcome.kind, outcome.reason or "-", bool(ref), message.message_id,
    )
    if outcome.kind == "not_product":
        return False
    if outcome.kind in ("answer", "ask_model"):
        await _safe_reply(message, outcome.text)
        return True
    # escalate: tell the member only what is true
    notified = await _notify_admin(context, message, chat, text, "منتج: " + outcome.reason)
    if notified:
        reply = (
            "ما لقيتش معلومات مؤكدة وموثوقة على هذا المنتج، والسؤال محتاج تحقق. "
            + ("وصلنا السؤال مع الصورة للمشرفين" if ref else "وصلنا السؤال للمشرفين")
            + " باش يتأكدوا ويجاوبوك."
        )
    else:
        reply = (
            "ما لقيتش معلومات مؤكدة وموثوقة على هذا المنتج، وما قدرتش نوصل السؤال للمشرفين تلقائيا. "
            "ممكن تنادي المشرفين مباشرة هنا في المجموعة."
        )
    await _safe_reply(message, reply + CHANNEL_FOOTER)
    return True


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


async def _safe_reply(message, text: str) -> bool:
    """Reply to the member. If Telegram refuses the reply (e.g. the original message was
    deleted), retry once as a plain group message. Never raises; returns True if sent."""
    try:
        await message.reply_text(text, reply_to_message_id=message.message_id, disable_web_page_preview=True)
        return True
    except TelegramError:
        logger.exception("Telegram refused the reply (message_id=%s); retrying without reply_to", message.message_id)
    try:
        await message.reply_text(text, disable_web_page_preview=True)
        return True
    except TelegramError:
        logger.exception("Telegram refused the plain reply too (message_id=%s); answer NOT delivered", message.message_id)
        return False


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
    image_ref = _image_ref(message)
    has_photo = image_ref is not None
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

    # 0) DHD tracking IDs are handled before topic classification so the number is not
    # mistaken for an ordinary question. Status lookup is intentionally not fabricated.
    tracking_number = extract_dhd_tracking_number(text)
    if tracking_number:
        await _answer_dhd_tracking(message, tracking_number)
        return

    # 0) Delivery prices: answered from the local table, before any other topic can claim the question.
    try:
        price = delivery.answer(text)
    except Exception:  # never let a bug here silence the bot
        logger.exception("Delivery engine crashed; falling back to the generic flow")
        price = None
    if price is not None and price.handled:
        sent = await _safe_reply(message, price.text)
        logger.info(
            "Delivery answer: kind=%s wilayas=%s show=%s fuzzy=%s sent=%s message_id=%s",
            price.kind, ",".join(price.wilayas) or "-", price.show, price.fuzzy, sent, message.message_id,
        )
        return
    if price is not None:
        logger.info("Delivery engine skipped message_id=%s reason=%s", message.message_id, price.reason)

    result = classify(text)
    topic = result.topic if result.status == "match" else None

    # 0.5) Product specs (photo + question, or a spec question in text). Tutorials/delivery answered above
    # keep priority; a confident tutorial match is never taken over by this flow.
    if topic is None and (has_photo or product_search.looks_like_spec_question(text)):
        try:
            if await _answer_product(update, context, text, image_ref):
                return
        except Exception:  # never let a bug here silence the bot
            logger.exception("Product search crashed; falling back to the generic flow")

    # 1) Local search first. Gemini only when the local engine is not confident.
    if topic is None and GEMINI_API_KEY:
        gemini_topic = await asyncio.to_thread(classify_with_gemini, text, result.candidates)
        if gemini_topic in VIDEOS:
            logger.info("Gemini resolved question to %s", gemini_topic)
            # exchange_warranty_policy_original is delivered through exchange_warranty_policy
            topic = "exchange_warranty_policy" if gemini_topic == "exchange_warranty_policy_original" else gemini_topic

    if topic:
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
    if isinstance(context.error, Conflict):
        logger.error(
            "Telegram Conflict: another instance of this bot (same token) is polling. "
            "Stop the old run/host, otherwise updates are split between the two and questions get no answer."
        )
        return
    logger.error("Unhandled exception while processing update", exc_info=context.error)


def build_application(token: str) -> Application:
    """Create the Telegram application with all handlers (no network access here)."""
    app = Application.builder().token(token).build()
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members)
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & ~filters.StatusUpdate.ALL
            & ~filters.COMMAND
            & (filters.TEXT | filters.CAPTION | filters.PHOTO | filters.Document.ALL),
            handle_group_message,
        )
    )
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_posts))
    app.add_error_handler(handle_error)
    return app


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

    selftest = delivery.answer("شحال التوصيل لوهران؟")
    logger.info(
        "Build: sha=%s delivery_wilayas=%d delivery_selftest=%s",
        os.getenv("GITHUB_SHA", "local")[:7], len(delivery.WILAYAS),
        "OK" if selftest.handled and selftest.wilayas == ["وهران"] else "FAILED",
    )

    app = build_application(token)

    logger.info("Mayna assistant bot starting.")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()
