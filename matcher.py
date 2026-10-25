"""Local intent matcher for Mayna questions (Arabic / Algerian Darija / French / mixed).

Scores every topic with weighted regex signals over a normalized text, then
decides: confident match, ambiguous (several close topics) or unknown.
No network access; Gemini is only an optional fallback handled in bot.py.
"""
import re
import unicodedata
from dataclasses import dataclass, field

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_LETTER_MAP = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ة": "ه", "ؤ": "و",
        "ڤ": "ف", "ݣ": "ك", "گ": "ك", "پ": "ب", "ڨ": "ق",
    }
)


def normalize(text: str) -> str:
    text = (text or "").translate(_ARABIC_DIGITS).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ـ", "").replace("œ", "oe").replace("'", " ").replace("’", " ")
    text = text.translate(_LETTER_MAP)
    # elongation: كيفااااش -> كيفاش (3+ repeats -> 1)
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    # keep letters (any script) and digits, everything else -> space
    text = re.sub(r"[^\w\s]|_", " ", text)
    return re.sub(r"\s+", " ", text).strip()


WILAYAS = {
    "ادرار": "أدرار", "adrar": "أدرار", "الشلف": "الشلف", "chlef": "الشلف",
    "الاغواط": "الأغواط", "laghouat": "الأغواط", "ام البواقي": "أم البواقي",
    "oum el bouaghi": "أم البواقي", "باتنه": "باتنة", "batna": "باتنة",
    "بجايه": "بجاية", "bejaia": "بجاية", "bgayet": "بجاية", "بسكره": "بسكرة",
    "biskra": "بسكرة", "بشار": "بشار", "bechar": "بشار", "البليده": "البليدة",
    "blida": "البليدة", "البويره": "البويرة", "bouira": "البويرة",
    "تمنراست": "تمنراست", "tamanrasset": "تمنراست", "تبسه": "تبسة", "tebessa": "تبسة",
    "تلمسان": "تلمسان", "tlemcen": "تلمسان", "تيارت": "تيارت", "tiaret": "تيارت",
    "تيزي وزو": "تيزي وزو", "tizi ouzou": "تيزي وزو", "الجزائر العاصمه": "الجزائر",
    "alger": "الجزائر", "الجلفه": "الجلفة", "djelfa": "الجلفة", "جيجل": "جيجل",
    "jijel": "جيجل", "سطيف": "سطيف", "setif": "سطيف", "سعيده": "سعيدة", "saida": "سعيدة",
    "سكيكده": "سكيكدة", "skikda": "سكيكدة", "سيدي بلعباس": "سيدي بلعباس",
    "sidi bel abbes": "سيدي بلعباس", "عنابه": "عنابة", "annaba": "عنابة",
    "قالمه": "قالمة", "guelma": "قالمة", "قسنطينه": "قسنطينة", "constantine": "قسنطينة",
    "المديه": "المدية", "medea": "المدية", "مستغانم": "مستغانم", "mostaganem": "مستغانم",
    "المسيله": "المسيلة", "msila": "المسيلة", "معسكر": "معسكر", "mascara": "معسكر",
    "ورقله": "ورقلة", "ouargla": "ورقلة", "وهران": "وهران", "oran": "وهران",
    "البيض": "البيض", "el bayadh": "البيض", "اليزي": "إليزي", "illizi": "إليزي",
    "برج بوعريريج": "برج بوعريريج", "bba": "برج بوعريريج", "بومرداس": "بومرداس",
    "boumerdes": "بومرداس", "الطارف": "الطارف", "el tarf": "الطارف", "تندوف": "تندوف",
    "tindouf": "تندوف", "تيسمسيلت": "تيسمسيلت", "tissemsilt": "تيسمسيلت",
    "الوادي": "الوادي", "el oued": "الوادي", "خنشله": "خنشلة", "khenchela": "خنشلة",
    "سوق اهراس": "سوق أهراس", "souk ahras": "سوق أهراس", "تيبازه": "تيبازة",
    "tipaza": "تيبازة", "ميله": "ميلة", "mila": "ميلة", "عين الدفلي": "عين الدفلى",
    "ain defla": "عين الدفلى", "النعامه": "النعامة", "naama": "النعامة",
    "عين تموشنت": "عين تموشنت", "ain temouchent": "عين تموشنت", "غرداييه": "غرداية",
    "ghardaia": "غرداية", "غليزان": "غليزان", "relizane": "غليزان",
}


_AL_KEEP = {"الله"}


def normalize_for_match(text: str) -> str:
    """normalize() + drop the Arabic definite article 'ال' from each token."""
    out = []
    for tok in normalize(text).split():
        if tok.startswith("ال") and tok not in _AL_KEEP and len(tok) - 2 >= 3:
            tok = tok[2:]
        out.append(tok)
    return " ".join(out)


def extract_wilaya(norm_text: str):
    padded = f" {norm_text} "
    for key in sorted(WILAYAS, key=len, reverse=True):
        # accept Arabic one-letter prefixes: لوهران، بوهران، في وهران
        if re.search(rf"(?<![\w]){'(?:ل|ب|و|ف)?'}{re.escape(key)}(?![\w])", padded):
            return WILAYAS[key]
    return None


# ---------------------------------------------------------------------------
# Signal vocabulary (all patterns are matched on normalized text)
# ---------------------------------------------------------------------------
COMM = r"(?:عمول\w*|ارباح|ربح|commission\w*|gains?|comision\w*|3omoula)"
MONEY = r"(?:دراهم\w*|فلوس\w*|مستحقات\w*|رصيد\w*|argent|solde|sous|gains?|money|دينار\w*)"
DELIV = r"(?:توصيل\w*|ليفريزون\w*|ليفراسيون\w*|شحن\w*|livraison\w*|livrer|livre\w*|expedition\w*|envoi|shipping|tawsil|livrezon)"
ORDER = r"(?:طلبي\w*|طلب\w*|كوموند\w*|commande\w*|colis|كولي|طرد\w*|شحنه|شحنات|بضاعه|order|commande)"
PRICE = r"(?:سعر\w*|اسعار\w*|ثمن\w*|تكلف\w*|حق|تاع|قداه|قداش|شحال|كم|prix|tarif\w*|frais|combien(?! de (?:jours|temps))|cout\w*|coute\w*|price|chhal|9adach)"
TIMEW = r"(?:مده|مدت\w*|وقتاش|وقتاه|امتي|متي|ايام|يوم|اسبوع|delai\w*|jours?|quand|durée|duree|temps|wa9tach|waqtach|ساعه|ساعات|sa3a|heures?)"
TIMES = r"(?:مده|مدت\w*|وقتاش|وقتاه|امتي|متي|delai\w*|quand|durée|duree|wa9tach|waqtach)"
TAKE = r"(?:تاخذ|ياخذ|تاخد|تستغرق|يحتاج|تحتاج|تقعد|تدوم|توصل|يوصل|توصلني|تصل|يصل|prend\w*|arrive\w*|mettre|met)"

# Each rule: (regex, weight).  Weights express how specific a signal is.
RULES = {
    "withdraw_commission": [
        (rf"(?:سحب|نسحب|تسحب|نسحبو|سحبت|retir\w*|retrait\w*|withdraw|nsa7ab|nsahab|رتيري)\W+(?:\w+\W+){{0,3}}(?:{COMM}|{MONEY}|الارباح)", 8),
        (rf"(?:{COMM}|{MONEY}).{{0,25}}(?:نسحب|نسحبو|سحب|retir\w*|retrait)", 7),
        (r"(?:كيفاش|كيف|كيفاه|comment|kifach|kifah)\W+(?:\w+\W+)?(?:نسحب|نسحبو|نخرج|retire\w*)", 7),
        (rf"(?:نخرج|اخراج|تحويل|استلام|نستلم|نقبض|قبض)\W+(?:\w+\W+){{0,2}}(?:{COMM}|{MONEY})", 6),
        (r"(?:وين|فين|win)\W+(?:\w+\W+){0,2}(?:نلقي|نلقى|نلقا|راهي|راه|نلقاو|تلقي)\W+(?:\w+\W+){0,2}(?:دراهمي|فلوسي|رصيدي|عمولتي|ارباحي)", 7),
        (rf"(?:نطلع|نجيب|نحول|نستلم|نستخرج|نستخلص|نقدر نجيب)\W+(?:\w+\W+){{0,3}}(?:{COMM}|{MONEY}|ربح\w*|ربحت\w*)", 7),
        (r"\b(?:نسحب|نسحبو|نسحبها|سحب)\b", 4),
        (r"(?:retirer|retrait)\b", 4),
    ],
    "commission_payment_days": [
        (rf"(?:{TIMEW})\W+(?:\w+\W+){{0,3}}(?:نخلص\w*|تخلص\w*|نقبض|يخلصو\w*|يدفعو\w*|تدفع\w*|الدفع|دفع\w*|تدخل\w*|ندخل\w*|تصل\w*|تتحول)", 8),
        (rf"(?:{TIMEW})\W+(?:\w+\W+){{0,3}}(?:{COMM}|{MONEY})", 7),
        (rf"(?:{COMM}|{MONEY}).{{0,25}}(?:{TIMEW})", 6),
        (rf"(?:{COMM}|{MONEY})\W+(?:\w+\W+){{0,2}}(?:تقعد|تاخذ|تدخل|تصل|تاخر\w*|تتاخر)", 7),
        (rf"(?:شحال|قداه|قداش|كم)\W+(?:\w+\W+){{0,2}}(?:تقعد|تاخذ|تدوم|يوم|ايام)\W+(?:\w+\W+){{0,3}}(?:{COMM}|{MONEY})", 8),
        (rf"(?:علاش|لماذا|pourquoi|3lach)\W+(?:\w+\W+){{0,3}}(?:وصلت|وصلتش|وصل|دخلت|دخلتش|recu|recue|recois)\W+(?:\w+\W+){{0,2}}(?:{COMM}|{MONEY})", 8),
        (rf"(?:ما|ماشي|لم|pas)\W+(?:\w+\W+){{0,2}}(?:وصلتش|دخلتش|وصلت|دخلت|recu|recue)\W+(?:\w+\W+){{0,2}}(?:{COMM}|{MONEY})", 7),
        (rf"(?:{COMM}|{MONEY})\W+(?:\w+\W+){{0,3}}(?:ما|لم)\W*(?:وصلتش|دخلتش|وصلت|دخلت)", 7),
        (r"(?:quand|when)\W+(?:\w+\W+){0,4}(?:recois|recevoir|paye|payee|payees|payer|paiement|paid|touche|toucher)", 8),
        (rf"(?:{TIMEW})\W+(?:\w+\W+){{0,3}}(?:\w*وصل\w*|تدخل\w*)\W+(?:\w+\W+){{0,2}}(?:{COMM}|{MONEY})", 10),
        (rf"(?:هل|wach|واش)\W+(?:\w+\W+){{0,2}}(?:{COMM})\W+(?:\w+\W+){{0,2}}(?:تدفع|تدفعو|تخلص|تتدفع)\W+(?:\w+\W+){{0,2}}(?:اسبوع|شهر|يوم|semaine|mois|jour)", 9),
        (rf"(?:كل|chaque)\W+(?:\w+\W+){{0,1}}(?:اسبوع|شهر|semaine|mois)\W+(?:\w+\W+){{0,3}}(?:تدفع\w*|تخلص\w*|paye\w*|paiement)", 9),
        (r"(?:نخلصو|نخلص|نقبضو)\b", 5),
        (r"(?:ايام|jour|jours)\W+(?:\w+\W+){0,2}(?:دفع|paiement|paye)", 7),
        (r"(?:paiement|paiements)\W+(?:\w+\W+){0,2}commission", 7),
    ],
    "new_order_commission": [
        (rf"(?:تسجيل|نسجل|نسجلو|سجل|ندخل|ندير|نزيد|اضافه|enregistr\w*|ajout\w*|passer|creer|saisir)\W+(?:\w+\W+){{0,2}}(?:{ORDER})", 8),
        (r"(?:طلبي\w*|طلب|كوموند\w*|commande)\W+(?:\w+\W+){0,1}(?:جديد\w*|nouvelle)", 8),
        (r"(?:nouvelle|new)\W+(?:commande|order)", 8),
        (rf"(?:احتساب|حساب|نحسب|تحسب|calcul\w*|combien)\W+(?:\w+\W+){{0,2}}{COMM}", 8),
        (rf"(?:شحال|قداه|قداش|كم|combien)\W+(?:\w+\W+){{0,2}}(?:{COMM})\W+(?:\w+\W+){{0,3}}(?:طلب\w*|كوموند\w*|commande|منتج|produit|قطعه|واحد)", 8),
        (rf"(?:{COMM})\W+(?:\w+\W+){{0,2}}(?:تاع|على|عن|par|sur)\W+(?:\w+\W+){{0,2}}(?:{ORDER}|منتج|produit)", 6),
        (r"(?:عمولتي|العمولات? تاعي)", 3),
    ],
    "delivery_prices_58_wilayas": [
        (rf"(?:{PRICE})\W+(?:\w+\W+){{0,3}}(?:{DELIV})", 8),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,4}}(?:{PRICE})", 7),
        (rf"(?:{PRICE})\W+(?:\w+\W+){{0,3}}(?:{DELIV})\W+(?:\w+\W+){{0,3}}(?:ولايه|ولايات|wilaya|وهران|58)", 2),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,2}}(?:للدار|الدار|domicile|للمنزل)\W+(?:\w+\W+){{0,2}}(?:{PRICE})", 3),
        (r"(?:حق|حقوق)\W+(?:ال)?(?:توصيل|ليفريزون)", 8),
        (rf"(?:{PRICE})\W+(?:\w+\W+){{0,3}}(?:{DELIV})\W+(?:\w+\W+){{0,4}}(?:للدار|دار|للمنزل|منزل|domicile|للبلديه|بلديه)", 10),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,3}}(?:للدار|دار|للمنزل|منزل|domicile|للبلديه|بلديه)\W+(?:\w+\W+){{0,3}}(?:{PRICE})", 10),
        (rf"(?:نخلص|ندفع|payer|paye)\W+(?:\w+\W+){{0,2}}(?:علي|على|pour|sur)?\W*(?:{DELIV})", 8),
        (r"(?:اسعار|سعر|ثمن|tarifs?|prix|frais)\W+(?:\w+\W+){0,1}(?:ال)?(?:ولايات|wilayas?|58)", 5),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,3}}(?:58|ولايات|wilayas)", 4),
        (r"(?:coute|cout|combien)\W+(?:\w+\W+){0,3}(?:livraison)", 8),
        (r"\b(?:اسعار|سعر)\b\W+(?:ال)?(?:ليفريزون|توصيل)", 3),
    ],
    "delivery_duration_58_wilayas": [
        (rf"(?:{TIMES})\W+(?:\w+\W+){{0,3}}(?:{DELIV})", 9),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,4}}(?:{TIMES})", 7),
        (rf"(?:{DELIV}|{ORDER})\W+(?:\w+\W+){{0,4}}(?:combien de (?:jours|temps)|كم يوم|شحال من يوم|شحال يوم|كم ساعه)", 9),
        (rf"(?:combien de (?:jours|temps)|كم يوم|شحال من يوم|شحال يوم)\W+(?:\w+\W+){{0,4}}(?:{DELIV}|{ORDER})", 9),
        (r"(?:في|dans|en)\W+(?:\w+\W+){0,1}(?:24|48|72)\W*(?:ساعه|ساعات|h|heures?)", 6),
        (rf"(?:{ORDER})\W+(?:\w+\W+){{0,3}}(?:{TAKE})\W+(?:\w+\W+){{0,3}}(?:{TIMEW}|وقتاش|ايام|يوم)", 6),
        (rf"(?:{ORDER}|{DELIV})\W+(?:\w+\W+){{0,2}}(?:{TAKE})\W+(?:\w+\W+){{0,2}}(?:شحال|قداه|قداش|كم|combien)", 9),
        (rf"(?:شحال|قداه|قداش|كم|combien)\W+(?:\w+\W+){{0,2}}(?:يوم|ايام|jours?|ساعه|ساعات|heures?)\W+(?:\w+\W+){{0,3}}(?:{TAKE}|{DELIV}|{ORDER})", 9),
        (rf"(?:شحال|قداه|قداش|كم)\W+(?:\w+\W+){{0,2}}(?:تاخذ|تقعد|تستغرق|تدوم)\W+(?:\w+\W+){{0,3}}(?:{ORDER}|{DELIV})", 9),
        (rf"(?:وقتاش|امتي|متي|quand)\W+(?:\w+\W+){{0,3}}(?:\w*وصل\w*|يصل|تصل|arrive|livre|livree|recevoir|recois)", 9),
        (r"(?:delai|durée|duree)\W+(?:\w+\W+){0,3}(?:livraison|expedition|colis|commande)", 9),
        (r"(?:مدة|مده)\W+(?:ال)?(?:شحن|توصيل|وصول)", 9),
        (r"(?:quand|combien de (?:temps|jours))\W+(?:\w+\W+){0,4}(?:arrive|livre|recevoir|livraison|colis)", 8),
        (r"(?:كم|شحال)\W+(?:\w+\W+){0,2}(?:تستغرق|تاخذ|يستغرق)\W+(?:\w+\W+){0,2}(?:توصيل|شحن)", 9),
    ],
    "delivery_tracking": [
        (rf"(?:تتبع|نتبع|نتبعو|نتتبع|تتبعو|نراقب|نتابع|متابع\w*|suivi\w*|suivre|suiv\w*|track\w*|tracking|follow)\W+(?:\w+\W+){{0,3}}(?:{ORDER}|colis|كولي|شحنه|بضاعه|سلعه)", 9),
        (rf"(?:{ORDER}|colis|كولي)\W+(?:\w+\W+){{0,3}}(?:تتبع|نتبع|suivi|suivre|tracking)", 8),
        (rf"(?:وين|فين|ou|win)\W+(?:\w+\W+){{0,2}}(?:وصلت|راهي|راه|رواح|وصل|est|se trouve|هي)\W+(?:\w+\W+){{0,3}}(?:{ORDER}|colis|كولي|شحنه|سلعه|بضاعه)", 9),
        (rf"(?:{ORDER}|colis|كولي)\W+(?:\w+\W+){{0,3}}(?:وين|فين|وصلت|راهي|راه|رواح|واش صرا|صرا|ou est|ou se trouve)", 8),
        (rf"(?:واش|شنو|ماذا)\W+(?:\w+\W+){{0,2}}(?:صرا|حصل|صار)\W+(?:\w+\W+){{0,2}}(?:{ORDER})", 8),
        (r"(?:ou|où)\W+(?:est|se trouve)\W+(?:\w+\W+){0,3}(?:colis|commande)", 9),
        (r"(?:رقم|lien|رابط|موقع|site)\W+(?:ال)?(?:تتبع|suivi|tracking)", 8),
        (rf"(?:نعرف|نشوف|نتاكد|نعلم)\W+(?:\w+\W+){{0,3}}(?:وين|فين)\W+(?:\w+\W+){{0,3}}(?:{ORDER}|كولي|colis)", 9),
        (rf"(?:نشوف|نعرف|شوف|نتاكد|نطلع علي)\W+(?:\w+\W+){{0,2}}(?:حال\w*|statut|etat|وضع\w*|موقع|مكان|position|emplacement|localisation)\W+(?:\w+\W+){{0,2}}(?:{ORDER}|colis|كولي)", 9),
        (r"(?:ou en est|ou est|ou se trouve|est ou|se trouve ou)\W+(?:\w+\W+){0,3}(?:colis|commande)", 9),
        (r"(?:colis|commande)\W+(?:\w+\W+){0,3}(?:ou en est|ou est|ou se trouve|est ou|se trouve ou)\b", 9),
        (r"\b(?:vitrans|فيترانس)\b", 5),
    ],
    "order_management_status": [
        (rf"(?:تعديل|نعدل|نبدل|تغيير|نغير|modifier|changer)\W+(?:\w+\W+){{0,2}}(?:{ORDER})", 8),
        (rf"(?:الغاء|نلغي|نلغو|الغي|annul\w*)\W+(?:\w+\W+){{0,2}}(?:{ORDER})", 8),
        (rf"(?:حال\w*|statut|etat|مراحل)\W+(?:\w+\W+){{0,2}}(?:{ORDER})", 7),
        (rf"(?:{ORDER})\W+(?:\w+\W+){{0,2}}(?:ملغيه|ملغاه|مرفوضه|annulee|refusee)", 6),
        (r"(?:سبب)\W+(?:ال)?(?:الغاء|رفض)", 7),
        (r"(?:في طور التسليم|طور التسليم)", 7),
    ],
    "registration": [
        (r"(?:كيفاش|كيف|كيفاه|comment|kifach|kifah)\W+(?:\w+\W+){0,2}(?:نسجل|نسجلو|نفتح|ندير|نولي|نبدا|نخدم|ندخل|inscri\w*|devenir|creer|ouvrir)\W+(?:\w+\W+){0,3}(?:حساب|inscription|compte|مسوق|ماينا|mayna|marketeur|affilie|vendeur)?", 5),
        (r"(?:طريقه|كيفيه|شرح|فيديو|خطوات)\W+(?:ال)?(?:تسجيل|inscription)(?!\W+(?:ال)?(?:طلب|كوموند|commande))", 8),
        (r"(?:انضمام|انضم|ننضم|join\w*|rejoindre|integrer)\W+(?:\w+\W+){0,3}(?:ماينا|mayna|مسوق|marketeur|affilie|فريق)", 9),
        (r"(?:inscri\w*)\W+(?:\w+\W+){0,3}(?:affilie|marketeur|vendeur|revendeur|compte)", 9),
        (r"(?:ندير|نعمل|نفتح|ouvrir|faire)\W+(?:\w+\W+){0,1}(?:compte|حساب)", 9),
        (r"(?:خطوه|خطوات|etapes?|premiere etape)\W+(?:\w+\W+){0,3}(?:نبدا|نبدو|نخدم|commencer|debuter)\W+(?:\w+\W+){0,3}(?:ماينا|mayna)", 9),
        (r"(?:نبدا|نبدو|commencer|debuter)\W+(?:\w+\W+){0,2}(?:مع|avec|في|ف)?\W*(?:ماينا|mayna)", 8),
        (r"(?:نفتح|فتح|ننشي|انشاء|creer|ouvrir|open)\W+(?:\w+\W+){0,2}(?:حساب|compte|account)", 9),
        (r"(?:inscription|inscrire|s inscrire|sinscrire|register|registration|تسجيل|نسجل)\W*(?:\w+\W+){0,3}(?:mayna|ماينا|مسوق|حساب|compte|site|موقع)", 9),
        (r"(?:ندير|نعمل|نديرو|faire|faire une)\W+(?:\w+\W+){0,1}(?:inscription|تسجيل)", 9),
        (r"(?:نولي|devenir|become)\W+(?:\w+\W+){0,2}(?:مسوق|marketeur|affilie|vendeur|revendeur)", 9),
        (r"(?:كيفاش|كيف|كيفاه)\W+(?:\w+\W+){0,1}(?:نسجل|نسجلو)\W*(?:في|ف|فى)?\W*(?:ماينا|mayna)", 9),
        (r"(?:حاب|حبيت|نحب|ودي|بغيت)\W+(?:\w+\W+){0,2}(?:نسجل|نبدا|نخدم|ندخل)", 8),
        (r"(?:راني|انا|je suis)\W+(?:جديد\w*|nouveau|nouvelle)", 7),
        (r"(?:كيفاش|كيف|كيفاه|comment)\W+(?:\w+\W+){0,2}(?:نبدا|نخدم)\W+(?:\w+\W+){0,2}(?:ماينا|mayna|تسويق|marketing)", 8),
        (r"(?:s inscrire|inscription)\W+(?:\w+\W+){0,3}(?:mayna|ماينا)", 3),
        # bare questions in the marketers' group: "كيفاش نسجل" / "كيفاش نبدا" mean registration
        (rf"(?:كيفاش|كيف|كيفاه|kifach|kifah)\W+(?:نسجل|نسجلو)(?!\W+(?:{ORDER}))", 9),
        (r"(?:كيفاش|كيف|كيفاه|kifach|kifah)\W+(?:نبدا|نبدو)\W*$", 8),
    ],
    "order_confirmation_times": [
        (rf"(?:تاكيد|تتاكد|تتأكد|يتاكد|نتاكد|يتم تاكيد|confirm\w*)\W+(?:\w+\W+){{0,3}}(?:{ORDER}|{ORDER}\w*)", 8),
        (rf"(?:{ORDER})\W+(?:\w+\W+){{0,3}}(?:تتاكد|تتأكد|تاكيد|يتاكد|confirm\w*)", 8),
        (r"(?:وقتاش|امتي|متي|quand|شحال|combien)\W+(?:\w+\W+){0,4}(?:يتصلو|يتصلوا|يتصل|اتصال|يكلمو|appel\w*|contact\w*|call)\W+(?:\w+\W+){0,3}(?:الزبون|client|clients|زبون)", 9),
        (r"(?:يتصلو|يتصلوا|يتصل|appel\w*)\W+(?:\w+\W+){0,3}(?:بالزبون|الزبون|client)", 7),
        (r"(?:زبون|client)\W+(?:\w+\W+){0,3}(?:وقتاش|امتي|متي|quand)\W+(?:\w+\W+){0,3}(?:يتصل\w*|يكلم\w*|appel\w*)", 9),
        (r"(?:quand|وقتاش|امتي|متي)\W+(?:\w+\W+){0,4}(?:client|زبون|بالزبون)\W+(?:\w+\W+){0,3}(?:appel\w*|contacte\w*|يتصل\w*)", 9),
        (r"(?:ا?وقات|اوقات|horaires?|heures?)\W+(?:\w+\W+){0,2}(?:تاكيد|confirmation)", 9),
        (r"confirmation\W+(?:\w+\W+){0,2}(?:commande|commandes)", 8),
    ],
    "exchange_warranty_policy": [
        (r"(?:استبدال|نبدل|نبدلو|تبديل|بدل|ترجيع|نرجع|نرجعو|استرجاع|استرداد|echang\w*|rembours\w*|retour\w*|retourner|renvoyer)", 7),
        (r"(?:ضمان|garantie|warranty|guarantee|ضمانه)", 8),
        (r"(?:عيب|معيب|فيه عيب|خراب|مكسور|defectu\w*|defaut|abime\w*|casse\w*|endommage\w*|ma tkhdemch)", 7),
        (r"(?:خاطئ|خاطي|غلط|غالط|erreur|mauvais|incorrect|مختلف)\W+(?:\w+\W+){0,2}(?:منتج|منتوج|سلعه|produit|مقاس|لون|taille)|(?:منتج|منتوج|سلعه|produit)\W+(?:\w+\W+){0,2}(?:خاطئ|خاطي|غلط|غالط|مختلف|incorrect|different)", 8),
        (r"(?:politique)\W+(?:\w+\W+){0,2}(?:echange|garantie|retour)", 9),
        (r"(?:reclamation|شكوي|شكايه|réclamation)", 8),
        (r"(?:منتوج|منتج|سلعه|produit)\W+(?:\w+\W+){0,3}(?:ما يخدمش|ما تخدمش|ما خدمش|مخرب|مكسر|defectueux|ne marche pas|marche pas)", 8),
    ],
    "delivery_companies": [
        (r"(?:شركات|شركه|societes?|entreprises?|compagnies?|transporteurs?|livreurs?|partenaires?|ناقل\w*)\W+(?:\w+\W+){0,2}(?:ال)?(?:توصيل|ليفريزون|ليفراسيون|livraison|ماينا)", 9),
        (r"(?:ال)?(?:توصيل|ليفريزون|livraison)\W+(?:\w+\W+){0,1}(?:شركات|شركه|societes?|transporteurs?)", 8),
        (r"(?:شكون|من|مع من|واش من|quels?|quelles?|qui|avec qui)\W+(?:\w+\W+){0,4}(?:يوصل|يوصلو|يدي|تتعامل\w*|تتعاملو|تخدمو|تخدم|livre|livrent|travaille\w*|partenaires?)", 7),
        (r"(?:noest|yalidine|yalidin|ياليدين|يا ليدين|نوست|zr express|zrexpress|ecotrack|maystro|procolis)", 6.5),
        (r"(?:transporteurs?)", 8),
    ],
    "municipality_home_delivery": [
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,2}}(?:للمنزل|للدار|الدار|المنزل|لدار|domicile|a domicile|chez moi|للبلديه|للبلديات|البلديه|لبلديتي)", 8),
        (rf"(?:{DELIV})\W+(?:\w+\W+){{0,2}}(?:à|a)\W+domicile", 8.5),
        (r"(?:بلديه|بلديات|بلديتي|commune|communes|دائره|daira)", 7),
        (r"(?:يوصلو|يوصل|توصل|livrent?|livre)\W+(?:\w+\W+){0,2}(?:للدار|للمنزل|الدار|domicile|chez)", 8),
        (r"(?:home|domicile)\W+(?:delivery|livraison)", 8),
        (r"(?:دار|منزل|بيت)\W+(?:\w+\W+){0,1}(?:يوصل\w*|توصيل|livre\w*)", 8),
    ],
    "customer_service_numbers": [
        (r"(?:رقم|ارقام|numero\w*|num|tel|telephone|هاتف|contact\w*)\W+(?:\w+\W+){0,2}(?:خدمه|service|دعم|support|ماينا|mayna|العملاء|clients?|اداره|admin)", 9),
        (r"(?:نتصل|نكلم|اتصل|كلم|contacter|appeler|joindre|call|join\w*)\W+(?:\w+\W+){0,3}(?:خدمه|service|دعم|support|ماينا|mayna|العملاء|clients?|اداره)", 9),
        (r"(?:service client|خدمه العملاء|الدعم)", 6),
    ],
    "marketplace_posting": [
        (r"(?:marketplace|ماركت ?بليس|ماركت بلايس|ماركتبلايس)", 9),
        (r"(?:ننشر|نشر|نحط|publier|poster)\W+(?:\w+\W+){0,3}(?:فيسبوك|فايسبوك|facebook|اعلان|annonce|منتج)", 7),
    ],
    "basket_feature": [
        (r"(?:السله|سله|panier|basket|cart)", 8),
    ],
    "google_lens_chatgpt_product_research": [
        (r"(?:google lens|غوغل لينس|جوجل لينس|لينس|lens|chat ?gpt|شات جي بي تي|شات جي بيتي)", 9),
        (r"(?:نبحث|البحث|نلقي)\W+(?:\w+\W+){0,2}(?:صوره|صور|image|photo)\W+(?:\w+\W+){0,2}(?:منتج|produit)", 7),
    ],
    "mayna_app_download_images_copy_text": [
        (r"(?:تحميل|نحمل|نزل|telecharger|download)\W+(?:\w+\W+){0,2}(?:صور|صوره|images?|photos?)", 9),
        (r"(?:نسخ|ننسخ|copier|copy)\W+(?:\w+\W+){0,2}(?:نص|النص|وصف|texte|description|معلومات)", 9),
        (r"(?:تطبيق|application|app)\W+(?:\w+\W+){0,2}(?:ماينا|mayna)", 6),
    ],
    "product_color_size_notes": [
        (r"(?:الوان|وان|لون|مقاس\w*|قياس\w*|couleurs?|tailles?|pointure|size|colors?)", 8),
    ],
}

# Questions that mention a delivery topic AND a person: when several delivery-ish
# topics tie, prefer the more specific topic below.
GREETING_PATTERNS = [
    r"^(?:ال)?سلام(?: عليكم| عليكم ورحمه الله(?: وبركاته)?)?$",
    r"^(?:assalam\w*|salam\w*|slm|salut|bonjour|bonsoir|coucou|hello|hi|hey|wa3alaykoum|واه|مرحبا|اهلا|هلا|صحا|صباح الخير|مساء الخير|صباح النور|مساء النور|سلام|السلام عليكم|سلام عليكم)(?: [\w]+){0,3}$",
]
_GREET_WORDS = (
    "سلام", "السلام", "عليكم", "مرحبا", "اهلا", "هلا", "صحا", "صباح", "مساء", "الخير", "النور",
    "salam", "slm", "salut", "bonjour", "bonsoir", "coucou", "hello", "hi", "hey", "assalamu", "alaykum",
    "alaikum", "wa3alaykoum", "ورحمه", "الله", "وبركاته", "صحه", "صحتك", "كيراك", "لاباس", "cv", "ça", "ca", "va",
    "عليك", "عليكي", "عليكما", "يا", "اخي", "خويا", "اخوي", "اختي", "خيي", "سيدي", "استاذ", "اهلين", "حياك", "حياكم", "مرحبتين", "تحيه", "طيبه", "نهارك", "نهاركم", "سعيد", "slt", "alaykoum", "alykoum", "3alaykoum", "alaykom", "salem", "salamo", "salamou", "cc", "khoya", "frere", "tout", "le", "monde", "للجميع", "جميعا", "اخواني", "خاوتي", "شباب", "الجماعه", "everyone", "كلكم", "بيكم",
)


def is_greeting(text: str) -> bool:
    """True only when the whole message is a greeting (no question inside)."""
    norm = normalize(text)
    if not norm:
        return False
    words = norm.split()
    if len(words) > 6:
        return False
    return all(w in _GREET_WORDS or (w.startswith('و') and w[1:] in _GREET_WORDS) for w in words)


@dataclass
class MatchResult:
    status: str  # "match" | "ambiguous" | "none"
    topic: str = ""
    score: float = 0.0
    scores: dict = field(default_factory=dict)
    candidates: list = field(default_factory=list)
    wilaya: str = ""


_COMPILED = {k: [(re.compile(p), w) for p, w in v] for k, v in RULES.items()}

MIN_SCORE = 6
MIN_MARGIN = 2


def score_topics(norm_text: str) -> dict:
    scores = {}
    for topic, rules in _COMPILED.items():
        best = 0
        extra = 0
        for rx, w in rules:
            if rx.search(norm_text):
                if w > best:
                    extra += best * 0.15
                    best = w
                else:
                    extra += w * 0.15
        total = best + min(extra, 2)
        if total:
            scores[topic] = round(total, 2)
    return scores


_MONEY_DOMAIN = re.compile(rf"(?:{COMM}|{MONEY})")
_PARCEL_DOMAIN = re.compile(rf"(?:{DELIV}|{ORDER}|colis|كولي)")
_COMM_TOPICS = ("withdraw_commission", "commission_payment_days")
_PARCEL_TOPICS = ("delivery_prices_58_wilayas", "delivery_duration_58_wilayas", "delivery_tracking",
                  "delivery_companies", "municipality_home_delivery", "order_confirmation_times")


_HINTS = [
    (re.compile(rf"(?:{COMM}|{MONEY})"), ["withdraw_commission", "commission_payment_days", "new_order_commission"]),
    (re.compile(rf"(?:{DELIV})"), ["delivery_prices_58_wilayas", "delivery_duration_58_wilayas", "delivery_companies"]),
    (re.compile(rf"(?:{ORDER})"), ["delivery_tracking", "order_confirmation_times", "new_order_commission"]),
]


def _domain_adjust(norm: str, scores: dict) -> dict:
    """If the message talks about money but not parcels (or vice versa), demote the other domain."""
    has_money = bool(_MONEY_DOMAIN.search(norm))
    has_parcel = bool(_PARCEL_DOMAIN.search(norm))
    out = dict(scores)
    if has_money and not has_parcel:
        for t in _PARCEL_TOPICS:
            if t in out:
                out[t] = round(out[t] * 0.6, 2)
    if has_parcel and not has_money:
        for t in _COMM_TOPICS:
            if t in out:
                out[t] = round(out[t] * 0.6, 2)
    return out


def classify(text: str) -> MatchResult:
    wilaya = extract_wilaya(normalize(text)) or ""
    norm = normalize_for_match(text)
    if not norm:
        return MatchResult("none")
    scores = _domain_adjust(norm, score_topics(norm))
    if not scores:
        # A bare topic noun ("العمولة", "التوصيل") is too vague to answer, but it is enough to
        # ask a useful clarifying question instead of silently escalating.
        hinted = []
        for rx, topics in _HINTS:
            if rx.search(norm):
                hinted.extend(t for t in topics if t not in hinted)
        if hinted:
            return MatchResult("ambiguous", scores={t: 3 for t in hinted}, candidates=hinted[:3], wilaya=wilaya)
        return MatchResult("none", wilaya=wilaya)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    cands = [t for t, _ in ranked[:3]]
    if top_score < MIN_SCORE:
        return MatchResult("ambiguous", scores=scores, candidates=cands, wilaya=wilaya)
    if top_score - second_score < MIN_MARGIN:
        return MatchResult("ambiguous", scores=scores, candidates=cands, wilaya=wilaya)
    return MatchResult("match", topic=top, score=top_score, scores=scores, candidates=cands, wilaya=wilaya)
