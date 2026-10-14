# -*- coding: utf-8 -*-
"""Package tracking for DHD (https://platform.dhd-dz.com/suivi/).

- find_tracking_numbers(text): detects numbers like DHDCQI726101420522909 in a message.
- lookup(number): asks the DHD tracking site and returns a TrackingResult.
- build_reply(result): Arabic/Darija reply for the group.

The site is a third party. Its exact request format must be confirmed with
`python tracking.py <number>` (prints the raw response) - see README-TRACKING-AR.md.
Everything network-related is isolated in `_fetch_raw`, so only that function
needs a change if the site's format differs from the default below.
"""
import html as html_lib
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("mayna-assistant")

TRACK_PAGE = os.getenv("DHD_TRACK_PAGE", "https://platform.dhd-dz.com/suivi/")
# Optional: exact endpoint once known. {n} is replaced by the tracking number.
#   GET  e.g. DHD_TRACK_URL=https://platform.dhd-dz.com/api/suivi/{n}
#   POST e.g. DHD_TRACK_POST_URL=https://.../suivi/  + DHD_TRACK_FIELD=tracking
TRACK_URL = os.getenv("DHD_TRACK_URL", "").strip()
TRACK_POST_URL = os.getenv("DHD_TRACK_POST_URL", "").strip()
TRACK_FIELD = os.getenv("DHD_TRACK_FIELD", "tracking").strip()
TIMEOUT = 15
MAX_NUMBERS_PER_MESSAGE = 3

# 2-10 letters followed by 8+ digits (DHDCQI726101420522909, DHD..., etc.), no letters/digits around it.
TRACKING_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,10}\d{8,})(?![A-Za-z0-9])")

# status buckets, checked in order (first match wins); keywords are lowercase / Arabic / French
STAGES = [
    ("delivered", "✅ تم تسليم الطلبية للزبون",
     ("livré", "livre", "livree", "delivered", "تم التسليم", "تم تسليم", "مسلم")),
    ("returned", "↩️ الطلبية مرجّعة (راجعة للمرسل)",
     ("retour", "returned", "رجوع", "مرتجع", "راجع")),
    ("out_for_delivery", "🛵 الطلبية عند الموزّع (في طريقها للزبون)",
     ("en cours de livraison", "out for delivery", "chez le livreur", "livreur", "distribution",
      "en livraison", "عند الموزع", "قيد التوصيل", "في طريق التسليم")),
    ("at_office", "🏢 الطلبية وصلت للمكتب (في انتظار التسليم)",
     ("au bureau", "agence", "bureau", "stop desk", "point relais", "arrivé à destination",
      "arrive a destination", "في المكتب", "وصل للمكتب", "وصلت للمكتب")),
    ("in_transit", "🚚 الطلبية في طور الشحن (في الطريق)",
     ("en transit", "in transit", "expédié", "expedie", "transfert", "en cours d'acheminement",
      "acheminement", "en route", "في الطريق", "قيد الشحن", "في طور الشحن", "تم الشحن")),
    ("preparing", "📦 الطلبية قيد التحضير / الاستلام من المورّد",
     ("en préparation", "en preparation", "prêt à expédier", "pret a expedier", "ramassé", "ramasse",
      "collecté", "créé", "cree", "قيد التحضير", "تم الاستلام", "جاهز")),
]


@dataclass
class TrackingResult:
    number: str
    ok: bool = False                 # True only if we found a real status
    stage: str = ""                  # key from STAGES, or "" if unknown
    stage_text: str = ""             # Arabic label for the stage
    raw_status: str = ""             # latest status text exactly as the site shows it
    history: List[str] = field(default_factory=list)  # latest events, newest first
    error: str = ""                  # "not_found" | "unreachable" | "unreadable"


def find_tracking_numbers(text: str) -> List[str]:
    """Unique tracking numbers in the message, upper-cased, in order of appearance."""
    seen, out = set(), []
    for m in TRACKING_RE.finditer(text or ""):
        number = m.group(1).upper()
        if number not in seen:
            seen.add(number)
            out.append(number)
    return out[:MAX_NUMBERS_PER_MESSAGE]


def classify_status(status_text: str):
    """Map the site's status wording to (stage key, Arabic label); ("", "") if unknown."""
    low = (status_text or "").lower()
    for key, label, words in STAGES:
        if any(w in low for w in words):
            return key, label
    return "", ""


# ---------------------------------------------------------------------------
# Network (the only part that depends on the DHD site)
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _open(request):
    with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode(charset, "replace")


def _fetch_raw(number: str) -> str:
    """Return the raw response body (JSON or HTML) for this tracking number. Raises on network errors."""
    headers = {"User-Agent": _UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
               "Accept-Language": "fr,ar;q=0.8,en;q=0.6"}
    if TRACK_URL:
        url = TRACK_URL.replace("{n}", urllib.parse.quote(number))
        return _open(urllib.request.Request(url, headers=headers))[2]
    if TRACK_POST_URL:
        data = urllib.parse.urlencode({TRACK_FIELD: number}).encode()
        return _open(urllib.request.Request(TRACK_POST_URL, data=data, headers=headers, method="POST"))[2]
    # Default guess: the public page accepts the number as a query parameter.
    # If the site works differently, run `python tracking.py <number>` and set DHD_TRACK_URL / DHD_TRACK_POST_URL.
    url = TRACK_PAGE + ("&" if "?" in TRACK_PAGE else "?") + urllib.parse.urlencode({"tracking": number})
    return _open(urllib.request.Request(url, headers=headers))[2]



def _fetch_with_browser(number: str) -> str:
    """Fallback: open the page in headless Chromium, type the number, return JSON seen on the wire or page text.
    Needs `pip install playwright` + `playwright install --with-deps chromium`. Raises if unavailable."""
    from playwright.sync_api import sync_playwright  # imported lazily: optional dependency

    captured = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=_UA, locale="fr-FR")

            def on_response(resp):
                try:
                    if "json" in (resp.headers.get("content-type") or "") and number.lower() in resp.text().lower():
                        captured.append(resp.text())
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(TRACK_PAGE, wait_until="networkidle", timeout=30000)
            box = page.locator("input:visible:not([type=hidden]):not([type=checkbox]):not([type=radio])").first
            box.fill(number, timeout=10000)
            button = page.locator(
                "button:visible, input[type=submit]:visible"
            ).filter(has_text=re.compile(r"suiv|track|rechercher|search|بحث|تتبع|ok", re.I))
            if button.count():
                button.first.click()
            else:
                box.press("Enter")
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_timeout(2500)
            if captured:
                return captured[-1]
            return page.inner_text("body")
        finally:
            browser.close()

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_STATUS_KEYS = ("status", "statut", "state", "etat", "état", "label", "libelle", "libellé", "situation")
_DATE_KEYS = ("date", "created_at", "updated_at", "datetime", "time")


def _walk(obj, events):
    """Collect (date, status) pairs from arbitrary JSON."""
    if isinstance(obj, dict):
        low = {str(k).lower(): v for k, v in obj.items()}
        status = next((low[k] for k in _STATUS_KEYS if isinstance(low.get(k), str) and low[k].strip()), None)
        date = next((str(low[k]) for k in _DATE_KEYS if low.get(k)), "")
        if status:
            events.append((date, status.strip()))
        for v in obj.values():
            _walk(v, events)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, events)


def _strip_html(body: str) -> str:
    body = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", body)
    body = re.sub(r"(?s)<[^>]+>", "\n", body)
    body = html_lib.unescape(body)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", body)).strip()


def parse_response(number: str, body: str) -> TrackingResult:
    """Turn the site's answer (JSON or HTML) into a TrackingResult. Never raises."""
    res = TrackingResult(number=number)
    body = body or ""
    events = []
    try:
        _walk(json.loads(body), events)
    except ValueError:
        text = _strip_html(body)
        if number.lower() not in text.lower() and not any(w in text.lower() for w in ("statut", "status", "livr")):
            res.error = "unreadable"
            return res
        if re.search(r"(introuvable|aucun colis|not found|non trouv|غير موجود|لم يتم العثور)", text, re.I):
            res.error = "not_found"
            return res
        for line in text.splitlines():
            line = line.strip()
            if 3 <= len(line) <= 120 and classify_status(line)[0]:
                events.append(("", line))
    if not events:
        res.error = "unreadable"
        return res
    # Heuristic: events are listed newest-first or oldest-first; prefer one with the latest date if parseable,
    # otherwise take the first (most trackers list newest first). Confirm with real data (see README).
    res.history = [f"{d} {s}".strip() for d, s in events[:5]]
    res.raw_status = events[0][1]
    res.stage, res.stage_text = classify_status(res.raw_status)
    res.ok = True
    return res


def lookup(number: str) -> TrackingResult:
    """Blocking call (run it with asyncio.to_thread). Never raises.
    1) plain HTTP request; 2) if that gives no readable status, a real headless browser."""
    result = TrackingResult(number=number, error="unreachable")
    try:
        body = _fetch_raw(number)
        result = parse_response(number, body)
        if not result.ok:
            logger.warning("DHD tracking plain request unreadable (%s). Body start: %r",
                           result.error, (body or "")[:300])
    except urllib.error.HTTPError as exc:
        logger.warning("DHD tracking plain request HTTP %s for %s", exc.code, number)
        result = TrackingResult(number=number, error="not_found" if exc.code == 404 else "unreachable")
    except Exception as exc:
        logger.warning("DHD tracking plain request failed: %s", type(exc).__name__)
    if result.ok or result.error == "not_found" and not os.getenv("DHD_FORCE_BROWSER"):
        return result
    try:
        body = _fetch_with_browser(number)
        browsed = parse_response(number, body)
        if not browsed.ok:
            logger.warning("DHD tracking browser result unreadable (%s). Text start: %r",
                           browsed.error, (body or "")[:500])
        return browsed if (browsed.ok or browsed.error == "not_found") else result
    except ImportError:
        logger.warning("Playwright not installed: browser fallback skipped")
    except Exception as exc:
        logger.warning("DHD tracking browser fallback failed: %s: %s", type(exc).__name__, str(exc)[:200])
    return result


def build_reply(results: List[TrackingResult]) -> str:
    parts = []
    for r in results:
        head = f"🔎 رقم التتبع: {r.number}"
        if r.ok:
            line = r.stage_text or "ℹ️ حالة الطلبية"
            body = f"{head}\n{line}\nالحالة عند شركة التوصيل: {r.raw_status}"
        elif r.error == "not_found":
            body = f"{head}\nما لقيتش هذا الرقم في موقع التتبع. تأكد أن الرقم صحيح."
        else:
            body = (f"{head}\nما قدرتش نجيب حالة الطلبية حاليا من موقع التتبع. "
                    f"جرب بنفسك هنا:\n{TRACK_PAGE}")
        parts.append(body)
    return "\n\n".join(parts)


if __name__ == "__main__":  # diagnostic: python tracking.py DHDCQI726101420522909
    import sys
    n = (sys.argv[1] if len(sys.argv) > 1 else "").upper()
    raw = _fetch_raw(n)
    print(raw[:3000])
    print("-----")
    print(parse_response(n, raw))
