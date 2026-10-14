# -*- coding: utf-8 -*-
"""Fresh phrasings written AFTER tuning, to detect overfitting."""
HELDOUT = {
    "withdraw_commission": [
        "نحب نسحب ربحي واش لازم نديرو",
        "كيفاه نستلم عمولتي في الحساب تاعي",
        "طريقة تحويل الارباح لحسابي",
        "ana n7eb nsa7ab commission",
        "Je veux retirer mon argent gagné",
        "كيفاش نطلع الدراهم لي ربحتهم",
    ],
    "commission_payment_days": [
        "امتى بالضبط توصلني العمولة",
        "شحال من يوم باش يدخلو الدراهم",
        "هل العمولة تدفع كل اسبوع؟",
        "quand est-ce que vous payez les commissions",
        "كل شهر تدفعو العمولة ولا كل اسبوع؟",
    ],
    "delivery_prices_58_wilayas": [
        "قداه الليفريزون لتلمسان",
        "ابغي نعرف ثمن الشحن لورقلة",
        "كم تكلفة التوصيل الى باتنة",
        "c'est combien la livraison pour tizi ouzou",
        "جدول اسعار التوصيل للـ58 ولاية",
        "prix livraison oran domicile",
    ],
    "delivery_duration_58_wilayas": [
        "الكولي يوصل في كم يوم لعنابة",
        "كم يوم يحتاج الشحن؟",
        "livraison en combien de jours ?",
        "الطلبية توصل في 24 ساعة ولا اكثر",
        "شحال من يوم تدوم الليفريزون لجيجل",
        "durée de la livraison",
    ],
    "delivery_tracking": [
        "ممكن نعرف مكان الطلبية؟",
        "عندي رقم التتبع وين نحطو",
        "ou en est ma commande",
        "نبغي نتتبع الشحنة تاع الزبون",
        "كيفاش نراقب الكوموند تاعي",
        "le colis est où",
    ],
    "registration": [
        "كيف يمكنني الانضمام الى ماينا كمسوق",
        "نحب نخدم معاكم كيفاش نسجل",
        "je veux m'inscrire comme affilié",
        "كيفاش ندير compte",
        "اول خطوة باش نبدا مع ماينا",
    ],
    "order_confirmation_times": [
        "شحال من وقت باش تتاكد الكوموند",
        "الزبون وقتاش يتصلو بيه",
        "confirmation des commandes à quelle heure",
        "متى تتاكد الطلبيات",
    ],
    "exchange_warranty_policy": [
        "الزبون حب يبدل المنتج واش ندير",
        "واش كاين ضمان على السلعة",
        "الزبون استلم منتج خاطئ",
        "est-ce qu'on peut retourner un produit",
        "garantie produit mayna",
        "كيفاش نرجع الدراهم للزبون",
    ],
}
# Looks like a topic keyword but is about something else -> must NOT be confident.
TRAPS = [
    "ما زال ما خلصتش",
    "الطلبية تاعي حابة تكون في الصباح",
    "كل يوم توصيل عندي مشكل مع الزبون",
    "واش رايكم في الشركة",
    "كم سعر الايفون",
    "عندي مشكل في الحساب",
    "ماذا اصنع الان",
    "bonjour je voudrais des informations",
    "شكرا على المعلومات",
    "هاد المنتج مليح",
]
