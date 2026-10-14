# -*- coding: utf-8 -*-
"""Routing through the REAL python-telegram-bot dispatcher and filters (Telegram is never contacted:
Bot.send_message is replaced by a mock). Skipped automatically when only the stub is available.

This proves what the mocked-handler tests cannot: that a plain group message actually passes the
registered filters and reaches handle_group_message.
"""
import os
import sys
import unittest
from unittest import mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import telegram
    from telegram import Bot, Update
    REAL = hasattr(telegram, "__version__") and hasattr(telegram, "Bot")
except ImportError:
    REAL = False


def _group_update(text, message_id=1, chat_type="supergroup"):
    return {
        "update_id": message_id,
        "message": {
            "message_id": message_id,
            "date": 1760400000,
            "chat": {"id": -1001234, "type": chat_type, "title": "Mayna Group"},
            "from": {"id": 77, "is_bot": False, "first_name": "Ali", "username": "ali"},
            "text": text,
        },
    }


@unittest.skipUnless(REAL, "real python-telegram-bot is not installed (only the stub is available)")
class TestRealDispatcherRouting(unittest.IsolatedAsyncioTestCase):
    async def _run(self, text, message_id=1, chat_type="supergroup"):
        import bot
        bot._SEEN = bot._SeenMessages()
        app = bot.build_application("123456:TEST-TOKEN-NOT-REAL")
        update = Update.de_json(_group_update(text, message_id, chat_type), app.bot)
        send = AsyncMock(return_value=None)
        with mock.patch.object(Bot, "send_message", send), mock.patch.dict(
            os.environ, {"ADMIN_CHAT_ID": "", "GROUP_CHAT_ID": ""}, clear=False
        ), mock.patch.object(bot, "GEMINI_API_KEY", ""):
            await app.process_update(update)
        return send

    async def test_plain_group_message_reaches_handler_and_gets_oran_price(self):
        send = await self._run("شحال التوصيل لوهران؟")
        self.assertEqual(send.await_count, 1)
        text = send.await_args.kwargs.get("text") or send.await_args.args[1]
        self.assertIn("600 دج", text)
        self.assertIn("350 دج", text)

    async def test_french_question_reaches_handler(self):
        send = await self._run("Prix livraison Oran", message_id=2)
        self.assertEqual(send.await_count, 1)

    async def test_private_chat_is_not_handled_by_group_handler(self):
        send = await self._run("شحال التوصيل لوهران؟", message_id=3, chat_type="private")
        self.assertEqual(send.await_count, 0)


if __name__ == "__main__":
    unittest.main()
