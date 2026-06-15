#!/usr/bin/env python3
"""
TouristNetTR lead machine.

Two production modes:
- antalya10: Antalya hotel/accommodation leads, target 10 per run.
- target100: Türkiye target-district tourism/accommodation leads, target 100 per run.

Design:
- No guessed emails.
- Source-visible / HTML-extracted emails only.
- Contact-first leads are allowed; they are not marked email-ready.
- Dedupes against existing CSV outputs in the repository.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import html
import os
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]

EMAIL_RE = re.compile(r"(?i)(?<![A-Z0-9._%+-])([A-Z0-9._%+\-]{1,64}@[A-Z0-9.\-]{2,255}\.[A-Z]{2,24})(?![A-Z0-9._%+-])")
PHONE_RE = re.compile(r"(?x)((?:\+?90|0)?\s*(?:\(?\d{3}\)?[\s.\-]*)\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2})")
CFEMAIL_RE = re.compile(r'data-cfemail=["\']([0-9a-fA-F]+)["\']')
CFEMAIL_HASH_RE = re.compile(r"/cdn-cgi/l/email-protection#([0-9a-fA-F]+)")

NOISE_EMAIL_DOMAINS = {
    "example.com", "domain.com", "sentry.io", "wix.com", "wordpress.com",
    "cloudflare.com", "google.com", "googlemail.com", "schema.org", "w3.org",
    "facebook.com", "instagram.com", "booking.com", "tripadvisor.com", "expedia.com",
}
COMMON_FREE_EMAIL_DOMAINS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yandex.com", "icloud.com", "live.com"}
SECOND_LEVEL_TR = {"com", "net", "org", "edu", "gov", "bel", "k12", "av", "gen", "web"}

EXCLUDED_DOMAINS = (
    "booking.", "tripadvisor.", "expedia.", "agoda.", "hotels.com", "trivago.", "airbnb.com",
    "vrbo.", "etstur.", "tatilsepeti.", "jollytur.", "otelz.", "neredekal.", "setur.",
    "facebook.com", "instagram.com", "youtube.com", "linkedin.com", "wikipedia.org",
    "google.", "yandex.", "mapcarta.", "touristica.", "tatilbudur.", "tourradar.",
)

CONTACT_LINK_KEYWORDS = (
    "contact", "iletisim", "iletişim", "reservation", "rezervasyon", "booking",
    "kvkk", "corporate", "kurumsal", "about", "hakkimizda", "hakkımızda",
    "sales", "satis", "satış", "front-office", "frontoffice", "guest", "misafir",
    "concierge", "partnership", "partner", "agency", "acente",
)

HOTEL_SIGNALS = (
    "hotel", "otel", "boutique", "butik", "apart", "aparthotel", "suite", "suites",
    "rooms", "accommodation", "konaklama", "guest", "misafir", "beach", "spa", "resort",
    "cave hotel", "thermal", "termal", "pansiyon", "konak",
)
PROPERTY_SIGNALS = (
    "villa", "villas", "property management", "airbnb management", "short term rental",
    "short-term rental", "holiday home", "vacation rental", "rental management",
    "villa rental", "kiralık villa", "tatil evi", "mülk yönetimi", "property manager",
)
AGENCY_SIGNALS = (
    "incoming agency", "incoming travel", "dmc", "destination management", "tour operator",
    "travel agency", "private tour", "daily tour", "local tour", "excursion", "tur operator",
    "seyahat acentesi", "turizm acentesi", "acente", "tours", "transfer",
)
TRANSFER_SIGNALS = (
    "airport transfer", "vip transfer", "transfer service", "concierge", "chauffeur",
    "shuttle", "private transfer",
)
NEGATIVE_SIGNALS = (
    "restaurant", "restoran", "cafe", "kafe", "clinic", "klinik", "dental", "hospital",
    "hastane", "car rental", "rent a car", "phone shop", "telefoncu", "sim card",
    "western union", "exchange office", "döviz", "market", "supermarket",
)

ANTALYA_DISTRICTS = [
    "Antalya Kaleiçi", "Antalya Muratpaşa", "Antalya Konyaaltı", "Antalya Lara",
    "Antalya Kundu", "Belek Antalya", "Serik Antalya", "Side Antalya",
    "Manavgat Antalya", "Alanya Antalya", "Kemer Antalya", "Kaş Antalya",
    "Kalkan Antalya", "Finike Antalya", "Demre Antalya", "Adrasan Antalya",
    "Çıralı Antalya", "Olympos Antalya",
]
ANTALYA_SEGMENTS = [
    "boutique hotel contact", "butik otel iletişim", "apart hotel contact",
    "aparthotel iletişim", "3 star hotel contact", "4 star hotel contact",
    "city hotel contact", "beach hotel contact", "small hotel contact",
    "suite hotel iletişim",
]

TARGET_DISTRICTS = [
    "Kaleiçi Antalya", "Muratpaşa Antalya", "Konyaaltı Antalya", "Lara Antalya",
    "Kundu Antalya", "Belek Antalya", "Side Antalya", "Manavgat Antalya",
    "Alanya Antalya", "Kemer Antalya", "Kaş Antalya", "Kalkan Antalya",
    "Sultanahmet İstanbul", "Sirkeci İstanbul", "Fatih İstanbul", "Beyoğlu İstanbul",
    "Galata İstanbul", "Karaköy İstanbul", "Taksim İstanbul", "Şişli İstanbul",
    "Kadıköy İstanbul", "Göreme Nevşehir", "Ürgüp Nevşehir", "Uçhisar Nevşehir",
    "Avanos Nevşehir", "Bodrum Muğla", "Fethiye Muğla", "Ölüdeniz Muğla",
    "Marmaris Muğla", "Datça Muğla", "Dalaman Muğla", "Çeşme İzmir",
    "Alaçatı İzmir", "Konak İzmir", "Selçuk İzmir", "Pamukkale Denizli",
    "Afyon thermal hotel", "Bursa thermal hotel", "Sapanca Sakarya", "Bolu Abant",
    "Trabzon Uzungöl", "Rize Ayder", "Mardin boutique hotel", "Gaziantep boutique hotel",
]
TARGET_SEGMENTS = [
    "villa rental contact", "property management contact", "airbnb management contact",
    "short term rental management contact", "holiday home rental contact",
    "incoming agency contact", "DMC Turkey contact", "local tour operator contact",
    "private tour agency contact", "airport transfer concierge contact",
    "boutique hotel contact", "apart hotel contact", "tourism agency contact",
]

CSV_COLUMNS = [
    "run_date", "run_slot", "mode", "lead_id", "business_name", "city_area",
    "segment", "website", "instagram", "phone", "email", "email_status",
    "email_source_url", "website_source_url", "phone_source_url", "source_urls",
    "first_contact_channel", "integration_point", "fit_score", "status",
    "short_note", "validation_notes",
]


@dataclasses.dataclass
class Candidate:
    name_hint: str
    city_area: str
    segment_query: str
    url: str
    source_query: str


@dataclasses.dataclass
class Lead:
    run_date: str
    run_slot: str
    mode: str
    lead_id: str
    business_name: str
    city_area: str
    segment: str
    website: str
    instagram: str
    phone: str
    email: str
    email_status: str
    email_source_url: str
    website_source_url: str
    phone_source_url: str
    source_urls: str
    first_contact_channel: str
    integration_point: str
    fit_score: int
    status: str
    short_note: str
    validation_notes: str

    def to_row(self) -> dict[str, str | int]:
        return dataclasses.asdict(self)


class SuppressionIndex:
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.domains: set[str] = set()
        self.phones: set[str] = set()
        self.emails: set[str] = set()
        self.instagrams: set[str] = set()

    def add_row(self, row: dict[str, str]) -> None:
        name = norm(row.get("business_name") or row.get("hotel_name") or row.get("company_name") or "")
        if name:
            self.names.add(name)
        domain = registered_domain(domain_of(row.get("website", "")))
        if domain:
            self.domains.add(domain)
        phone = normalize_phone(row.get("phone") or row.get("phone_whatsapp") or "")
        if phone:
            self.phones.add(phone)
        email = clean_email(row.get("email") or row.get("verified_email") or "")
        if email:
            self.emails.add(email)
        insta = normalize_instagram(row.get("instagram", ""))
        if insta:
            self.instagrams.add(insta)

    def duplicate(self, lead: Lead) -> bool:
        return any([
            norm(lead.business_name) in self.names if lead.business_name else False,
            registered_domain(domain_of(lead.website)) in self.domains if lead.website else False,
            normalize_phone(lead.phone) in self.phones if lead.phone else False,
            clean_email(lead.email) in self.emails if lead.email else False,
            normalize_instagram(lead.instagram) in self.instagrams if lead.instagram else False,
        ])


def istanbul_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=3)


def run_date() -> str:
    return istanbul_now().date().isoformat()


def run_slot() -> str:
    return istanbul_now().strftime("%H%M")


def norm(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    return re.sub(r"\s+", " ", value)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def domain_of(url_or_email: str) -> str:
    value = (url_or_email or "").strip().lower()
    if not value:
        return ""
    if "@" in value and "://" not in value:
        value = value.split("@", 1)[1]
    else:
        value = normalize_url(value)
        value = urlparse(value).netloc
    value = value.split("@")[-1].split(":")[0]
    if value.startswith("www."):
        value = value[4:]
    return value.strip(".")


def registered_domain(domain: str) -> str:
    parts = (domain or "").lower().split(".")
    if len(parts) <= 2:
        return domain.lower()
    if len(parts) >= 3 and parts[-1] == "tr" and parts[-2] in SECOND_LEVEL_TR:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if not digits:
        return ""
    if digits.startswith("90") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+9" + digits
    if len(digits) == 10:
        return "+90" + digits
    return "+" + digits if (value or "").strip().startswith("+") else digits


def normalize_instagram(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if "instagram.com" not in value.lower():
        return value if value.startswith("@") else value
    parsed = urlparse(value if "://" in value else "https://" + value)
    handle = parsed.path.strip("/").split("/")[0]
    return f"@{handle.lower()}" if handle else ""


def clean_email(value: str) -> str:
    email = norm(value).replace("mailto:", "").split("?", 1)[0]
    return email.strip(".,;:()[]{}<>\"'")


def decode_cfemail(encoded: str) -> str:
    try:
        data = bytes.fromhex(encoded)
        key = data[0]
        return "".join(chr(b ^ key) for b in data[1:])
    except Exception:
        return ""


def is_noise_email(email: str) -> bool:
    email = clean_email(email)
    domain = domain_of(email)
    local = email.split("@", 1)[0] if "@" in email else ""
    if not email or "@" not in email:
        return True
    if domain in NOISE_EMAIL_DOMAINS:
        return True
    if local in {"example", "test", "yourname", "name", "email", "mail"}:
        return True
    if any(email.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return True
    return False


def soup_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def request_get(session: requests.Session, url: str, timeout: int = 18) -> requests.Response | None:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code >= 400:
            return None
        ctype = response.headers.get("content-type", "").lower()
        if ctype and "text/html" not in ctype and "application/xhtml" not in ctype:
            return None
        return response
    except requests.RequestException:
        return None


def is_excluded_url(url: str) -> bool:
    domain = domain_of(url)
    return not domain or any(x in domain for x in EXCLUDED_DOMAINS)


def search_duckduckgo(session: requests.Session, query: str, limit: int) -> list[str]:
    url = "https://duckduckgo.com/html/"
    try:
        response = session.post(url, data={"q": query}, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code >= 400:
            return []
    except requests.RequestException:
        return []
    soup = BeautifulSoup(response.text, "lxml")
    urls: list[str] = []
    for a in soup.select("a.result__a, a[href]"):
        href = a.get("href") or ""
        if "duckduckgo.com/l/" in href or href.startswith("//duckduckgo.com/l/"):
            parsed = urlparse("https:" + href if href.startswith("//") else href)
            qs = parse_qs(parsed.query)
            if qs.get("uddg"):
                href = unquote(qs["uddg"][0])
        if not href.startswith(("http://", "https://")):
            continue
        if is_excluded_url(href):
            continue
        urls.append(href)
        if len(urls) >= limit:
            break
    return urls


def search_brave(session: requests.Session, query: str, limit: int) -> list[str]:
    token = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not token:
        return []
    try:
        response = session.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20), "country": "TR"},
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            timeout=20,
        )
        if response.status_code >= 400:
            return []
        data = response.json()
    except Exception:
        return []
    urls = []
    for item in data.get("web", {}).get("results", []):
        url = item.get("url") or ""
        if url and not is_excluded_url(url):
            urls.append(url)
    return urls[:limit]


def extract_emails(raw_html: str, soup: BeautifulSoup) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = html.unescape(a["href"])
        if href.lower().startswith("mailto:"):
            email = clean_email(href.split(":", 1)[1].split("?", 1)[0])
            if not is_noise_email(email):
                found.append((email, "mailto"))
    for match in EMAIL_RE.finditer(html.unescape(raw_html)):
        email = clean_email(match.group(1))
        if not is_noise_email(email):
            found.append((email, "html"))
    for encoded in CFEMAIL_RE.findall(raw_html) + CFEMAIL_HASH_RE.findall(raw_html):
        email = clean_email(decode_cfemail(encoded))
        if email and not is_noise_email(email):
            found.append((email, "cloudflare"))
    out, seen = [], set()
    for email, kind in found:
        if email not in seen:
            seen.add(email)
            out.append((email, kind))
    return out


def extract_phone(text: str) -> str:
    for match in PHONE_RE.finditer(text):
        phone = normalize_phone(match.group(1))
        if phone and len(re.sub(r"\D+", "", phone)) >= 10:
            return phone
    return ""


def extract_instagram(soup: BeautifulSoup) -> str:
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "instagram.com" in href.lower():
            return normalize_instagram(href)
    return ""


def candidate_contact_links(base_url: str, soup: BeautifulSoup, max_links: int) -> list[str]:
    base_reg = registered_domain(domain_of(base_url))
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "tel:", "mailto:")):
            continue
        url = urljoin(base_url, href)
        if registered_domain(domain_of(url)) != base_reg:
            continue
        hay = norm(url + " " + a.get_text(" ", strip=True))
        if any(k in hay for k in CONTACT_LINK_KEYWORDS):
            canonical = urlparse(url)._replace(fragment="", query="").geturl()
            if canonical not in seen:
                seen.add(canonical)
                links.append(canonical)
        if len(links) >= max_links:
            break
    return links


def infer_name(title_hint: str, soup: BeautifulSoup, domain: str) -> str:
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        text = title_tag.get_text(" ", strip=True)
    else:
        text = title_hint or domain
    text = re.sub(r"\s+\|.*$|\s+-\s+.*$", "", text).strip()
    return text or domain


def infer_segment(mode: str, query: str, text: str) -> str:
    hay = norm(" ".join([query, text[:5000]]))
    if any(s in hay for s in PROPERTY_SIGNALS):
        return "villa/property-management"
    if any(s in hay for s in AGENCY_SIGNALS):
        if "transfer" in hay:
            return "transfer/concierge"
        return "incoming-agency/dmc/tour-operator"
    if any(s in hay for s in TRANSFER_SIGNALS):
        return "transfer/concierge"
    if any(s in hay for s in HOTEL_SIGNALS):
        if "apart" in hay:
            return "apart-hotel"
        if "boutique" in hay or "butik" in hay:
            return "boutique-hotel"
        if "resort" in hay:
            return "resort-hotel"
        return "hotel/accommodation"
    return "tourism-business"


def mode_fit_ok(mode: str, segment: str, text: str) -> tuple[bool, str]:
    hay = norm(text[:6000])
    has_negative = any(s in hay for s in NEGATIVE_SIGNALS)
    has_positive = any(s in hay for s in HOTEL_SIGNALS + PROPERTY_SIGNALS + AGENCY_SIGNALS + TRANSFER_SIGNALS)
    if has_negative and not has_positive:
        return False, "negative_non_target_signal"
    if mode == "antalya10":
        if segment not in {"hotel/accommodation", "boutique-hotel", "apart-hotel", "resort-hotel"}:
            return False, "antalya_mode_requires_hotel_accommodation"
    if not has_positive:
        return False, "target_fit_not_clear"
    return True, "target_fit_verified"


def foreign_tourist_signal(text: str) -> bool:
    hay = norm(text[:7000])
    return any(x in hay for x in [
        "english", "deutsch", "russian", "русский", "arabic", "français",
        "airport", "transfer", "tour", "reservation", "booking", "eur", "usd",
        "guest", "misafir", "concierge",
    ])


def integration_point(segment: str, text: str) -> str:
    hay = norm(text[:5000])
    if segment == "villa/property-management":
        return "guest pre-arrival message / check-in guide / property QR"
    if segment == "incoming-agency/dmc/tour-operator":
        return "tour confirmation message / voucher / guide handoff"
    if segment == "transfer/concierge":
        return "airport pickup message / WhatsApp handoff / concierge note"
    if "reservation" in hay or "rezervasyon" in hay or "booking" in hay:
        return "reservation confirmation / pre-arrival email"
    if "whatsapp" in hay or "check-in" in hay or "check in" in hay:
        return "WhatsApp check-in / guest arrival message"
    if "reception" in hay or "front office" in hay or "frontoffice" in hay:
        return "reception QR / front-office handoff"
    return "website form / WhatsApp / reception QR"


def best_email(emails: list[tuple[str, str, str]], official_domain: str) -> tuple[str, str, str]:
    if not emails:
        return "", "", ""
    official_reg = registered_domain(official_domain)

    def score(item: tuple[str, str, str]) -> int:
        email, url, kind = item
        local, domain = email.split("@", 1)
        local = local.lower()
        s = 0
        if registered_domain(domain) == official_reg:
            s += 50
        s += {"cloudflare": 30, "mailto": 25, "html": 15}.get(kind, 0)
        if local in {"sales", "reservation", "reservations", "booking", "partner", "agency"}:
            s += 15
        elif local in {"info", "contact", "reception", "frontoffice", "hello"}:
            s += 10
        if domain in COMMON_FREE_EMAIL_DOMAINS:
            s -= 5
        return s

    email, url, kind = max(emails, key=score)
    return email, url, kind


def lead_id_for(name: str, city: str, website: str, email: str) -> str:
    domain = registered_domain(domain_of(website)) or domain_of(email)
    base = re.sub(r"[^a-z0-9]+", "-", norm("__".join([name, city, domain or email]))).strip("-")
    digest = hashlib.sha1((base + "|" + clean_email(email)).encode("utf-8")).hexdigest()[:10]
    return f"{base}-{digest}"[:120]


def fit_score(segment: str, email: str, phone: str, instagram: str, text: str) -> int:
    score = 50
    if segment != "tourism-business":
        score += 15
    if email:
        score += 18
    if phone:
        score += 8
    if instagram:
        score += 4
    if foreign_tourist_signal(text):
        score += 8
    return min(100, score)


def inspect_candidate(session: requests.Session, mode: str, candidate: Candidate, max_pages: int, sleep_seconds: float) -> tuple[Lead | None, str]:
    response = request_get(session, candidate.url)
    if response is None:
        return None, "homepage_fetch_failed"
    homepage = response.url
    official_reg = registered_domain(domain_of(homepage))
    soup = BeautifulSoup(response.text, "lxml")
    pages = [homepage]
    pages += [u for u in candidate_contact_links(homepage, soup, max_links=max_pages - 1) if u not in pages]

    texts: list[str] = []
    checked: list[str] = []
    emails: list[tuple[str, str, str]] = []
    phone = ""
    phone_url = ""
    instagram = ""

    for url in pages[:max_pages]:
        if sleep_seconds:
            time.sleep(sleep_seconds)
        r = response if url == homepage else request_get(session, url)
        if r is None:
            continue
        checked.append(r.url)
        s = BeautifulSoup(r.text, "lxml")
        text = soup_text(s)
        texts.append(text)
        if not instagram:
            instagram = extract_instagram(s)
        if not phone:
            phone = extract_phone(text)
            if phone:
                phone_url = r.url
        for email, kind in extract_emails(r.text, s):
            if registered_domain(domain_of(r.url)) == official_reg:
                emails.append((email, r.url, kind))

    if not checked:
        return None, "no_pages_checked"

    combined = " ".join(texts)
    segment = infer_segment(mode, candidate.segment_query, combined)
    ok, fit_reason = mode_fit_ok(mode, segment, candidate.name_hint + " " + homepage + " " + combined)
    if not ok:
        return None, fit_reason

    email, email_url, email_kind = best_email(emails, official_reg)
    score = fit_score(segment, email, phone, instagram, combined)
    if not email and not phone and not instagram and len(checked) < 2:
        return None, "no_contact_path"

    status = "A_EMAIL_READY" if email else "B_CONTACT_FIRST"
    first_channel = "email" if email else ("phone/whatsapp" if phone else ("instagram" if instagram else "website_form"))
    name = infer_name(candidate.name_hint, soup, domain_of(homepage))
    lead = Lead(
        run_date=run_date(),
        run_slot=run_slot(),
        mode=mode,
        lead_id=lead_id_for(name, candidate.city_area, homepage, email),
        business_name=name,
        city_area=candidate.city_area,
        segment=segment,
        website=homepage,
        instagram=instagram,
        phone=phone,
        email=email,
        email_status=("source_visible_or_html_extracted" if email else "no_email_verified"),
        email_source_url=email_url,
        website_source_url=homepage,
        phone_source_url=phone_url,
        source_urls="; ".join(checked[:10]),
        first_contact_channel=first_channel,
        integration_point=integration_point(segment, combined),
        fit_score=score,
        status=status,
        short_note=f"{segment} lead for TouristNetTR; first move: {first_channel}.",
        validation_notes="; ".join(x for x in [
            fit_reason,
            f"Email extracted by {email_kind} from source page." if email else "No source-valid email found; do not bulk email.",
            "No guessed email used.",
            f"Checked URLs: {', '.join(checked[:5])}",
        ] if x),
    )
    return lead, "accepted"


def build_queries(mode: str, max_queries: int) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if mode == "antalya10":
        for district in ANTALYA_DISTRICTS:
            for segment in ANTALYA_SEGMENTS:
                rows.append((district, segment, f"{district} {segment} official website email phone"))
                rows.append((district, segment, f"{district} {segment} resmi site iletişim e-posta telefon"))
    else:
        for district in TARGET_DISTRICTS:
            for segment in TARGET_SEGMENTS:
                rows.append((district, segment, f"{district} {segment} official website email phone"))
                rows.append((district, segment, f"{district} {segment} resmi site iletişim e-posta telefon"))
    return rows[:max_queries]


def collect_candidates(session: requests.Session, mode: str, max_queries: int, results_per_query: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen_domains: set[str] = set()
    for city_area, segment_query, query in build_queries(mode, max_queries):
        urls = search_brave(session, query, results_per_query) or search_duckduckgo(session, query, results_per_query)
        for url in urls:
            reg = registered_domain(domain_of(url))
            if not reg or reg in seen_domains:
                continue
            seen_domains.add(reg)
            candidates.append(Candidate(name_hint=reg, city_area=city_area, segment_query=segment_query, url=url, source_query=query))
        time.sleep(0.35)
    return candidates


def load_suppression_index(mode: str) -> SuppressionIndex:
    index = SuppressionIndex()
    for csv_path in (ROOT / "leads").glob("**/*.csv"):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    index.add_row(row)
        except Exception:
            continue
    return index


def output_paths(mode: str, target_count: int) -> tuple[Path, Path]:
    date = run_date()
    slot = run_slot()
    base = "antalya10" if mode == "antalya10" else "target100"
    lead_dir = ROOT / "leads" / "auto" / base / date / slot
    report_dir = ROOT / "reports" / "auto" / base / date / slot
    lead_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = lead_dir / f"touristnettr_{base}_{target_count}_{date}_{slot}.csv"
    md_path = report_dir / f"touristnettr_{base}_{target_count}_{date}_{slot}.md"
    return csv_path, md_path


def md_escape(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def write_outputs(mode: str, leads: list[Lead], stats: dict[str, object], target_count: int) -> tuple[Path, Path]:
    csv_path, md_path = output_paths(mode, target_count)
    leads = sorted(leads, key=lambda x: (x.status == "A_EMAIL_READY", x.fit_score), reverse=True)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_row())

    status_counts = Counter(lead.status for lead in leads)
    segment_counts = Counter(lead.segment for lead in leads)
    area_counts = Counter(lead.city_area for lead in leads)
    reject_counts: Counter = stats.get("reject_counts", Counter())  # type: ignore[assignment]

    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# TouristNetTR Lead Machine — {mode} — {run_date()} {run_slot()}\n\n")
        f.write("## Result\n\n")
        f.write(f"- Target count: {target_count}\n")
        f.write(f"- Leads written: {len(leads)}\n")
        f.write(f"- Candidates collected: {stats.get('candidates_collected', 0)}\n")
        f.write(f"- Candidates inspected: {stats.get('candidates_inspected', 0)}\n")
        f.write(f"- Duplicates skipped: {stats.get('duplicates_skipped', 0)}\n")
        f.write(f"- CSV: `{csv_path.relative_to(ROOT)}`\n\n")
        f.write("## Status Counts\n")
        for key, count in status_counts.most_common():
            f.write(f"- {key}: {count}\n")
        f.write("\n## Segment Counts\n")
        for key, count in segment_counts.most_common():
            f.write(f"- {key}: {count}\n")
        f.write("\n## Area Counts\n")
        for key, count in area_counts.most_common(30):
            f.write(f"- {key}: {count}\n")
        f.write("\n## Lead Table\n\n")
        f.write("| business | area | segment | status | first channel | email | phone | score | website |\n")
        f.write("|---|---|---|---|---|---|---|---:|---|\n")
        for lead in leads[:120]:
            f.write(
                f"| {md_escape(lead.business_name)} | {md_escape(lead.city_area)} | {lead.segment} | "
                f"{lead.status} | {lead.first_contact_channel} | {md_escape(lead.email)} | {md_escape(lead.phone)} | "
                f"{lead.fit_score} | {md_escape(lead.website)} |\n"
            )
        f.write("\n## Rejection Counts\n")
        if reject_counts:
            for key, count in reject_counts.most_common():
                f.write(f"- {key}: {count}\n")
        else:
            f.write("- No rejection counts.\n")
        if len(leads) < target_count:
            f.write("\n## Warning\n\n")
            f.write("Target was not fully reached. No fake rows were added. Expand query lanes or add Brave Search API key if this repeats.\n")
    return csv_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["antalya10", "target100"], required=True)
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--max-queries", type=int, default=None)
    parser.add_argument("--results-per-query", type=int, default=int(os.getenv("RESULTS_PER_QUERY", "8")))
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--max-pages-per-site", type=int, default=int(os.getenv("MAX_PAGES_PER_SITE", "6")))
    parser.add_argument("--sleep-seconds", type=float, default=float(os.getenv("CRAWL_SLEEP_SECONDS", "0.2")))
    args = parser.parse_args()

    target_count = args.target_count if args.target_count is not None else (10 if args.mode == "antalya10" else 100)
    max_queries = args.max_queries if args.max_queries is not None else (80 if args.mode == "antalya10" else 220)
    max_candidates = args.max_candidates if args.max_candidates is not None else (250 if args.mode == "antalya10" else 1200)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 TouristNetTRLeadMachine/1.0 (+https://github.com/yasarcamus/zipkin)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    candidates = collect_candidates(session, args.mode, max_queries, args.results_per_query)[:max_candidates]
    suppression = load_suppression_index(args.mode)
    leads: list[Lead] = []
    seen_current: set[tuple[str, str, str]] = set()
    reject_counts: Counter = Counter()
    inspected = 0
    duplicates = 0

    for candidate in candidates:
        if len(leads) >= target_count:
            break
        inspected += 1
        lead, reason = inspect_candidate(session, args.mode, candidate, args.max_pages_per_site, args.sleep_seconds)
        if lead is None:
            reject_counts[reason] += 1
            continue
        current_key = (
            registered_domain(domain_of(lead.website)),
            clean_email(lead.email),
            normalize_phone(lead.phone),
        )
        if suppression.duplicate(lead) or current_key in seen_current:
            duplicates += 1
            reject_counts["duplicate"] += 1
            continue
        seen_current.add(current_key)
        leads.append(lead)

    csv_path, md_path = write_outputs(args.mode, leads, {
        "candidates_collected": len(candidates),
        "candidates_inspected": inspected,
        "duplicates_skipped": duplicates,
        "reject_counts": reject_counts,
    }, target_count)
    print(f"LEADS_WRITTEN={len(leads)}")
    print(f"CSV={csv_path.relative_to(ROOT)}")
    print(f"REPORT={md_path.relative_to(ROOT)}")
    if len(leads) < target_count:
        print(f"WARNING=target_not_reached {len(leads)}/{target_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
