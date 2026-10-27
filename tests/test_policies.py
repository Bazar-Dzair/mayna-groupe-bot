# -*- coding: utf-8 -*-
"""Store ("online only, no shop") and wholesale policies: detection + the full handler path."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import telegram_stub  # noqa: E402

telegram_stub.install()

import policies  # noqa: E402
from tests.test_bot_flow import FlowBase, make_update  # noqa: E402
import bot  # noqa: E402


class TestDetection(unittest.TestCase):
    def kind(self, text):
        return policies.detect(text).kind

    def test_store_questions(self):
        for q in [
            "زبون حاب يجي يدي منتج من عندكم",
            "زبون حب يجي للمحل و يشري",
            "واش عندكم محل؟",
            "وين المحل تاعكم",
            "الزبون من وهران يحب يجي يستلم من المحل",
            "نجي نشري من عندكم مباشرة",
            "كاين محل في الجزائر العاصمة؟",
            "زبون باغي ينزل يشري السلعة من المخزن",
            "client veut venir au magasin",
            "Vous avez une boutique ?",
            "est-ce que je peux passer récupérer le produit chez vous",
        ]:
            self.assertEqual(self.kind(q), policies.KIND_STORE, q)

    def test_wholesale_questions(self):
        for q in [
            "تبيعو بالجملة؟",
            "تبيعو جملة؟",
            "واش كاين سعر الجملة",
            "vente en gros possible ?",
            "wholesale?",
            "زبون حاب ياخد كمية كبيرة",
            "زبون يحب ياخد 10 حبات",
        ]:
            self.assertEqual(self.kind(q), policies.KIND_WHOLESALE, q)

    def test_all_at_once_questions(self):
        for q in [
            "الزبون يحب ياخد كمية كاملة دفعة وحدة",
            "نبعثلو 10 حبات دفعة وحدة؟",
            "زبون حب 8 قطع كلها دفعة وحدة ممكن؟",
            "باغي كمية كبيرة وندفع عربون",
        ]:
            self.assertEqual(self.kind(q), policies.KIND_BULK_ONCE, q)

    def test_other_questions_are_left_alone(self):
        for q in [
            "كيفاش نسحب العمولة؟",
            "شحال التوصيل لوهران؟",
            "وقتاش توصل الطلبية؟",
            "الكمية متوفرة؟",
            "واش كاين ستوك؟",
            "عندي محل نبيع فيه منتجاتكم",
            "نحب نفتح محل",
            "كيفاش نسجل طلبية؟",
            "السلام عليكم",
            "وين وصلت طلبيتي",
            "زبون حب يستلم من مكتب ياليدين",
            "الزبون ياخد المنتج وقتاش؟",
            "شحال سعر المنتج؟",
            "نحب نقول جملة مفيدة",
            "زبون حب يشري منتج",
        ]:
            self.assertFalse(policies.detect(q).handled, q)

    def test_answers_contain_the_agreed_rules(self):
        store = policies.STORE_REPLY
        self.assertIn("أونلاين فقط", store)
        self.assertIn("ديبو", store)
        self.assertNotIn("http", store)

        wholesale = policies.WHOLESALE_REPLY
        self.assertIn("3 حبات", wholesale)
        self.assertIn("نصف المبلغ", wholesale)
        self.assertIn("روتور", wholesale)
        self.assertIn("الملاحظة", wholesale)
        self.assertIn(policies._NOTE_TEXT, wholesale)

        once = policies.BULK_ONCE_REPLY
        self.assertIn("نصف المبلغ", once)
        self.assertIn(policies._NOTE_TEXT, once)


class TestHandlerPath(FlowBase):
    async def test_store_question_gets_online_only_reply(self):
        update, ctx, ev = make_update("زبون حاب يجي يدي منتج من عندكم")
        await bot.handle_group_message(update, ctx)
        self.assertEqual([e[0] for e in ev], ["reply"], ev)
        self.assertEqual(ev[0][1], policies.STORE_REPLY)
        self.assertEqual(ev[0][2].get("reply_to_message_id"), 1)
        self.assertEqual([e for e in ev if e[0] in ("send", "copy")], [])  # no admin escalation, no post copy

    async def test_wholesale_question_gets_wholesale_reply(self):
        update, ctx, ev = make_update("تبيعو بالجملة؟")
        await bot.handle_group_message(update, ctx)
        self.assertEqual([e[0] for e in ev], ["reply"], ev)
        self.assertEqual(ev[0][1], policies.WHOLESALE_REPLY)
        self.assertEqual([e for e in ev if e[0] in ("send", "copy")], [])

    async def test_all_at_once_gets_prepayment_reply(self):
        update, ctx, ev = make_update("زبون يحب ياخد كمية كاملة دفعة وحدة")
        await bot.handle_group_message(update, ctx)
        self.assertEqual(ev[0][1], policies.BULK_ONCE_REPLY)

    async def test_delivery_price_question_still_answered_by_delivery_engine(self):
        update, ctx, ev = make_update("شحال التوصيل لوهران؟")
        await bot.handle_group_message(update, ctx)
        self.assertNotIn(ev[0][1], (policies.STORE_REPLY, policies.WHOLESALE_REPLY, policies.BULK_ONCE_REPLY))
        self.assertIn("وهران", ev[0][1])


if __name__ == "__main__":
    unittest.main()
