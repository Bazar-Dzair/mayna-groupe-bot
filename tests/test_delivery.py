# -*- coding: utf-8 -*-
"""Delivery-price tests: the whole path  Telegram message -> handle_group_message -> engine -> reply.

REFERENCE_TABLE below was typed by hand from Mayna's «أسعار التوصيل» poster and is deliberately
independent of delivery_prices.json, so a wrong value in the JSON cannot hide itself.
Telegram itself is never contacted (see tests/test_real_ptb.py for the real-PTB routing test).
"""
import os
import sys
import unittest
from unittest import mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_bot_flow import FlowBase, make_update  # noqa: E402  (also installs the PTB stub)
import bot  # noqa: E402
import delivery  # noqa: E402
from telegram.error import TelegramError  # noqa: E402

# (number, name, home, office) — 9999 = needs admin confirmation
REFERENCE_TABLE = [
    (1, "أدرار", 1100, 550), (2, "الشلف", 650, 350), (3, "الأغواط", 800, 350), (4, "أم البواقي", 650, 350),
    (5, "باتنة", 650, 350), (6, "بجاية", 600, 350), (7, "بسكرة", 700, 350), (8, "بشار", 900, 500),
    (9, "البليدة", 450, 450), (10, "البويرة", 600, 350), (11, "تمنراست", 1500, 700), (12, "تبسة", 700, 350),
    (13, "تلمسان", 650, 350), (14, "تيارت", 700, 350), (15, "تيزي وزو", 600, 350), (16, "الجزائر", 300, 300),
    (17, "الجلفة", 800, 450), (18, "جيجل", 650, 350), (19, "سطيف", 650, 350), (20, "سعيدة", 700, 350),
    (21, "سكيكدة", 650, 350), (22, "سيدي بلعباس", 650, 350), (23, "عنابة", 650, 350), (24, "قالمة", 700, 350),
    (25, "قسنطينة", 650, 350), (26, "المدية", 600, 350), (27, "مستغانم", 650, 350), (28, "المسيلة", 700, 350),
    (29, "معسكر", 650, 350), (30, "ورقلة", 900, 450), (31, "وهران", 600, 350), (32, "البيض", 1000, 800),
    (33, "إليزي", 1500, 1500), (34, "برج بوعريريج", 650, 350), (35, "بومرداس", 400, 400),
    (36, "الطارف", 700, 350), (37, "تندوف", 1300, 1300), (38, "تيسمسيلت", 650, 350), (39, "الوادي", 900, 500),
    (40, "خنشلة", 700, 350), (41, "سوق أهراس", 750, 400), (42, "تيبازة", 400, 300), (43, "ميلة", 700, 400),
    (44, "عين الدفلى", 650, 350), (45, "النعامة", 900, 450), (46, "عين تموشنت", 650, 400),
    (47, "غرداية", 800, 450), (48, "غليزان", 750, 400), (49, "تيميمون", 1200, 750),
    (50, "برج باجي مختار", 9999, 9999), (51, "أولاد جلال", 850, 550), (52, "بني عباس", 1000, 1000),
    (53, "عين صالح", 1600, 900), (54, "عين قزام", 9999, 9999), (55, "تقرت", 850, 450),
    (56, "جانت", 9999, 9999), (57, "المغير", 950, 500), (58, "المنيعة", 950, 550),
]
CONFIRMED = [r for r in REFERENCE_TABLE if r[2] != 9999]


def _ask_phrase(name: str) -> str:
    """Natural Darija prefix form: وهران -> لوهران, الشلف -> للشلف."""
    return ("لل" + name[2:]) if name.startswith("ال") else "ل" + name


class TestPriceTable(unittest.TestCase):
    def test_json_matches_reference_table_for_all_58(self):
        self.assertEqual(len(delivery.WILAYAS), 58)
        actual = [(w.number, w.name, w.home, w.office) for w in delivery.WILAYAS]
        self.assertEqual(actual, REFERENCE_TABLE)

    def test_every_alias_maps_to_exactly_one_wilaya_and_finds_it(self):
        for w in delivery.WILAYAS:
            for alias in (w.name,) + w.aliases:
                found = [n for n, _, _ in delivery.find_wilayas(f"شحال التوصيل {alias}")]
                self.assertIn(w.number, found, alias)


class TestEngine(unittest.TestCase):
    def test_spec_questions_are_price_questions(self):
        for q in [
            "شحال التوصيل لوهران؟", "شحال ليفريزون وهران؟", "وهران للدار شحال؟", "شحال للمكتب في وهران؟",
            "prix livraison Oran", "combien coûte la livraison à Oran", "Tarif de livraison à domicile à Oran",
            "شحال حق التوصيل للولاية تاعي؟", "أسعار التوصيل للولايات", "ابعثلي جدول أسعار التوصيل",
            "نحب نعرف سعر التوصيل",
        ]:
            self.assertTrue(delivery.answer(q).handled, q)

    def test_oran_variants_all_give_oran(self):
        for q in ["شحال التوصيل لوهران؟", "التوصيل في ولاية وهران شحال", "prix livraison Oran", "وهران للدار شحال؟"]:
            r = delivery.answer(q)
            self.assertEqual(r.wilayas, ["وهران"], q)

    def test_home_only_and_office_only(self):
        home = delivery.answer("وهران للدار شحال؟").text
        self.assertIn("600 دج", home)
        self.assertNotIn("350", home)
        office = delivery.answer("شحال للمكتب في وهران؟").text
        self.assertIn("350 دج", office)
        self.assertNotIn("600", office)
        both = delivery.answer("شحال التوصيل لوهران؟").text
        self.assertIn("600 دج", both)
        self.assertIn("350 دج", both)

    def test_other_delivery_topics_are_not_price_answers(self):
        for q in [
            "شحال تستغرق التوصيلة لوهران؟", "وقتاش توصل الكولي لوهران", "مدة التوصيل لوهران",
            "la livraison prend combien de temps", "شكون شركات التوصيل لي تتعاملو معاهم؟",
            "شركات التوصيل", "كيفاش نتتبع الطرد", "Où est mon colis ?", "كيفاش نسحب العمولة؟",
        ]:
            r = delivery.answer(q)
            self.assertFalse(r.handled, (q, r.reason))

    def test_corpus_has_no_false_positives(self):
        from tests.cases import CASES
        from tests.heldout import HELDOUT, TRAPS
        from tests.blind import BLIND
        rows = [(t, q) for src in (CASES, HELDOUT) for t, qs in src.items() for q in qs] + list(BLIND)
        for topic, q in rows:
            if topic != "delivery_prices_58_wilayas":
                self.assertFalse(delivery.answer(q).handled, (topic, q))
            else:
                self.assertTrue(delivery.answer(q).handled, q)
        for q in TRAPS:
            self.assertFalse(delivery.answer(q).handled, q)

    def test_spelling_variants_and_small_typos(self):
        for q, name in [
            ("شحال التوصيل لوهرن", "وهران"), ("Prix livraison Oraan", "وهران"), ("سعر التوصيل لتلمسن", "تلمسان"),
            ("tarif livraison tizi-ouzou", "تيزي وزو"), ("سعر المكتب في Tizi Ouzou", "تيزي وزو"),
            ("شحال التوصيل ل Alger Centre", "الجزائر"), ("prix livraison timimoun", "تيميمون"),
            ("شحال التوصيل لولاية سطيف", "سطيف"), ("سعر التوصيل فـ constantine", "قسنطينة"),
        ]:
            self.assertEqual(delivery.answer(q).wilayas, [name], q)

    def test_typo_is_confirmed_to_the_member(self):
        self.assertIn("فهمت أنك تقصد وهران", delivery.answer("شحال التوصيل لوهرن").text)

    def test_no_wilaya_asks_instead_of_guessing(self):
        for q in ["نحب نعرف سعر التوصيل", "شحال حق التوصيل للولاية تاعي؟", "combien coûte la livraison ?"]:
            r = delivery.answer(q)
            self.assertEqual(r.kind, "ask_wilaya", q)
            self.assertIn("واش هي الولاية تاعك؟", r.text)
            self.assertNotRegex(r.text, r"\d{3,}")

    def test_general_question_returns_all_58(self):
        for q in ["أسعار التوصيل للولايات", "ابعثلي جدول أسعار التوصيل", "prix livraison toutes les wilayas"]:
            r = delivery.answer(q)
            self.assertEqual(r.kind, "table", q)
            for _, name, home, office in REFERENCE_TABLE:
                self.assertIn(name, r.text)
            self.assertNotIn("9999", r.text)
            self.assertLess(len(r.text), 4096)

    def test_unconfirmed_9999_is_never_shown_as_a_price(self):
        for number, name, _, _ in [r for r in REFERENCE_TABLE if r[2] == 9999]:
            for q in (f"شحال التوصيل ل{name}", f"سعر المكتب في {name}", f"التوصيل للدار في {name} شحال"):
                r = delivery.answer(q)
                self.assertEqual(r.wilayas, [name], q)
                self.assertNotIn("9999", r.text)
                self.assertIn("تأكيد", r.text)
                self.assertNotRegex(r.text.split("للاطلاع")[0], r"\d{3,}")

    def test_two_wilayas_in_one_question(self):
        r = delivery.answer("شحال التوصيل لسطيف وقسنطينة")
        self.assertEqual(r.wilayas, ["سطيف", "قسنطينة"])

    def test_country_word_with_plural_means_table_not_the_capital(self):
        self.assertEqual(delivery.answer("اسعار التوصيل لكل ولايات الجزائر").kind, "table")
        self.assertEqual(delivery.answer("شحال التوصيل للجزائر").wilayas, ["الجزائر"])

    def test_reply_format_matches_the_requested_text(self):
        text = delivery.answer("شحال التوصيل لوهران؟").text
        self.assertEqual(
            text,
            "أسعار التوصيل إلى وهران حسب جدول Mayna:\n"
            "- التوصيل للبيت: 600 دج\n"
            "- مكتب التوصيل: 350 دج\n\n"
            "للاطلاع على شروحات ومعلومات أخرى، ادخل لقناة Mayna:\n"
            "https://t.me/+wyKej2q0oK0zYjI0",
        )


class TestGroupHandlerFullPath(FlowBase):
    """message -> bot.handle_group_message -> delivery engine -> reply_text (mocked Telegram)."""

    def _replies(self, ev):
        return [e[1] for e in ev if e[0] == "reply"]

    async def test_oran_question_gets_oran_prices_only(self):
        update, ctx, ev = make_update("شحال التوصيل لوهران؟")
        await bot.handle_group_message(update, ctx)
        reply = self._replies(ev)
        self.assertEqual(len(reply), 1)
        self.assertIn("600 دج", reply[0])
        self.assertIn("350 دج", reply[0])
        self.assertEqual([e for e in ev if e[0] in ("copy", "send")], [])  # no channel post, no admin ping

    async def test_handler_really_calls_the_delivery_engine(self):
        with mock.patch.object(bot.delivery, "answer", wraps=bot.delivery.answer) as spy:
            update, ctx, ev = make_update("Prix livraison Oran", message_id=5)
            await bot.handle_group_message(update, ctx)
        spy.assert_called_once_with("Prix livraison Oran")
        self.assertIn("600 دج", self._replies(ev)[0])

    async def test_french_capital_office_and_home_questions(self):
        cases = [
            ("Prix livraison Oran", ["600", "350"], []),
            ("شحال للدار في الجزائر العاصمة؟", ["300 دج"], ["350"]),
            ("سعر المكتب في تيزي وزو", ["350 دج"], ["600"]),
        ]
        for i, (q, present, absent) in enumerate(cases, start=20):
            update, ctx, ev = make_update(q, message_id=i)
            await bot.handle_group_message(update, ctx)
            reply = self._replies(ev)[0]
            for p in present:
                self.assertIn(p, reply, q)
            for a in absent:
                self.assertNotIn(a, reply, q)

    async def test_duration_question_does_not_return_prices(self):
        update, ctx, ev = make_update("شحال تستغرق التوصيلة لوهران؟")
        await bot.handle_group_message(update, ctx)
        self.assertEqual([e[2]["message_id"] for e in ev if e[0] == "copy"], [436])  # duration post
        self.assertNotIn("600 دج", " ".join(self._replies(ev)))

    async def test_companies_question_does_not_return_prices(self):
        update, ctx, ev = make_update("شكون شركات التوصيل لي تتعاملو معاهم؟")
        await bot.handle_group_message(update, ctx)
        self.assertEqual([e[2]["message_id"] for e in ev if e[0] == "copy"], [400])  # companies post
        self.assertNotRegex(" ".join(self._replies(ev)), r"\d{3,} دج")

    async def test_general_question_sends_whole_table(self):
        update, ctx, ev = make_update("أسعار التوصيل للولايات")
        await bot.handle_group_message(update, ctx)
        text = self._replies(ev)[0]
        self.assertIn("وهران: بيت 600 | مكتب 350", text)
        self.assertIn("تمنراست: بيت 1500 | مكتب 700", text)

    async def test_missing_wilaya_asks_the_member(self):
        update, ctx, ev = make_update("نحب نعرف سعر التوصيل")
        await bot.handle_group_message(update, ctx)
        self.assertIn("واش هي الولاية تاعك؟", self._replies(ev)[0])

    async def test_unconfirmed_wilaya_is_not_answered_with_9999(self):
        update, ctx, ev = make_update("سعر التوصيل لجانت")
        await bot.handle_group_message(update, ctx)
        reply = self._replies(ev)[0]
        self.assertNotIn("9999", reply)
        self.assertIn("تأكيد", reply)

    async def test_typo_in_wilaya_name_still_answers(self):
        update, ctx, ev = make_update("شحال التوصيل لوهرن")
        await bot.handle_group_message(update, ctx)
        self.assertIn("600 دج", self._replies(ev)[0])

    async def test_all_58_wilayas_get_their_own_correct_price_through_the_handler(self):
        message_id = 1000
        for number, name, home, office in REFERENCE_TABLE:
            for question, show in [
                (f"شحال التوصيل {_ask_phrase(name)}؟", "both"),
                (f"سعر المكتب في {name}", "office"),
                (f"شحال للدار في {name}", "home"),
            ]:
                message_id += 1
                update, ctx, ev = make_update(question, message_id=message_id)
                await bot.handle_group_message(update, ctx)
                replies = self._replies(ev)
                self.assertEqual(len(replies), 1, question)
                reply = replies[0]
                self.assertIn(f"إلى {name}", reply, question)
                body = reply.split("للاطلاع")[0]
                if home == 9999:
                    self.assertNotIn("9999", reply, question)
                    self.assertIn("تأكيد", reply, question)
                    continue
                if show in ("both", "home"):
                    self.assertIn(f"التوصيل للبيت: {home} دج", body, question)
                else:
                    self.assertNotIn("التوصيل للبيت", body, question)
                if show in ("both", "office"):
                    self.assertIn(f"مكتب التوصيل: {office} دج", body, question)
                else:
                    self.assertNotIn("مكتب التوصيل", body, question)

    async def test_other_wilaya_does_not_repeat_oran_prices(self):
        update, ctx, ev = make_update("شحال التوصيل لتمنراست؟", message_id=70)
        await bot.handle_group_message(update, ctx)
        reply = self._replies(ev)[0]
        self.assertIn("1500 دج", reply)
        self.assertIn("700 دج", reply)
        self.assertNotIn("600", reply)
        self.assertNotIn("وهران", reply)


class TestTelegramFailures(FlowBase):
    async def test_failed_reply_is_retried_without_reply_to(self):
        update, ctx, ev = make_update("شحال التوصيل لوهران؟")
        ok = []

        async def flaky(text, **kwargs):
            if "reply_to_message_id" in kwargs:
                raise TelegramError("Message to be replied not found")
            ok.append(text)

        update.effective_message.reply_text = AsyncMock(side_effect=flaky)
        with self.assertLogs("mayna-assistant", level="ERROR") as logs:
            await bot.handle_group_message(update, ctx)
        self.assertEqual(len(ok), 1)
        self.assertIn("600 دج", ok[0])
        self.assertTrue(any("refused the reply" in line for line in logs.output))

    async def test_total_telegram_failure_is_logged_and_does_not_crash(self):
        update, ctx, ev = make_update("شحال التوصيل لوهران؟")
        update.effective_message.reply_text = AsyncMock(side_effect=TelegramError("Forbidden: bot was kicked"))
        with self.assertLogs("mayna-assistant", level="ERROR") as logs:
            await bot.handle_group_message(update, ctx)  # must not raise
        self.assertTrue(any("NOT delivered" in line for line in logs.output))
        self.assertEqual(update.effective_message.reply_text.await_count, 2)

    async def test_engine_crash_falls_back_to_normal_flow(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟")
        with mock.patch.object(bot.delivery, "answer", side_effect=RuntimeError("boom")):
            with self.assertLogs("mayna-assistant", level="ERROR"):
                await bot.handle_group_message(update, ctx)
        self.assertEqual([e[2]["message_id"] for e in ev if e[0] == "copy"], [15])


class TestWorkflowConfig(unittest.TestCase):
    def test_workflow_runs_bot_py_and_passes_all_secrets(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, ".github", "workflows", "bot.yml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("python bot.py", text)
        for name in ("TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID", "GEMINI_API_KEY", "GROUP_CHAT_ID"):
            self.assertIn(f"secrets.{name}", text)
        self.assertNotRegex(text, r"\d{8,}:[A-Za-z0-9_-]{30,}")  # no hard-coded bot token


if __name__ == "__main__":
    unittest.main()
