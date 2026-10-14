# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tracking  # noqa: E402


class TrackingTests(unittest.TestCase):
    def test_detects_number(self):
        self.assertEqual(tracking.find_tracking_numbers("وين وصلت DHDCQI726101420522909 ؟"), ["DHDCQI726101420522909"])
        self.assertEqual(tracking.find_tracking_numbers("dhdcqi726101420522909"), ["DHDCQI726101420522909"])
        self.assertEqual(tracking.find_tracking_numbers("DHDCQI726101420522909 و DHDCQI726101420522909"), ["DHDCQI726101420522909"])

    def test_ignores_normal_text(self):
        for t in ("شحال التوصيل لوهران؟", "رقمي 0555123456", "mayna2024", "كيفاش نسجل"):
            self.assertEqual(tracking.find_tracking_numbers(t), [], t)

    def test_stage_mapping(self):
        self.assertEqual(tracking.classify_status("Livré")[0], "delivered")
        self.assertEqual(tracking.classify_status("En cours de livraison")[0], "out_for_delivery")
        self.assertEqual(tracking.classify_status("Arrivé au bureau")[0], "at_office")
        self.assertEqual(tracking.classify_status("En transit")[0], "in_transit")
        self.assertEqual(tracking.classify_status("Retour")[0], "returned")

    def test_parse_json(self):
        body = '{"tracking":"X","history":[{"date":"2026-10-14","status":"En cours de livraison"},{"date":"2026-10-13","status":"En transit"}]}'
        r = tracking.parse_response("DHDCQI726101420522909", body)
        self.assertTrue(r.ok)
        self.assertEqual(r.stage, "out_for_delivery")
        self.assertIn("الموزّع", tracking.build_reply([r]))

    def test_parse_html_not_found_and_garbage(self):
        n = "DHDCQI726101420522909"
        self.assertEqual(tracking.parse_response(n, "<html><body>Colis introuvable DHDCQI726101420522909</body></html>").error, "not_found")
        self.assertEqual(tracking.parse_response(n, "<html><body>hello</body></html>").error, "unreadable")

    def test_unreachable_reply_is_honest(self):
        r = tracking.TrackingResult(number="DHDCQI726101420522909", error="unreachable")
        self.assertIn("ما قدرتش", tracking.build_reply([r]))
        self.assertNotIn("تم تسليم", tracking.build_reply([r]))


if __name__ == "__main__":
    unittest.main()
