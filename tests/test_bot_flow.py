# -*- coding: utf-8 -*-
"""Full message path with mocks: group message -> handler -> search -> copy post -> channel link.

Telegram itself is NOT contacted. If python-telegram-bot is not installed, tests/telegram_stub.py
provides a minimal stand-in so the handler logic can be imported and run.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import telegram_stub  # noqa: E402

STUBBED = telegram_stub.install()

import bot  # noqa: E402
from telegram.error import TelegramError  # noqa: E402

ADMIN = "-1009999"


def make_update(text, message_id=1, chat_id=-1001234, chat_type="supergroup", is_bot=False, photo=False, caption=None):
    events = []

    async def reply(*args, **kwargs):
        events.append(("reply", args[0] if args else kwargs.get("text"), kwargs))

    message = SimpleNamespace(
        text=None if (photo or caption) else text,
        caption=caption if caption else (text if photo else None),
        photo=[object()] if photo else None,
        message_id=message_id,
        via_bot=None,
        new_chat_members=None,
        from_user=SimpleNamespace(id=77, username="ali", first_name="Ali", is_bot=is_bot),
        reply_text=AsyncMock(side_effect=reply),
    )
    chat = SimpleNamespace(id=chat_id, type=chat_type, title="Mayna Group", username=None)
    update = SimpleNamespace(effective_message=message, effective_chat=chat)

    async def copy(**kwargs):
        events.append(("copy", kwargs.get("chat_id"), kwargs))
        return SimpleNamespace(message_id=999)

    async def send(**kwargs):
        events.append(("send", kwargs.get("chat_id"), kwargs))

    context = SimpleNamespace(bot=SimpleNamespace(copy_message=AsyncMock(side_effect=copy), send_message=AsyncMock(side_effect=send)))
    return update, context, events


class FlowBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot._SEEN = bot._SeenMessages()
        patcher = mock.patch.dict(os.environ, {"ADMIN_CHAT_ID": ADMIN, "GROUP_CHAT_ID": "-1001234"}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        g = mock.patch.object(bot, "GEMINI_API_KEY", "")
        g.start()
        self.addCleanup(g.stop)

    def copies(self, events):
        return [e for e in events if e[0] == "copy"]


class TestPlainMessageReachesSearchHandler(FlowBase):
    async def test_plain_message_without_command_gets_correct_post_then_link(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟")
        await bot.handle_group_message(update, ctx)
        kinds = [e[0] for e in ev]
        self.assertEqual(kinds, ["reply", "copy", "reply"], ev)  # intro, post, link (separate message)
        copy = ev[1][2]
        self.assertEqual(copy["from_chat_id"], bot.MAYNA_CHANNEL_ID)
        self.assertEqual(copy["message_id"], 15)  # withdraw_commission
        self.assertEqual(copy["chat_id"], -1001234)
        self.assertEqual(copy["reply_to_message_id"], 1)
        self.assertIn(bot.CHANNEL_LINK, ev[2][1])
        self.assertNotIn(bot.CHANNEL_LINK, ev[0][1])  # link never mixed with the intro

    async def test_function_call_alone_is_not_success(self):
        """A correct answer = right post id AND link sent after it; not just 'handler ran'."""
        update, ctx, ev = make_update("Où est mon colis ?")
        await bot.handle_group_message(update, ctx)
        self.assertEqual(self.copies(ev)[0][2]["message_id"], 26)  # delivery_tracking
        self.assertEqual(ev[-1][0], "reply")
        self.assertIn(bot.CHANNEL_LINK, ev[-1][1])

    async def test_each_main_topic_sends_expected_post(self):
        expected = {
            "وقتاش نخلصو؟": 425,
            "شحال التوصيل لوهران؟": 399,
            "مدة التوصيل": 436,
            "كيفاش نفتح حساب؟": 334,
            "وقتاش تتأكد الكوموند؟": 398,
            "شركات التوصيل": 400,
            "رقم خدمة العملاء": 396,
        }
        for i, (q, post) in enumerate(expected.items(), start=10):
            update, ctx, ev = make_update(q, message_id=i)
            await bot.handle_group_message(update, ctx)
            self.assertEqual(self.copies(ev)[0][2]["message_id"], post, q)

    async def test_warranty_sends_both_official_posts(self):
        update, ctx, ev = make_update("هل يوجد ضمان؟")
        await bot.handle_group_message(update, ctx)
        self.assertEqual([c[2]["message_id"] for c in self.copies(ev)], [216, 412])

    async def test_wilaya_is_mentioned_but_no_price_invented(self):
        update, ctx, ev = make_update("شحال التوصيل لوهران؟")
        await bot.handle_group_message(update, ctx)
        intro = ev[0][1]
        self.assertIn("وهران", intro)
        self.assertNotRegex(intro, r"\d{3,}")  # no invented price/duration number

    async def test_caption_of_photo_is_searched(self):
        update, ctx, ev = make_update("", photo=True, caption="كيفاش نتبع الكوموند")
        await bot.handle_group_message(update, ctx)
        self.assertEqual(self.copies(ev)[0][2]["message_id"], 26)


class TestGreetings(FlowBase):
    async def test_greeting_replies_with_link(self):
        for i, g in enumerate(["السلام عليكم", "صباح الخير", "Bonjour", "Salut", "صحا"], start=1):
            update, ctx, ev = make_update(g, message_id=i)
            await bot.handle_group_message(update, ctx)
            self.assertEqual(len(ev), 1, g)
            self.assertIn(bot.CHANNEL_LINK, ev[0][1])

    async def test_new_member_welcome(self):
        update, ctx, ev = make_update("")
        update.effective_message.new_chat_members = [SimpleNamespace(is_bot=False, first_name="Sara")]
        await bot.handle_new_members(update, ctx)
        text = ev[0][1]
        self.assertIn("Sara", text)
        self.assertIn("مسوقي Mayna", text)
        self.assertIn(bot.CHANNEL_LINK, text)


class TestFailures(FlowBase):
    async def test_copy_failure_gives_fallback_and_notifies_admin(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟")
        ctx.bot.copy_message = AsyncMock(side_effect=TelegramError("chat not found"))
        await bot.handle_group_message(update, ctx)
        replies = [e[1] for e in ev if e[0] == "reply"]
        self.assertTrue(any("ما قدرتش نبعث الشرح" in r for r in replies), replies)
        ctx.bot.send_message.assert_awaited()  # admin informed
        self.assertEqual(ctx.bot.send_message.await_args.kwargs["chat_id"], int(ADMIN))

    async def test_deleted_post_is_not_reported_as_sent(self):
        update, ctx, ev = make_update("مدة التوصيل")
        ctx.bot.copy_message = AsyncMock(side_effect=TelegramError("message to copy not found"))
        await bot.handle_group_message(update, ctx)
        replies = [e[1] for e in ev if e[0] == "reply"]
        self.assertFalse(any("لمعلومات وشروحات أخرى" in r and "ما قدرتش" not in r for r in replies[1:2]))
        self.assertTrue(any("ما قدرتش نبعث الشرح" in r for r in replies))

    async def test_unknown_question_escalated_and_user_told_only_after_success(self):
        update, ctx, ev = make_update("عندي مشكل غريب في حسابي")
        await bot.handle_group_message(update, ctx)
        ctx.bot.send_message.assert_awaited_once()
        body = ctx.bot.send_message.await_args.kwargs["text"]
        self.assertIn("@ali", body)
        self.assertIn("https://t.me/c/1234/1", body)  # message link
        self.assertIn("وصلنا السؤال للمشرفين", ev[-1][1])

    async def test_admin_failure_is_not_claimed_as_delivered(self):
        update, ctx, ev = make_update("عندي مشكل غريب في حسابي")
        ctx.bot.send_message = AsyncMock(side_effect=TelegramError("Forbidden"))
        await bot.handle_group_message(update, ctx)
        reply = ev[-1][1]
        self.assertNotIn("وصلنا السؤال للمشرفين", reply)
        self.assertIn("ما قدرتش نوصل السؤال", reply)

    async def test_missing_admin_chat_id_is_not_claimed_as_delivered(self):
        with mock.patch.dict(os.environ, {"ADMIN_CHAT_ID": ""}):
            update, ctx, ev = make_update("عندي مشكل غريب في حسابي")
            await bot.handle_group_message(update, ctx)
        self.assertNotIn("وصلنا السؤال للمشرفين", ev[-1][1])
        ctx.bot.send_message.assert_not_awaited()

    async def test_ambiguous_question_asks_for_clarification_not_guess(self):
        update, ctx, ev = make_update("العمولة")
        await bot.handle_group_message(update, ctx)
        self.assertEqual(self.copies(ev), [])
        self.assertIn("تقصد", ev[-1][1])

    async def test_unmatched_photo_goes_to_admin_with_the_photo(self):
        update, ctx, ev = make_update("", photo=True, caption="واش هاد المنتج متوفر؟")
        await bot.handle_group_message(update, ctx)
        ctx.bot.copy_message.assert_awaited()
        self.assertEqual(ctx.bot.copy_message.await_args.kwargs["chat_id"], int(ADMIN))


class TestGemini(FlowBase):
    async def test_gemini_not_called_when_local_search_is_confident(self):
        with mock.patch.object(bot, "GEMINI_API_KEY", "k"), mock.patch.object(bot, "classify_with_gemini") as g:
            update, ctx, ev = make_update("كيفاش نسحب العمولة؟")
            await bot.handle_group_message(update, ctx)
            g.assert_not_called()

    async def test_gemini_failure_falls_back_to_admin_not_silence(self):
        with mock.patch.object(bot, "GEMINI_API_KEY", "k"), mock.patch.object(bot, "classify_with_gemini", return_value=None):
            update, ctx, ev = make_update("عندي مشكل غريب في حسابي")
            await bot.handle_group_message(update, ctx)
        self.assertTrue(ev, "bot must always answer")
        ctx.bot.send_message.assert_awaited()

    async def test_gemini_resolves_only_known_posts(self):
        with mock.patch.object(bot, "GEMINI_API_KEY", "k"), mock.patch.object(bot, "classify_with_gemini", return_value="delivery_tracking"):
            update, ctx, ev = make_update("عندي مشكل غريب في حسابي")
            await bot.handle_group_message(update, ctx)
        self.assertEqual(self.copies(ev)[0][2]["message_id"], 26)

    def test_gemini_http_error_pauses_and_returns_none(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 429, "quota", {}, None)
        with mock.patch.object(bot, "GEMINI_API_KEY", "secret-key"), \
             mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertIsNone(bot.classify_with_gemini("سؤال"))
            self.assertGreater(bot._GEMINI_PAUSED_UNTIL, 0)
        bot._GEMINI_PAUSED_UNTIL = 0.0

    def test_gemini_key_is_sent_in_header_not_url(self):
        captured = {}

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"candidates":[{"content":{"parts":[{"text":"delivery_tracking"}]}}]}'

        def fake_open(req, timeout=None):
            captured["url"], captured["headers"], captured["timeout"] = req.full_url, dict(req.header_items()), timeout
            return R()

        with mock.patch.object(bot, "GEMINI_API_KEY", "secret-key"), mock.patch("urllib.request.urlopen", fake_open):
            self.assertEqual(bot.classify_with_gemini("سؤال"), "delivery_tracking")
        self.assertNotIn("secret-key", captured["url"])
        self.assertEqual(captured["headers"].get("X-goog-api-key"), "secret-key")
        self.assertEqual(captured["timeout"], 12)

    def test_gemini_garbage_answer_is_rejected(self):
        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"candidates":[{"content":{"parts":[{"text":"make_up_a_price"}]}}]}'
        with mock.patch.object(bot, "GEMINI_API_KEY", "k"), mock.patch("urllib.request.urlopen", lambda *a, **k: R()):
            self.assertIsNone(bot.classify_with_gemini("سؤال"))


class TestProtection(FlowBase):
    async def test_same_message_is_answered_once(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟", message_id=5)
        await bot.handle_group_message(update, ctx)
        n = len(ev)
        await bot.handle_group_message(update, ctx)
        self.assertEqual(len(ev), n)

    async def test_bot_messages_and_private_chats_ignored(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟", is_bot=True)
        await bot.handle_group_message(update, ctx)
        update2, ctx2, ev2 = make_update("كيفاش نسحب العمولة؟", chat_type="private", message_id=2)
        await bot.handle_group_message(update2, ctx2)
        self.assertEqual(ev + ev2, [])

    async def test_commands_are_left_to_other_handlers(self):
        update, ctx, ev = make_update("/start")
        await bot.handle_group_message(update, ctx)
        self.assertEqual(ev, [])

    async def test_group_restriction_is_opt_in(self):
        update, ctx, ev = make_update("كيفاش نسحب العمولة؟", chat_id=-1005555)
        await bot.handle_group_message(update, ctx)
        self.assertTrue(ev)  # default: answers in any group the bot is a member of
        with mock.patch.dict(os.environ, {"RESTRICT_TO_GROUP": "1"}):
            update, ctx, ev = make_update("كيفاش نسحب العمولة؟", chat_id=-1005555, message_id=2)
            await bot.handle_group_message(update, ctx)
        self.assertEqual(ev, [])


class TestKnowledgeBase(unittest.TestCase):
    def test_all_reference_posts_preserved(self):
        expected = {
            334, 335, 15, 16, 26, 72, 77, 84, 216, 17, 399, 396, 398, 400, 408, 409, 412, 425, 436,
        }
        self.assertEqual(set(bot.VIDEOS.values()), expected)
        self.assertEqual(bot.MAYNA_CHANNEL_ID, -1003071373878)

    def test_every_topic_has_intro_and_label(self):
        for key in bot.VIDEOS:
            self.assertIn(key, bot.INTRO_TEXTS)
        for key in bot.VIDEOS:
            if key != "exchange_warranty_policy_original":
                self.assertIn(key, bot.TOPIC_LABELS)


class TestRegistration(unittest.TestCase):
    def test_handlers_registered_for_plain_text_in_groups(self):
        """Stub-level check only: real PTB filter semantics must be confirmed in a live run."""
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x"}):
            bot.main()
        from telegram.ext import Application
        app = Application.last if STUBBED else None
        if app is None:
            self.skipTest("real PTB installed: verify with a live run")
        callbacks = [h.callback for h in app.handlers]
        self.assertIn(bot.handle_group_message, callbacks)
        group_filter = repr(app.handlers[callbacks.index(bot.handle_group_message)].filters)
        self.assertIn("GROUPS", group_filter)
        self.assertIn("~COMMAND", group_filter)
        self.assertNotIn("(COMMAND", group_filter.replace("~COMMAND", ""))
        self.assertEqual(app.error_handlers, [bot.handle_error])


if __name__ == "__main__":
    unittest.main()
