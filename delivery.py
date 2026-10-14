# -*- coding: utf-8 -*-
"""Local delivery-price engine for the Mayna bot (Arabic / Darija / French).

Pipeline (see answer()):
  1. normalize the text (Arabic letters, digits, accents, elongation)
  2. decide whether it is a *delivery price* question (not duration / companies / tracking)
  3. extract the wilaya(s) with a synonym dictionary (+ prefix handling and a careful typo fallback)
  4. look the wilaya up in delivery_prices.json (the single source of truth)
  5. build the text reply (home price / office price / both)

No network, no Gemini: a price that exists in the table is always answered from the table.
"""
import difflib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from matcher import COMM, normalize

logger = logging.getLogger("mayna-assistant")

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delivery_prices.json")
CHANNEL_LINK = "https://t.me/+wyKej2q0oK0zYjI0"
UNCONFIRMED = 9999  # the table uses 9999 for "price must be confirmed by the admin"
EXPECTED_WILAYAS = 58

FOOTER = "\n\nللاطلاع على شروحات ومعلومات أخرى، ادخل لقناة Mayna:\n" + CHANNEL_LINK
ASK_WILAYA = (
    "واش هي الولاية تاعك؟ اكتب اسمها باش نعطيك سعر التوصيل.\n"
    "مثال: شحال التوصيل لوهران؟"
)
UNCONFIRMED_TEXT = "السعر يحتاج إلى تأكيد من الإدارة"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Wilaya:
    number: int
    name: str
    home: int
    office: int
    aliases: Tuple[str, ...] = ()


def load_wilayas(path: str = DATA_FILE) -> List[Wilaya]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)["wilayas"]
    wilayas = [
        Wilaya(int(r["number"]), r["name"], int(r["home"]), int(r["office"]), tuple(r.get("aliases", ())))
        for r in raw
    ]
    numbers = [w.number for w in wilayas]
    if len(wilayas) != EXPECTED_WILAYAS or sorted(numbers) != list(range(1, EXPECTED_WILAYAS + 1)):
        raise RuntimeError(f"delivery_prices.json must contain wilayas 1..{EXPECTED_WILAYAS} exactly once")
    return wilayas


WILAYAS: List[Wilaya] = load_wilayas()
BY_NUMBER: Dict[int, Wilaya] = {w.number: w for w in WILAYAS}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
def _drop_al(tok: str) -> str:
    """Drop the Arabic definite article 'ال' (same rule as matcher.normalize_for_match)."""
    return tok[2:] if tok.startswith("ال") and tok != "الله" and len(tok) - 2 >= 3 else tok


def _words(text: str) -> List[str]:
    return [_drop_al(t) for t in normalize(text).split()]


_PREFIXES = ("و", "ف", "ب", "ل", "ك")


def _variants(tok: str) -> List[str]:
    """Token forms to try: the token itself and with attached one-letter prefixes removed
    (لوهران، بوهران، وبوهران، للجزائر = ل + الجزائر)."""
    seen: List[str] = []

    def add(t: str) -> None:
        if t and t not in seen:
            seen.append(t)

    add(tok)
    add(_drop_al(tok))
    current = [tok]
    for _ in range(2):  # up to two stacked prefixes (وب، ول، فل)
        following = []
        for t in current:
            if t.startswith("لل") and len(t) > 4:
                add(t[2:])
                following.append(t[2:])
            if t[:1] in _PREFIXES and len(t) > 2:  # «لأم» -> normalized «لام» (3 letters)
                rest = t[1:]
                add(rest)
                add(_drop_al(rest))
                following.append(rest)
        current = following
    return seen


def _build_index() -> Tuple[Dict[Tuple[str, ...], int], Dict[str, int]]:
    index: Dict[Tuple[str, ...], int] = {}
    fuzzy: Dict[str, int] = {}
    for w in WILAYAS:
        for alias in (w.name,) + w.aliases:
            key = tuple(_words(alias))
            if not key:
                continue
            owner = index.setdefault(key, w.number)
            if owner != w.number:
                raise RuntimeError(f"alias {alias!r} belongs to two wilayas ({owner}, {w.number})")
            compact = "".join(key)
            if len(compact) >= 4:
                fuzzy.setdefault(compact, w.number)
    return index, fuzzy


_INDEX, _FUZZY = _build_index()
_MAX_NGRAM = max(len(k) for k in _INDEX)
_CAPITAL_BARE = tuple(_words("الجزائر"))  # bare "الجزائر" = capital, but also the country name

# Words of the question itself: never treated as a misspelled wilaya.
_VOCAB = set(
    "توصيل ليفريزون ليفراسيون شحال قداش قداه سعر اسعار ثمن تكلفه حق مكتب للمكتب دار للدار بيت للبيت "
    "منزل للمنزل جدول ولايه ولايات ولايتي ولايتك تاعي تاعك تاعنا نحب نعرف حاب ابعثلي ابعث ارسل "
    "livraison prix tarif tarifs combien coute frais domicile bureau stopdesk tableau liste "
    "price delivery wilaya wilayas toutes tous pour dans chez moi".split()
)


def find_wilayas(text: str) -> List[Tuple[int, Tuple[str, ...], bool]]:
    """Return [(wilaya number, matched key, fuzzy?)] in order of appearance, no duplicates."""
    words = _words(text)
    found: List[Tuple[int, Tuple[str, ...], bool]] = []
    seen = set()
    i = 0
    while i < len(words):
        hit = None
        for n in range(min(_MAX_NGRAM, len(words) - i), 0, -1):
            tail = tuple(words[i + 1:i + n])
            for first in _variants(words[i]):
                key = (first,) + tail
                if key in _INDEX:
                    hit = (_INDEX[key], key, n)
                    break
            if hit:
                break
        if hit:
            number, key, n = hit
            if number not in seen:
                seen.add(number)
                found.append((number, key, False))
            i += n
        else:
            i += 1
    if found:
        return found
    # Typo fallback: only when nothing matched exactly, only for words that are not part of
    # the question vocabulary, and only for a close, unambiguous match.
    for word in words:
        if len(word) < 4 or word in _VOCAB or word.isdigit():
            continue
        for var in _variants(word):
            if len(var) < 4 or var in _VOCAB:
                continue
            close = difflib.get_close_matches(var, list(_FUZZY), n=2, cutoff=0.84)
            numbers = {_FUZZY[c] for c in close}
            if len(numbers) == 1:
                number = numbers.pop()
                if number not in seen:
                    seen.add(number)
                    found.append((number, (var,), True))
                break
    return found


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------
def _nm(text: str) -> str:
    """Normalized text with 'ال' removed from every token (patterns below rely on that)."""
    return " ".join(_words(text))


_P = r"[لبوف]?"  # one-letter Arabic prefix
DELIV = re.compile(
    rf"(?<!\w){_P}(?:توصيل\w*|ليفريزون\w*|ليفراسيون\w*|ليفري\w*|livraison\w*|livrer|livre\w*|"
    r"شحن\w*|expedition\w*|shipping|delivery|tawsil|livrezon)(?!\w)"
)
STRONG_PRICE = re.compile(
    rf"(?<!\w){_P}(?:سعر\w*|اسعار|ثمن\w*|تكلف\w*|تكاليف|مصاريف|حق|حقوق|prix|tarifs?|tarification|"
    r"frais|couts?|coute\w*|price|pricing)(?!\w)"
)
WEAK_PRICE = re.compile(
    rf"(?<!\w)[ب]?(?:شحال|قداه|قداش|قدش|كم|combien|chhal|chhel|9adach|9deh|kadach|kdach)(?!\w)"
)
HOME = re.compile(
    rf"(?<!\w)(?:لل|{_P})?(?:دار|بيت|منزل)(?!\w)|(?<!\w)(?:domicile|chez moi|a la maison|home|porte a porte)(?!\w)"
)
OFFICE = re.compile(
    rf"(?<!\w)(?:لل|{_P})?(?:مكتب|مكاتب|بيرو)(?!\w)|(?<!\w)(?:bureau|bureaux|stop ?desk|agence|point relais|office|pickup)(?!\w)"
)
TABLE = re.compile(
    rf"(?<!\w)(?:لل|{_P})?(?:جدول|tableau|liste|grille|ولايات|wilayas|toutes|tous|جميع|كامل)(?!\w)|(?<!\w)58(?!\w)|كل ولاي"
)

DURATION = re.compile(
    rf"(?<!\w){_P}(?:مده|مدت\w*|وقتاش|وقتاه|امتي|متي|ايام|يوم|يومين|اسبوع|ساعه|ساعات|delai\w*|jours?|"
    r"duree|temps|heures?|quand|wa9tach|waqtach|تستغرق|يستغرق|استغرق|"
    r"تاخذ|تاخد|ياخذ|ياخد|تقعد|يقعد|تدوم|يدوم|prend|prennent|arrive|arrivent|تصل|يصل|توصل|يوصل)(?!\w)"
)
COMPANY = re.compile(
    r"(?<!\w)(?:شركات|شركه|societes?|transporteurs?|livreurs?|partenaires?|yalidine|yalidin|ياليدين|"
    r"noest|نوست|zr ?express|ecotrack|maystro|procolis|ناقل\w*)(?!\w)"
    r"|(?<!\w)(?:شكون|qui)\W+(?:\w+\W+){0,3}(?:يوصل\w*|يدي|livre\w*|تتعامل\w*)"
)
TRACKING = re.compile(r"(?<!\w)(?:تتبع|نتبع|suivi|suivre|tracking|track)(?!\w)|وين وصل|ou est|ou en est")
_COMM = re.compile(COMM)


@dataclass
class DeliveryAnswer:
    handled: bool
    reason: str
    text: str = ""
    kind: str = ""  # "wilaya" | "table" | "ask_wilaya" | ""
    wilayas: List[str] = field(default_factory=list)
    show: str = "both"  # "both" | "home" | "office"
    fuzzy: bool = False


def _skip(reason: str) -> DeliveryAnswer:
    return DeliveryAnswer(False, reason)


def _price_value(value: int) -> str:
    return UNCONFIRMED_TEXT if value == UNCONFIRMED else f"{value} دج"


def format_wilaya(w: Wilaya, show: str = "both", fuzzy: bool = False) -> str:
    rows = []
    if show in ("both", "home"):
        rows.append(("التوصيل للبيت", w.home))
    if show in ("both", "office"):
        rows.append(("مكتب التوصيل", w.office))
    if all(v == UNCONFIRMED for _, v in rows):
        head = f"فهمت أنك تقصد {w.name}.\n" if fuzzy else ""
        return (
            f"{head}سعر التوصيل إلى {w.name} يحتاج إلى تأكيد من الإدارة حاليا، "
            "وما نقدرش نعطيك سعر مؤكد. تواصل مع المشرفين باش يأكدولك السعر."
        )
    head = f"فهمت أنك تقصد {w.name}.\n" if fuzzy else ""
    lines = "\n".join(f"- {label}: {_price_value(v)}" for label, v in rows)
    return f"{head}أسعار التوصيل إلى {w.name} حسب جدول Mayna:\n{lines}"


def format_table() -> str:
    lines = [f"{w.number}. {w.name}: بيت {_cell(w.home)} | مكتب {_cell(w.office)}" for w in WILAYAS]
    return (
        "أسعار التوصيل للولايات الـ58 حسب جدول Mayna (بالدينار):\n\n"
        + "\n".join(lines)
        + "\n\nالولايات المكتوب فيها «يحتاج تأكيد» سعرها يحتاج إلى تأكيد من الإدارة."
    )


def _cell(value: int) -> str:
    return "يحتاج تأكيد" if value == UNCONFIRMED else str(value)


def answer(text: str) -> DeliveryAnswer:
    """Full pipeline. handled=False means 'not a delivery-price question' (caller continues)."""
    nm = _nm(text)
    if not nm:
        return _skip("empty")

    # Other delivery topics must never return prices.
    if DURATION.search(nm):
        return _skip("duration_question")
    if COMPANY.search(nm):
        return _skip("companies_question")
    if TRACKING.search(nm):
        return _skip("tracking_question")
    if _COMM.search(nm):
        return _skip("commission_question")

    has_deliv = bool(DELIV.search(nm))
    has_strong = bool(STRONG_PRICE.search(nm))
    has_weak = bool(WEAK_PRICE.search(nm))
    has_home = bool(HOME.search(nm))
    has_office = bool(OFFICE.search(nm))
    has_table = bool(TABLE.search(nm))

    found = find_wilayas(text)

    price_word = has_strong or has_weak
    is_price = False
    if price_word and has_deliv:
        is_price = True
    elif price_word and (has_home or has_office) and found:
        is_price = True  # «وهران للدار شحال؟» / «شحال للمكتب في وهران؟»
    elif has_deliv and has_table and re.search(r"جدول|tableau|liste|grille", nm):
        is_price = True  # «ابعثلي جدول التوصيل»
    if not is_price:
        return _skip("no_price_intent")

    show = "both"
    if has_home and not has_office:
        show = "home"
    elif has_office and not has_home:
        show = "office"

    # «الجزائر» alone together with a plural/«all» word means the country: send the table.
    if found and all(key == _CAPITAL_BARE for _, key, _ in found) and has_table:
        found = []

    if not found:
        if has_table:
            return DeliveryAnswer(True, "table_request", format_table() + FOOTER, "table")
        return DeliveryAnswer(True, "wilaya_missing", ASK_WILAYA, "ask_wilaya")

    chosen = found[:3]
    blocks = [format_wilaya(BY_NUMBER[n], show, fuzzy) for n, _, fuzzy in chosen]
    body = "\n\n".join(blocks)
    if len(found) > len(chosen):
        body += "\n\nاكتب باقي الولايات في سؤال آخر باش نعطيك أسعارها."
    return DeliveryAnswer(
        True,
        "wilaya_found",
        body + FOOTER,
        "wilaya",
        [BY_NUMBER[n].name for n, _, _ in chosen],
        show,
        any(f for _, _, f in chosen),
    )
