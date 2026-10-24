# -*- coding: utf-8 -*-
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest import mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import telegram_stub  # noqa: E402

telegram_stub.install()

import bot  # noqa: E402
import moderation  # noqa: E402
from telegram.ext import ApplicationHandlerStop  # noqa: E402

CHAT = NS(id=-1001234, type="supergroup", title="Mayna Group", username=None)


def msg(text=None, user="ali", user_id=77, is_bot=False, entities=None, **kw):
    base = dict(
        text=text, caption=None, entities=entities or [], caption_entities=[], photo=None, video=None,
        video_note=None, animation=None, sticker=None, document=None, via_bot=None, new_chat_members=None,
        sender_chat=None, is_automatic_forward=False, reply_to_message=None, message_id=5,
        from_user=NS(id=user_id, username=user, first_name="Ali", is_bot=is_bot),
        delete=AsyncMock(), reply_text=AsyncMock(),
    )
    base.update(kw)
    return NS(**base)


def ctx(admin_ids=()):
    sent = NS(delete=AsyncMock())
    bot_obj = NS(
        get_chat_administrators=AsyncMock(return_value=[NS(user=NS(id=i)) for i in admin_ids]),
        send_message=AsyncMock(return_value=sent),
        copy_message=AsyncMock(return_value=NS(message_id=999)),
    )
    return NS(bot=bot_obj)


class TestLinkDetection(unittest.TestCase):
    def test_links_are_detected(self):
        for t in (
            "https://example.com/x", "http://a.b", "www.site.com", "t.me/SomeBot", "https://t.me/SomeBot?start=1",
            "telegram.me/abc", "t . me / abc", "visitez mayna.dz/promo", "go to shop.com", "TG://resolve?domain=x",
            "أنظر هنا: site.online", "h t t p s : //x.com",
        ):
            self.assertTrue(moderation.has_link(msg(t)), t)

    def test_hidden_and_entity_links(self):
        self.assertTrue(moderation.has_link(msg("اضغط هنا", entities=[NS(type="text_link")])))
        self.assertTrue(moderation.has_link(msg("x", entities=[NS(type="url")])))
        self.assertTrue(moderation.has_link(msg(None, caption="https://x.com")))

    def test_normal_text_is_not_a_link(self):
        for t in ("شحال التوصيل لوهران؟", "سلام @MaynaDz", "بعتلك mail على ali@gmail.com", "السعر 2500 دج",
                  "كيفاش نسجل", "ok.", "الثمن 3.5 ألف", "version 2.0"):
            self.assertFalse(moderation.has_link(msg(t)), t)


class TestMediaDetection(unittest.TestCase):
    def test_blocked(self):
        for kw in (
            dict(photo=[object()]), dict(video=object()), dict(video_note=object()), dict(animation=object()),
            dict(sticker=object()),
            dict(document=NS(mime_type="image/png", file_name="a.png")),
            dict(document=NS(mime_type="video/mp4", file_name="a.mp4")),
            dict(document=NS(mime_type="application/octet-stream", file_name="clip.MOV")),
            dict(document=NS(mime_type=None, file_name="p.jpeg")),
        ):
            self.assertTrue(moderation.blocked_media(msg("x", **kw)), kw)

    def test_allowed(self):
        self.assertFalse(moderation.blocked_media(msg("نص فقط")))
        self.assertFalse(moderation.blocked_media(msg("x", document=NS(mime_type="application/pdf", file_name="a.pdf"))))


class TestModerationHandler(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        moderation._ADMIN_CACHE.clear()
        bot._WARNED_AT.clear()
        p = mock.patch.dict(os.environ, {"RESTRICT_TO_GROUP": "", "ADMIN_CHAT_ID": "-100999"}, clear=False)
        p.start()
        self.addCleanup(p.stop)

    async def run_handler(self, message, context=None):
        context = context or ctx()
        stopped = False
        try:
            await bot.handle_moderation(NS(effective_message=message, effective_chat=CHAT), context)
        except ApplicationHandlerStop:
            stopped = True
        return stopped, context

    async def test_member_link_deleted_and_warned(self):
        m = msg("https://t.me/SomeBot")
        stopped, c = await self.run_handler(m)
        self.assertTrue(stopped)
        m.delete.assert_awaited_once()
        text = c.bot.send_message.await_args.kwargs["text"]
        self.assertIn("ممنوع نشر الروابط", text)
        self.assertIn("⚠️", text)

    async def test_member_photo_and_video_deleted(self):
        for kw in (dict(photo=[object()]), dict(video=object())):
            bot._WARNED_AT.clear()
            m = msg(None, **kw)
            stopped, c = await self.run_handler(m)
            self.assertTrue(stopped)
            m.delete.assert_awaited_once()
            self.assertIn("ممنوع نشر الصور والفيديوهات", c.bot.send_message.await_args.kwargs["text"])

    async def test_album_gets_one_warning(self):
        c = ctx()
        for i in range(4):
            await self.run_handler(msg(None, photo=[object()], message_id=10 + i), c)
        self.assertEqual(c.bot.send_message.await_count, 1)

    async def test_admin_by_username_may_post_links_and_media(self):
        for m in (msg("https://x.com", user="MaynaDz", user_id=1), msg(None, user="maynadz", user_id=1, photo=[object()])):
            stopped, c = await self.run_handler(m)
            self.assertFalse(stopped)
            m.delete.assert_not_awaited()

    async def test_group_administrator_may_post(self):
        m = msg("www.x.com", user="other", user_id=42)
        stopped, c = await self.run_handler(m, ctx(admin_ids=[42]))
        self.assertFalse(stopped)
        m.delete.assert_not_awaited()

    async def test_anonymous_admin_and_bots_may_post(self):
        anon = msg("https://x.com", sender_chat=NS(id=CHAT.id))
        self.assertFalse((await self.run_handler(anon))[0])
        b = msg("https://x.com", user="somebot", is_bot=True)
        self.assertFalse((await self.run_handler(b))[0])
        v = msg("https://x.com", via_bot=NS(id=1))
        self.assertFalse((await self.run_handler(v))[0])

    async def test_normal_member_message_untouched(self):
        m = msg("شحال التوصيل لوهران؟")
        stopped, c = await self.run_handler(m)
        self.assertFalse(stopped)
        m.delete.assert_not_awaited()
        c.bot.send_message.assert_not_awaited()

    async def test_delete_failure_notifies_admin_not_group(self):
        from telegram.error import TelegramError
        m = msg("https://x.com")
        m.delete = AsyncMock(side_effect=TelegramError("no rights"))
        bot._NO_DELETE_NOTIFIED_AT.clear()
        stopped, c = await self.run_handler(m)
        self.assertTrue(stopped)
        self.assertEqual(c.bot.send_message.await_args.kwargs["chat_id"], -100999)

    def test_moderation_handler_runs_first(self):
        app = bot.build_application("123:ABC")
        first = [h for h in app.handlers if getattr(h, "group", 0) == -1]
        self.assertEqual(len(first), 1)
        self.assertIs(first[0].callback, bot.handle_moderation)


class TestBotSilentForAdmin(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        moderation._ADMIN_CACHE.clear()
        bot._SEEN = bot._SeenMessages()
        for p in (mock.patch.object(bot, "GEMINI_API_KEY", ""),
                  mock.patch.dict(os.environ, {"RESTRICT_TO_GROUP": "", "ADMIN_CHAT_ID": "-100999"}, clear=False)):
            p.start()
            self.addCleanup(p.stop)

    async def ask(self, message, context=None):
        context = context or ctx()
        await bot.handle_group_message(NS(effective_message=message, effective_chat=CHAT), context)
        return context

    async def test_admin_question_gets_no_answer(self):
        m = msg("كيفاش نسجل في مينا؟", user="MaynaDz", user_id=1)
        c = await self.ask(m)
        m.reply_text.assert_not_awaited()
        c.bot.send_message.assert_not_awaited()

    async def test_other_group_admin_still_gets_answer(self):
        # only @MaynaDz is ignored; other group admins are answered like members
        m = msg("كيفاش نسجل في مينا؟", user="other", user_id=42)
        c = await self.ask(m, ctx(admin_ids=[42]))
        self.assertTrue(m.reply_text.await_count > 0 or c.bot.copy_message.await_count > 0)

    async def test_member_still_gets_answer(self):
        m = msg("كيفاش نسجل في مينا؟")
        c = await self.ask(m)
        self.assertTrue(m.reply_text.await_count > 0 or c.bot.copy_message.await_count > 0)

    async def test_reply_to_admin_message_is_answered_by_default(self):
        admin_msg = msg("جاوبتك", user="MaynaDz", user_id=1)
        m = msg("كيفاش نسجل في مينا؟", reply_to_message=admin_msg)
        c = await self.ask(m)
        self.assertTrue(m.reply_text.await_count > 0 or c.bot.copy_message.await_count > 0)

    async def test_reply_to_admin_ignored_when_flag_set(self):
        admin_msg = msg("جاوبتك", user="MaynaDz", user_id=1)
        m = msg("كيفاش نسجل في مينا؟", reply_to_message=admin_msg)
        with mock.patch.dict(os.environ, {"IGNORE_REPLIES_TO_ADMIN": "1"}):
            c = await self.ask(m)
        m.reply_text.assert_not_awaited()
        c.bot.send_message.assert_not_awaited()

    async def test_unclear_question_points_to_admin(self):
        m = msg("blabla qsdqsd xyzxyz؟")
        c = await self.ask(m)
        texts = [call.args[0] for call in m.reply_text.await_args_list if call.args]
        self.assertTrue(any("@MaynaDz" in t for t in texts), texts)


class TestWelcomeDisappears(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_is_deleted_after_10_seconds(self):
        self.assertEqual(bot.WELCOME_LIFETIME_SECONDS, 10)
        welcome = NS(delete=AsyncMock())
        message = NS(
            new_chat_members=[NS(is_bot=False, first_name="Sami"), NS(is_bot=True, first_name="SomeBot")],
            reply_text=AsyncMock(return_value=welcome),
        )
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with mock.patch.object(bot.asyncio, "sleep", fake_sleep):
            await bot.handle_new_members(NS(effective_message=message), NS())
            await bot.asyncio.gather(*list(bot._BACKGROUND_TASKS))
        message.reply_text.assert_awaited_once()      # no welcome for the bot member
        self.assertEqual(sleeps, [10])
        welcome.delete.assert_awaited_once()

    async def test_failed_delete_does_not_crash(self):
        welcome = NS(delete=AsyncMock(side_effect=Exception("gone")))
        await bot._delete_later(welcome, 0)


if __name__ == "__main__":
    unittest.main()
