# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from matcher import classify, extract_wilaya, is_greeting, is_thanks, normalize  # noqa: E402
from tests.blind import BLIND  # noqa: E402
from tests.cases import CASES, UNCLEAR  # noqa: E402
from tests.heldout import HELDOUT, TRAPS  # noqa: E402


class TestNormalize(unittest.TestCase):
    def test_arabic_forms_and_diacritics(self):
        self.assertEqual(normalize("إِلْغَاءُ الطَّلَبِيَّة"), normalize("الغاء الطلبيه"))

    def test_elongation_and_punctuation(self):
        self.assertEqual(normalize("كيفااااش!!! نسحب؟؟"), "كيفاش نسحب")

    def test_french_accents(self):
        self.assertEqual(normalize("Où est mon colis ?"), "ou est mon colis")

    def test_arabic_indic_digits_kept(self):
        self.assertIn("58", normalize("٥٨ ولاية"))

    def test_wilaya_extraction(self):
        self.assertEqual(extract_wilaya(normalize("شحال التوصيل لوهران")), "وهران")
        self.assertEqual(extract_wilaya(normalize("prix livraison Oran")), "وهران")
        self.assertIsNone(extract_wilaya(normalize("شحال التوصيل")))


class TestGreeting(unittest.TestCase):
    def test_greetings(self):
        for g in ["السلام عليكم", "سلام", "صباح الخير", "صحا", "Bonjour", "Salut", "سلام عليكم ورحمة الله"]:
            self.assertTrue(is_greeting(g), g)

    def test_greeting_plus_question_is_not_a_greeting(self):
        self.assertFalse(is_greeting("سلام كيفاش نسحب العمولة"))
        self.assertFalse(is_greeting("Bonjour comment retirer ma commission ?"))


def _make_topic_test(topic, question):
    def test(self):
        r = classify(question)
        self.assertEqual((r.status, r.topic), ("match", topic), f"{question!r} -> {r.status}/{r.topic} {r.scores}")
    return test


class TestTopics(unittest.TestCase):
    pass


for _topic, _qs in CASES.items():
    for _i, _q in enumerate(_qs):
        setattr(TestTopics, f"test_{_topic}_{_i:02d}", _make_topic_test(_topic, _q))
for _topic, _qs in HELDOUT.items():
    for _i, _q in enumerate(_qs):
        setattr(TestTopics, f"test_heldout_{_topic}_{_i:02d}", _make_topic_test(_topic, _q))
for _i, (_topic, _q) in enumerate(BLIND):
    setattr(TestTopics, f"test_blind_{_i:02d}_{_topic}", _make_topic_test(_topic, _q))


class TestNoWrongMatch(unittest.TestCase):
    def test_unclear_questions_never_confident(self):
        for q in UNCLEAR + TRAPS:
            r = classify(q)
            self.assertNotEqual(r.status, "match", f"{q!r} -> {r.topic}")

    def test_single_keyword_is_not_enough(self):
        # one word shared with a topic must not pick that topic
        for q in ["الطلبية", "التوصيل", "العمولة", "الزبون"]:
            self.assertNotEqual(classify(q).status, "match", q)

    def test_order_word_does_not_force_tracking(self):
        r = classify("كيفاش نسجل طلبية جديدة")
        self.assertEqual(r.topic, "new_order_commission")
        r = classify("الطلبية وقتاش تتأكد")
        self.assertEqual(r.topic, "order_confirmation_times")

    def test_delivery_word_does_not_force_prices(self):
        self.assertEqual(classify("مدة التوصيل").topic, "delivery_duration_58_wilayas")
        self.assertEqual(classify("شركات التوصيل").topic, "delivery_companies")
        self.assertEqual(classify("اسعار التوصيل").topic, "delivery_prices_58_wilayas")
        self.assertEqual(classify("وين راهي الطلبية").topic, "delivery_tracking")

    def test_wilaya_is_extracted_not_used_to_invent_data(self):
        r = classify("شحال التوصيل لوهران؟")
        self.assertEqual(r.topic, "delivery_prices_58_wilayas")
        self.assertEqual(r.wilaya, "وهران")


if __name__ == "__main__":
    unittest.main()


class TestThanks(unittest.TestCase):
    def test_thanks_variants(self):
        for t in ["شكرا", "شكرا اخي راني حتى نتعلم باش نقدر نخدم معكم", "نعم شكرا اخي", "ربي يحفظك",
                  "بارك الله فيك", "جزاك الله خيرا", "merci beaucoup", "Thanks", "يعطيك الصحة",
                  "مشكور خويا", "Barakallahou fik", "الله يبارك فيك", "تسلم"]:
            self.assertTrue(is_thanks(t), t)

    def test_not_thanks(self):
        for t in ["شكرا بصح كيفاش نسجل", "شكرا واش التوصيل", "سلام وعليكم نهاركم مبارك", "كيفاش نسجل", "شحال التوصيل لوهران؟"]:
            self.assertFalse(is_thanks(t), t)
