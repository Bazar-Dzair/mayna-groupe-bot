# -*- coding: utf-8 -*-
"""Product spec search: photo+question, photo only, text question, Gemini failure, search failure,
unidentifiable product, plus the "no invented specs" guarantees.

Gemini and Telegram are NEVER contacted: product_search._post_gemini is replaced by a fake and any
accidental call to urllib raises. Product names/specs below are fictional test data.
"""
import io
import json
import os
import sys
import time
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_bot_flow import ADMIN, make_update  # noqa: E402
from tests import test_bot_flow  # noqa: E402

import bot  # noqa: E402
import product_search as ps  # noqa: E402

SOURCE = "https://example.com/tb-100-specs"
IDENT_OK = {
    "is_product": True, "name": "Air Fryer", "brand": "TestBrand", "model": "TB-100",
    "reference": "", "category": "air fryer", "confidence": "high", "requested_specs": ["القوة"],
}
IDENT_NO_MODEL = dict(IDENT_OK, model="", confidence="low")
WEB_OK = {
    "exact_model_match": True,
    "specs": [
        {"label": "القوة", "value": "1400 W", "confirmed": True},
        {"label": "الوزن", "value": "4 kg", "confirmed": False},
    ],
}


def fake_gemini(ident=None, web=None, sources=(SOURCE,), ident_exc=None, web_exc=None, calls=None):
    def _post(payload, api_key, model=None, timeout=40):
        is_web = "tools" in payload
        if calls is not None:
            calls.append("web" if is_web else "identify")
        if is_web:
            if web_exc:
                raise web_exc
            return {
                "candidates": [{
                    "content": {"parts": [{"text": json.dumps(web)}]},
                    "groundingMetadata": {"groundingChunks": [{"web": {"uri": u, "title": "example.com"}} for u in sources]},
                }]
            }
        if ident_exc:
            raise ident_exc
        return {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(ident) + "\n```"}]}}]}
    return _post


def attach_photo(update, ctx, data=b"JPEGDATA", fail=False):
    update.effective_message.photo = [
        SimpleNamespace(file_id="small", file_size=100),
        SimpleNamespace(file_id="big", file_size=5000),
    ]
    if fail:
        ctx.bot.get_file = AsyncMock(side_effect=bot.TelegramError("file too big"))
    else:
        ctx.bot.get_file = AsyncMock(return_value=SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(data))))


class ProductBase(test_bot_flow.FlowBase):
    def setUp(self):
        super().setUp()
        ps._PAUSED_UNTIL = 0.0
        for patcher in (
            mock.patch.object(bot, "GEMINI_API_KEY", "test-key"),
            mock.patch.object(ps, "CATALOG_FILE", "/nonexistent/catalog.json"),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("real network call in a test")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def replies(self, ev):
        return [e[1] for e in ev if e[0] == "reply"]

    def admin_events(self, ev):
        return [e for e in ev if e[0] in ("send", "copy") and e[1] == int(ADMIN)]


class TestPhotoWithQuestion(ProductBase):
    async def test_confirmed_specs_are_separated_from_unverified_and_source_is_linked(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, ["identify", "web"])
        ctx.bot.get_file.assert_awaited_once_with("big")  # largest photo is downloaded
        text = self.replies(ev)[0]
        self.assertIn("TB-100", text)
        self.assertIn("1400 W", text)
        self.assertIn(SOURCE, text)
        self.assertLess(text.index("✅"), text.index("1400 W"))
        self.assertLess(text.index("1400 W"), text.index("⚠️"))
        self.assertLess(text.index("⚠️"), text.index("4 kg"))  # unverified value sits under the warning
        self.assertEqual(self.admin_events(ev), [])  # nothing escalated

    async def test_image_sent_as_file_is_handled_too(self):
        update, ctx, ev = make_update("", caption="شحال قوة هذا الجهاز؟")
        update.effective_message.document = SimpleNamespace(file_id="doc1", mime_type="image/png")
        attach_photo(update, ctx)
        update.effective_message.photo = None
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK)):
            await bot.handle_group_message(update, ctx)
        ctx.bot.get_file.assert_awaited_once_with("doc1")
        self.assertIn("1400 W", self.replies(ev)[0])

    async def test_photo_download_failure_is_escalated_not_silent(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx, fail=True)
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK)):
            await bot.handle_group_message(update, ctx)
        self.assertTrue(self.admin_events(ev))
        self.assertIn("للمشرفين", self.replies(ev)[-1])


class TestPhotoWithoutQuestion(ProductBase):
    async def test_no_question_no_reply_and_no_gemini_call(self):
        update, ctx, ev = make_update("", photo=True)
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(ev, [])
        self.assertEqual(calls, [])


class TestTextQuestion(ProductBase):
    async def test_text_question_about_a_product(self):
        update, ctx, ev = make_update("واش هي مواصفات TB-100؟")
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, ["identify", "web"])
        self.assertIn("1400 W", self.replies(ev)[0])

    async def test_text_question_without_any_model_asks_for_it(self):
        update, ctx, ev = make_update("شحال قوة الخلاط تاع كوزينة؟")
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_NO_MODEL, WEB_OK)):
            await bot.handle_group_message(update, ctx)
        self.assertIn("رقم الموديل", self.replies(ev)[0])
        self.assertEqual(self.admin_events(ev), [])


class TestFailures(ProductBase):
    async def test_gemini_failure_goes_to_admin_with_photo_and_user_is_told(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(ident_exc=ps.GeminiUnavailable("http 429"), calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, ["identify"])
        admin = self.admin_events(ev)
        self.assertEqual([a[0] for a in admin], ["send", "copy"])  # text + the photo itself
        self.assertIn("شحال قوة هذا الجهاز", admin[0][2]["text"])
        self.assertIn("تحقق", self.replies(ev)[-1])

    async def test_search_failure_goes_to_admin(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, web_exc=ps.GeminiUnavailable("Timeout"))):
            await bot.handle_group_message(update, ctx)
        self.assertTrue(self.admin_events(ev))
        self.assertIn("فشل البحث", self.admin_events(ev)[0][2]["text"])
        self.assertNotIn("1400", " ".join(self.replies(ev)))

    async def test_user_is_not_told_admin_was_notified_when_it_was_not(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        ctx.bot.send_message = AsyncMock(side_effect=bot.TelegramError("chat not found"))
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, web_exc=ps.GeminiUnavailable("Timeout"))):
            await bot.handle_group_message(update, ctx)
        self.assertIn("ما قدرتش نوصل السؤال للمشرفين", self.replies(ev)[-1])

    async def test_no_gemini_key_photo_goes_to_admin(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        with mock.patch.object(bot, "GEMINI_API_KEY", ""):
            await bot.handle_group_message(update, ctx)
        self.assertTrue(self.admin_events(ev))

    async def test_product_cannot_be_identified_asks_for_label_photo_and_does_not_search(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال الوزن؟")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_NO_MODEL, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, ["identify"])  # no web search on a guessed product
        self.assertIn("الملصق", self.replies(ev)[0])
        self.assertEqual(self.admin_events(ev), [])

    async def test_wrong_model_found_is_not_presented_as_the_product(self):
        update, ctx, ev = make_update("واش هي مواصفات TB-100؟")
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, dict(WEB_OK, exact_model_match=False))):
            await bot.handle_group_message(update, ctx)
        self.assertNotIn("1400", " ".join(self.replies(ev)))
        self.assertTrue(self.admin_events(ev))

    async def test_confirmed_spec_without_any_source_link_is_not_trusted(self):
        update, ctx, ev = make_update("واش هي مواصفات TB-100؟")
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, sources=())):
            await bot.handle_group_message(update, ctx)
        self.assertNotIn("1400", " ".join(self.replies(ev)))
        self.assertTrue(self.admin_events(ev))

    async def test_only_unverified_specs_are_not_given_as_an_answer(self):
        web = {"exact_model_match": True, "specs": [{"label": "الوزن", "value": "4 kg", "confirmed": False}]}
        update, ctx, ev = make_update("واش هي مواصفات TB-100؟")
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, web)):
            await bot.handle_group_message(update, ctx)
        self.assertNotIn("4 kg", " ".join(self.replies(ev)))
        self.assertTrue(self.admin_events(ev))

    async def test_crash_in_product_flow_falls_back_to_normal_flow(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال قوة هذا الجهاز؟")
        attach_photo(update, ctx)
        with mock.patch.object(bot.product_search, "search_product", side_effect=RuntimeError("boom")):
            with self.assertLogs("mayna-assistant", level="ERROR"):
                await bot.handle_group_message(update, ctx)
        self.assertTrue(self.admin_events(ev))  # old behaviour: unmatched photo goes to admin


class TestExistingFeaturesKeepPriority(ProductBase):
    async def test_tutorial_question_with_photo_still_gets_the_tutorial(self):
        update, ctx, ev = make_update("", photo=True, caption="كيفاش نسحب العمولة؟")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, [])
        self.assertEqual([e[2]["message_id"] for e in ev if e[0] == "copy"], [15])

    async def test_delivery_price_question_with_photo_still_gets_the_price(self):
        update, ctx, ev = make_update("", photo=True, caption="شحال التوصيل لوهران؟")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, [])
        self.assertIn("600 دج", self.replies(ev)[0])

    async def test_greeting_with_photo_still_gets_greeting(self):
        update, ctx, ev = make_update("", photo=True, caption="السلام عليكم")
        attach_photo(update, ctx)
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK)):
            await bot.handle_group_message(update, ctx)
        self.assertIn("وعليكم السلام", self.replies(ev)[0])

    async def test_non_product_photo_falls_through_to_admin_as_before(self):
        update, ctx, ev = make_update("", photo=True, caption="شكرا بزاف")
        attach_photo(update, ctx)
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(dict(IDENT_OK, is_product=False), WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, ["identify"])
        self.assertTrue(self.admin_events(ev))
        self.assertIn("وصلنا السؤال للمشرفين", self.replies(ev)[-1])

    async def test_plain_unrelated_text_never_calls_gemini_vision_flow(self):
        update, ctx, ev = make_update("كيفاش نفتح حساب؟")
        calls = []
        with mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            await bot.handle_group_message(update, ctx)
        self.assertEqual(calls, [])
        self.assertEqual([e[2]["message_id"] for e in ev if e[0] == "copy"], [334])


class TestModule(unittest.TestCase):
    def setUp(self):
        ps._PAUSED_UNTIL = 0.0
        self.addCleanup(setattr, ps, "_PAUSED_UNTIL", 0.0)

    def test_spec_question_detection(self):
        for q in ("شحال قوته؟", "واش هي مواصفات هذا المنتج", "quel est le poids ?", "dimensions du produit", "كم الوزن؟"):
            self.assertTrue(ps.looks_like_spec_question(q), q)
        for q in ("كيفاش نسجل؟", "السلام عليكم", "وقتاش نخلصو", ""):
            self.assertFalse(ps.looks_like_spec_question(q), q)

    def test_text_hint_needs_a_real_model_token(self):
        self.assertEqual(ps._text_hint("مواصفات WH-1000XM5").model, "WH-1000XM5")
        self.assertIsNone(ps._text_hint("مواصفات الخلاط تاع كوزينة"))

    def test_http_429_pauses_gemini_and_key_is_in_header_only(self):
        seen = {}

        def boom(req, timeout=None):
            seen["url"], seen["key"] = req.full_url, req.get_header("X-goog-api-key")
            raise urllib.error.HTTPError(req.full_url, 429, "quota", {}, io.BytesIO(b""))

        with mock.patch("urllib.request.urlopen", side_effect=boom):
            with self.assertRaises(ps.GeminiUnavailable):
                ps._post_gemini({"contents": []}, "SECRET")
        self.assertEqual(seen["key"], "SECRET")
        self.assertNotIn("SECRET", seen["url"])
        self.assertGreater(ps._PAUSED_UNTIL, time.time())
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("must not be called while paused")):
            with self.assertRaises(ps.GeminiUnavailable):
                ps._post_gemini({"contents": []}, "SECRET")

    def test_garbled_gemini_answer_is_rejected(self):
        bad = {"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]}
        with mock.patch.object(ps, "_post_gemini", return_value=bad):
            with self.assertRaises(ps.GeminiUnavailable):
                ps.identify("x", None, "image/jpeg", "k")

    def test_local_catalog_is_searched_before_the_web(self):
        catalog = [{"name": "Test Fryer", "model": "TB-100", "url": "https://mayna.example/p/1", "specs": {"القوة": "1400 W"}}]
        calls = []
        with mock.patch.object(ps, "load_catalog", return_value=catalog), \
             mock.patch.object(ps, "_post_gemini", fake_gemini(IDENT_OK, WEB_OK, calls=calls)):
            out = ps.search_product("مواصفات TB100", None, api_key="k")
        self.assertEqual(out.kind, "answer")
        self.assertEqual(calls, ["identify"])  # no web search needed
        self.assertIn("كتالوج Mayna", out.text)
        self.assertIn("https://mayna.example/p/1", out.text)

    def test_missing_or_broken_catalog_is_harmless(self):
        import tempfile
        self.assertEqual(ps.load_catalog("/nonexistent/catalog.json"), [])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{broken")
        self.addCleanup(os.unlink, fh.name)
        with self.assertLogs("mayna-assistant.product", level="ERROR"):
            self.assertEqual(ps.load_catalog(fh.name), [])

    def test_shipped_catalog_is_valid_json(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "products_catalog.json")
        with open(path, encoding="utf-8") as fh:
            self.assertIsInstance(json.load(fh)["products"], list)

    def test_image_ref_prefers_the_largest_photo_and_accepts_image_documents(self):
        msg = SimpleNamespace(photo=[SimpleNamespace(file_id="a", file_size=10), SimpleNamespace(file_id="b", file_size=20)])
        self.assertEqual(bot._image_ref(msg), ("b", "image/jpeg"))
        doc = SimpleNamespace(photo=None, document=SimpleNamespace(file_id="d", mime_type="image/webp"))
        self.assertEqual(bot._image_ref(doc), ("d", "image/webp"))
        pdf = SimpleNamespace(photo=None, document=SimpleNamespace(file_id="p", mime_type="application/pdf"))
        self.assertIsNone(bot._image_ref(pdf))
        self.assertIsNone(bot._image_ref(SimpleNamespace(photo=None)))


if __name__ == "__main__":
    unittest.main()
