"""Best-effort DHD tracking lookup using the public tracking form.

If the site changes its form or blocks automated requests, callers can still provide
members with the official tracking page rather than inventing a shipment status.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
import re

TRACKING_URL = "https://platform.dhd-dz.com/suivi/"
USER_AGENT = "Mozilla/5.0 (compatible; MaynaDzBot/1.0)"

class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.forms=[]; self.form=None; self.visible=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag == "form":
            self.form={"action":a.get("action", ""), "method":a.get("method", "get").lower(), "fields":{}}
            self.forms.append(self.form)
        elif tag == "input" and self.form is not None and a.get("name"):
            self.form["fields"][a["name"]]=a.get("value", "")
    def handle_endtag(self, tag):
        if tag == "form": self.form=None
    def handle_data(self, data):
        s=data.strip()
        if s: self.visible.append(s)

def lookup_tracking(number: str) -> dict:
    """Return {status, details, url}; status is None when automated lookup fails."""
    opener=build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        req=Request(TRACKING_URL, headers={"User-Agent":USER_AGENT})
        with opener.open(req, timeout=12) as response:
            html=response.read(2_000_000).decode("utf-8", "replace")
            page_url=response.geturl()
        parser=_FormParser(); parser.feed(html)
        form=None; field=None
        for f in parser.forms:
            for name in f["fields"]:
                if any(k in name.lower() for k in ("tracking", "suivi", "code", "colis")):
                    form=f; field=name; break
            if form: break
        if not form:
            return {"status":None,"details":"","url":TRACKING_URL}
        fields=dict(form["fields"]); fields[field]=number
        action=urljoin(page_url, form["action"] or page_url)
        method=form["method"]
        if method == "post":
            data=urlencode(fields).encode()
            req=Request(action, data=data, headers={"User-Agent":USER_AGENT,"Referer":page_url,"Content-Type":"application/x-www-form-urlencoded"})
        else:
            from urllib.parse import urlsplit, urlunsplit, parse_qsl
            parts=urlsplit(action); query=dict(parse_qsl(parts.query)); query.update(fields)
            from urllib.parse import quote
            action=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),parts.fragment))
            req=Request(action, headers={"User-Agent":USER_AGENT,"Referer":page_url})
        with opener.open(req, timeout=12) as response:
            result=response.read(2_000_000).decode("utf-8", "replace")
        out=_FormParser(); out.feed(result)
        text=" ".join(out.visible)
        # Only report a status when the response visibly contains a known shipment status.
        statuses=[
            (r"colis\s+livr[ée]", "تم تسليم الطرد (Colis livré)"),
            (r"en\s+cours\s+de\s+livraison", "الطرد خرج للتوصيل (En cours de livraison)"),
            (r"arriv[ée]\s+[àa]\s+la\s+station", "وصل إلى المحطة الجهوية (Arrivé à la station régionale)"),
            (r"en\s+attente\s+d['’]envoi", "الطرد في انتظار الإرسال (En attente d'envoi)"),
            (r"retour", "توجد إشارة إلى إرجاع الطرد (Retour)"),
        ]
        for pattern,label in statuses:
            if re.search(pattern,text,re.I):
                return {"status":label,"details":text[:1400],"url":action}
        return {"status":None,"details":"","url":TRACKING_URL}
    except Exception:
        return {"status":None,"details":"","url":TRACKING_URL}

def extract_tracking_number(text: str):
    s=(text or "").strip()
    # Treat standalone tracking-like codes as tracking numbers; avoid ordinary short numbers.
    if re.fullmatch(r"(?i)(?:tracking\s*)?(?:dhd)?[a-z0-9-]{10,32}", s):
        cleaned=re.sub(r"(?i)^tracking\s*", "", s).strip()
        return cleaned if any(c.isdigit() for c in cleaned) else None
    # In explicit tracking context, accept a code embedded in a sentence.
    if re.search(r"tracking|تتبع|suivi",s,re.I):
        m=re.search(r"(?i)(?:dhd)?[a-z0-9-]{10,32}",s)
        if m and any(c.isdigit() for c in m.group()): return m.group()
    return None
