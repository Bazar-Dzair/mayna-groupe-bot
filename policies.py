# -*- coding: utf-8 -*-
"""Fixed company policies answered directly by the bot (no channel post, no admin escalation).

Two policies live here:

1. STORE   - a customer wants to come to a shop / pick up in person / buy on the spot.
             Answer: Mayna works online only, there is no shop (it is a big depot).
2. WHOLESALE - a marketer asks about wholesale / big quantities.
             Answer: wholesale exists at the company prices, minimum 3 pieces, delivered in
             batches of 3; a customer who wants everything at once must pay half in advance.

Pure logic, no network and no Telegram import, so it is easy to test (tests/test_policies.py).
`detect(text)` returns a PolicyAnswer; handled=False means "not one of these questions".
"""
import re
from dataclasses import dataclass

from matcher import normalize
from moderation import ADMIN_MENTION

KIND_STORE = "store"
KIND_WHOLESALE = "wholesale"
KIND_BULK_ONCE = "wholesale_all_at_once"

MIN_PIECES = 3

# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

STORE_REPLY = (
    "أخي المسوق، حنا نخدمو أونلاين فقط 🛒 وما عندناش محل.\n"
    "هذا ديبو (مخزن) كبير ونبيعو عن طريق الأنترنت فقط، يعني الزبون ما يقدرش يجي يشري "
    "مباشرة، سواء كان من الجزائر العاصمة أو من أي ولاية أخرى.\n"
    "الزبون يطلب المنتج عن طريقك، وتوصله الطلبية بالتوصيل."
)

_NOTE_TEXT = "الزبون طلب كمية وسيدفع نصف المبلغ المتفق عليه"

_ALL_AT_ONCE_PART = (
    "⚠️ إذا الزبون حب نبعثولو الكمية كاملة دفعة وحدة: هذا ما نقدروش نديروه بدون ضمان، "
    "لأن ممكن الطلبية ترجع (روتور) ونرجعو في الخسارة. "
    "لهذا لازم الزبون يدفع نصف المبلغ مسبقا في حساب الشركة، "
    f"وللدفع وتفاصيل الحساب تواصل مع المسؤول {ADMIN_MENTION}.\n\n"
    "📝 وكي تسجل الطلبية على هذا الأساس (الزبون قبل ودفع النصف)، لازم تكتب في الملاحظة (Note):\n"
    f"«{_NOTE_TEXT}»"
)

WHOLESALE_REPLY = (
    "طبعا نبيعو بالجملة ✅\n"
    "أسعار الشركة تبقى كيما هي (هي أسعار الجملة)، وانت أدرى بكيفاش تبيع بالعمولة على سعر الجملة.\n\n"
    f"📦 أقل كمية هي {MIN_PIECES} حبات. وتتسجل الطلبيات على دفعات:\n"
    f"• كل طلبية {MIN_PIECES} حبات.\n"
    f"• كي توصل الـ{MIN_PIECES} حبات الأولى للزبون، تزيد الدفعة الثانية، وبعدها الثالثة، "
    "وهكذا حتى تكمل الكمية لي طلبها.\n\n"
    + _ALL_AT_ONCE_PART
)

BULK_ONCE_REPLY = (
    f"الأصل عندنا أن الكمية تتسجل على دفعات، كل دفعة {MIN_PIECES} حبات (أقل كمية)، "
    "وكل ما توصل دفعة للزبون تزيد اللي بعدها حتى تكمل الكمية.\n\n"
    + _ALL_AT_ONCE_PART
)


@dataclass
class PolicyAnswer:
    handled: bool
    kind: str = ""
    reason: str = ""
    text: str = ""


# ---------------------------------------------------------------------------
# Patterns (applied to normalize(text): lower-case, ة->ه, أ->ا, ى->ي, no punctuation)
# ---------------------------------------------------------------------------

_P = r"[وفبلك]?(?:ال)?"  # optional one-letter prefix + definite article
_S = r"(?:كم|ك|نا|ي)?"   # optional pronoun suffix (محلكم, محلك ...)

STORE_WORD = re.compile(
    rf"(?<!\w){_P}(?:محل|محلات|حانوت|حانوتات|مغازه|دكان|دكانه|مقر|مخزن|ديبو|ستور|"
    rf"متجر)(?:كم|ك|نا)?(?!\w)"
    r"|(?<!\w)(?:le |votre |un )?(?:magasin|boutique|local|showroom|depot|point de vente|"
    r"store|shop)(?!\w)"
)
# the customer physically coming
COME = re.compile(
    r"(?<!\w)(?:ي|ن|ت)?(?:جي|جو|جيو|زور|زورو|نزل|مر|عدي)(?!\w)|(?<!\w)(?:جاي|جايين|جايه|راح|يروح|نروح|"
    r"يتوجه|ينتقل|يحضر|يحضرو)(?!\w)"
    r"|(?<!\w)(?:venir|viens|vient|passer|passe|passent|aller|va|vais|se deplacer|deplacer|"
    r"descendre|visiter|visite)(?!\w)"
)
COME_STRICT = re.compile(
    r"(?<!\w)(?:ي|ن)(?:جي|جو|جيو|زور|زورو|نزل|مر)(?!\w)|(?<!\w)(?:جاي|جايين|جايه)(?!\w)"
    r"|(?<!\w)(?:venir|viens|vient|passer|passe|passent|se deplacer|descendre|visiter)(?!\w)"
)
# buying / taking on the spot
TAKE = re.compile(
    r"(?<!\w)(?:ي|ن|ت)?(?:دي|اخد|اخذ|شري|اشتري|استلم|جيب|شتري)(?!\w)"
    r"|(?<!\w)(?:استلام|شراء|اشتراء)(?!\w)"
    r"|(?<!\w)(?:acheter|achete|achet|prendre|prends|prend|recuperer|recupere|retirer|retrait|"
    r"ramasser|ramasse|pickup|pick up)(?!\w)"
)
FROM_YOU = re.compile(r"(?:من )?(?:عندكم|عندك|منكم|منك)(?!\w)|chez vous|chez toi")
WHERE = re.compile(
    r"(?<!\w)(?:وين|فين|اين|واين|وينا|win|wine|ou|où)(?!\w)|(?<!\w)(?:عنوان\w*|موقع\w*|مكان\w*|"
    r"adresse\w*|localisation|position|situe|situes|trouve|trouvez|trouvent|"
    r"تقعدو|تقعد|تسكنو|مكانكم)(?!\w)"
)
HAS_STORE = re.compile(
    r"(?<!\w)(?:عندكم|عندك|عندكوم|كاين|كاينه|كاينين|يوجد|توجد|هل|هل لديكم|لديكم|avez|avez-vous|"
    r"y a|il y a|existe|est-ce que|est ce que)(?!\w)"
)
# talking about something else: money, delivery, tracking ...
NOT_STORE_TOPIC = re.compile(
    r"(?<!\w)(?:عمول\w*|ارباح|ربح|commission\w*|رصيد\w*|فلوس|دراهم|مستحقات|"
    r"سحب|نسحب|ياخد العمول\w*|تتبع|suivi|tracking)(?!\w)"
)
FIRST_PERSON_SHOP = re.compile(
    r"(?<!\w)(?:عندي|عندنا|نملك|نفتح|نبي|نحب نفتح|فتحت|لدي|ندير|ديرت|j ai|jai|ouvrir|j'ai)\s+(?:\w+\s+){0,1}"
    rf"{_P}(?:محل|حانوت|مغازه|دكان|متجر|magasin|boutique|local)"
)

WHOLESALE_WORD = re.compile(
    rf"(?<!\w)[وفبلك]?(?:ال)?جمل[ةه](?!\w)(?!\s+(?:مفيد|من ))"
    r"|(?<!\w)(?:wholesale|grossiste\w*|grosiste\w*|en gros|de gros|vente en gros|prix de gros|"
    r"prix gros|demi gros|demi-gros|ديمي ?غرو|ديمي ?جروس|غروس|جروس)(?!\w)"
)
QTY_WORD = re.compile(
    r"(?<!\w)[وفبلك]?(?:ال)?(?:كميه|كميات|كمي|quantite\w*|quantity|quantities)(?!\w)"
)
QTY_BIG = re.compile(
    r"(?<!\w)(?:كبير\w*|كثير\w*|بزاف|معتبر\w*|ضخم\w*|كامل\w*|كلها|كله|كل|importante?s?|grande?s?|"
    r"grosse?s?|beaucoup|plusieurs|enorme\w*)(?!\w)"
)
QTY_WANT = re.compile(
    r"(?<!\w)(?:ي|ن|ت|ا)?(?:حب|بغي|بي|دي|اخد|اخذ|شري|اشتري|طلب|بعث\\w*|ارسل\\w*|ابعث\\w*|رسل\\w*|وفر|جيب|"
    r"ابي|يبي|حاب|باغي)(?!\w)"
    r"|(?<!\w)(?:veut|veux|voudrais|voudrait|souhaite|acheter|prendre|commander|commande|envoyer|envoie|"
    r"besoin)(?!\w)"
)
AVAILABILITY = re.compile(
    r"(?<!\w)(?:متوفر\w*|موجود\w*|ستوك|stock|disponible\w*|rupture|متاح\w*|خلص\w*|نفد\w*|"
    r"باقي|باقيه|بقات|بقاو)(?!\w)"
)
# "10 حبات", "5 قطع", "20 pieces"
NUM_UNITS = re.compile(
    r"(?<!\w)(\d{1,4})\s*(?:حبه|حبات|حبة|قطعه|قطع|قطعة|وحده|وحدات|وحدة|منتج\w*|سلعه|سلعة|كارتون\w*|"
    r"pieces?|pcs|pc|unites?|articles?|exemplaires?|produits?|cartons?|x)(?!\w)"
)
ALL_AT_ONCE = re.compile(
    r"(?:دفعه|مره|مرا|خطره|نوبه|شحنه)\s*(?:وحده|واحده|وحد|وحدا)"
    r"|(?<!\w)(?:كلها|كامله|الكل|كاملا|دفعه واحده|دفعه وحده)(?!\w)"
    r"|en une (?:seule )?fois|d un coup|dun coup|d un seul coup|en une seule fois|tout en un|"
    r"tout d un coup|tout ensemble|en meme temps"
)
PREPAY = re.compile(
    r"(?<!\w)(?:عربون\w*|مسبق\w*|مقدم\w*|نصف المبلغ|نص المبلغ|نصف الثمن|نص الثمن|نصف السعر|"
    r"avance|acompte|prepaiement|paiement avant|moitie|50)(?!\w)|paiement a l avance|paye avant|payer avant|"
    r"قبل الدفع|الدفع قبل"
)


def _has_number_at_least(nm: str, minimum: int) -> bool:
    return any(int(m.group(1)) >= minimum for m in NUM_UNITS.finditer(nm))


def _is_store_question(nm: str) -> bool:
    if NOT_STORE_TOPIC.search(nm):
        return False
    store = bool(STORE_WORD.search(nm))
    if store and FIRST_PERSON_SHOP.search(nm):
        return False  # «عندي محل نبيع فيه ...»: someone talking about THEIR shop
    come = bool(COME_STRICT.search(nm)) or bool(COME.search(nm)) and (store or bool(TAKE.search(nm)))
    take = bool(TAKE.search(nm))
    from_you = bool(FROM_YOU.search(nm))
    if store:
        # «يجي للمحل» / «يجي يشري من المحل» / «وين المحل» / «عندكم محل؟» / «نستلم من المحل»
        if come or take or WHERE.search(nm) or HAS_STORE.search(nm):
            return True
        return False
    # no shop word: «زبون حب يجي يدي منتج من عندكم»
    if COME_STRICT.search(nm) and take:
        return True
    if COME_STRICT.search(nm) and from_you:
        return True
    return False


def _is_wholesale_question(nm: str) -> bool:
    if WHOLESALE_WORD.search(nm):
        return True
    if AVAILABILITY.search(nm):
        return False  # «الكمية متوفرة؟» is a stock question, not a wholesale one
    if QTY_WORD.search(nm) and (QTY_BIG.search(nm) or QTY_WANT.search(nm)):
        return True
    # a clearly bigger order than the 3-piece minimum: «زبون حب ياخد 10 حبات»
    if _has_number_at_least(nm, MIN_PIECES + 1) and (QTY_WANT.search(nm) or ALL_AT_ONCE.search(nm)):
        return True
    return False


def detect(text: str) -> PolicyAnswer:
    nm = normalize(text)
    if not nm:
        return PolicyAnswer(False, reason="empty")

    if _is_store_question(nm):
        return PolicyAnswer(True, KIND_STORE, "store_visit", STORE_REPLY)

    if _is_wholesale_question(nm):
        # asked specifically about getting everything at once / paying in advance
        wants_once = bool(ALL_AT_ONCE.search(nm)) or bool(PREPAY.search(nm))
        if wants_once and not WHOLESALE_WORD.search(nm):
            return PolicyAnswer(True, KIND_BULK_ONCE, "all_at_once", BULK_ONCE_REPLY)
        if wants_once and re.search(r"(?:بعث|ارسل|ابعث|envoy|d un coup|en une)", nm):
            return PolicyAnswer(True, KIND_BULK_ONCE, "all_at_once", BULK_ONCE_REPLY)
        return PolicyAnswer(True, KIND_WHOLESALE, "wholesale", WHOLESALE_REPLY)

    return PolicyAnswer(False, reason="no_policy_intent")
