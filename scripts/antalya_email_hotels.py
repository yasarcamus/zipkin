#!/usr/bin/env python3
"""
TouristNetTR Antalya email-ready hotel crawler.

Goal:
Find Antalya province hotels with source-visible emails.
Prioritize 2/3/4-star, boutique and apart hotels.
Decision-maker data is not required.

Outputs:
- leads/approved/YYYY-MM-DD-antalya-email-hotels.csv
- reports/YYYY-MM-DD-antalya-email-hotels-brief.md
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
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

DISTRICTS = [
    "Antalya Kaleici", "Antalya Muratpasa", "Antalya Konyaalti", "Antalya Lara",
    "Antalya Kundu", "Belek", "Serik", "Side", "Manavgat", "Alanya",
    "Kemer", "Kas", "Kalkan", "Finike", "Demre", "Adrasan", "Cirali", "Olympos",
]
SEGMENTS = [
    "2 star hotel", "3 star hotel", "4 star hotel", "boutique hotel", "butik otel",
    "apart hotel", "aparthotel", "suite hotel", "small hotel", "city hotel", "beach hotel",
]

SEARCH_QUERIES = [
    f"{district} {segment} official website contact email" for district in DISTRICTS for segment in SEGMENTS
] + [
    f"{district} {segment} resmi site iletişim e-posta" for district in DISTRICTS for segment in SEGMENTS
]

EXCLUDED_DOMAINS = (
    "booking.", "tripadvisor.", "expedia.", "agoda.", "hotels.com", "trivago.", "airbnb.",
    "vrbo.", "etstur.", "tatilsepeti.", "jollytur.", "otelz.", "neredekal.", "setur.",
    "facebook.com", "instagram.com", "youtube.com", "linkedin.com", "wikipedia.org",
    "google.", "yandex.", "mapcarta.", "touristica.", "tatilbudur.", "tourradar.",
)
HOTEL_SIGNALS = (
    "hotel", "otel", "boutique", "butik", "apart", "aparthotel", "suite", "suites",
    "rooms", "accommodation", "konaklama", "guest", "misafir", "beach", "spa", "resort",
)
TARGET_SIGNALS = (
    "2 star", "2-star", "2 yıldız", "2 yildiz", "3 star", "3-star", "3 yıldız", "3 yildiz",
    "4 star", "4-star", "4 yıldız", "4 yildiz", "boutique", "butik", "apart", "aparthotel", "suite",
)
NEGATIVE_SIGNALS = (
    "villa", "villas", "airbnb", "emlak", "real estate", "property management", "rent a car",
    "transfer", "travel agency", "tour operator", "restaurant", "restoran", "cafe", "camping",
    "hostel", "dorm", "yurt", "clinic", "klinik", "dental", "hospital", "hastane",
)
CONTACT_LINK_KEYWORDS = (
    "contact", "iletisim", "iletişim", "reservation", "rezervasyon", "booking", "sales",
    "satis", "satış", "kvkk", "about", "hakkimizda", "hakkımızda", "frontoffice", "front-office",
)
NOISE_EMAIL_DOMAINS = {
    "example.com", "domain.com", "sentry.io", "wix.com", "wordpress.com", "cloudflare.com",
    "google.com", "schema.org", "w3.org", "facebook.com", "instagram.com", "booking.com",
    "tripadvisor.com", "expedia.com",
}
COMMON_FREE_EMAIL_DOMAINS = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yandex.com", "icloud.com", "live.com"}

EMAIL_RE = re.compile(r"(?i)(?<![A-Z0-9._%+-])([A-Z0-9._%+\-]{1,64}@[A-Z0-9.\-]{2,255}\.[A-Z]{2,24})(?![A-Z0-9._%+-])")
PHONE_RE = re.compile(r"(?x)((?:\+?90|0)?\s*(?:\(?\d{3}\)?[\s.\-]*)\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2})")
CFEMAIL_RE = re.compile(r'data-cfemail=["\']([0-9a-fA-F]+)["\']')
CFEMAIL_HASH_RE = re.compile(r"/cdn-cgi/l/email-protection#([0-9a-fA-F]+)")

CSV_COLUMNS = [
    "run_date", "hotel_name", "district_city", "hotel_type", "stars", "website", "instagram",
    "phone_whatsapp", "email", "email_status", "email_source_url", "source_links", "contact_source",
    "first_contact_channel", "foreign_tourist_signal", "integration_point", "fit_score", "status", "qc_note",
]


@dataclasses.dataclass
class Candidate:
    title: str
    url: str
    district_city: str
    query: str


@dataclasses.dataclass
class Lead:
    run_date: str
    hotel_name: str
    district_city: str
    hotel_type: str
    stars: str
    website: str
    instagram: str
    phone_whatsapp: str
    email: str
    email_status: str
    email_source_url: str
    source_links: str
    contact_source: str
    first_contact_channel: str
    foreign_tourist_signal: str
    integration_point: str
    fit_score: int
    status: str
    qc_note: str

    def to_row(self) -> dict[str, str | int]:
        return dataclasses.asdict(self)


def today() -> str:
    return (dt.datetime.utcnow() + dt.timedelta(hours=3)).date().isoformat()


def norm(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    return re.sub(r"\s+", " ", value)


def clean_email(value: str) -> str:
    return norm(value).replace("mailto:", "").strip(".,;:()[]{}<>\"'")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
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
    second_level_cc = {"com", "net", "org", "edu", "gov", "bel", "k12", "av", "gen", "web"}
    if len(parts) >= 3 and parts[-1] == "tr" and parts[-2] in second_level_cc:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_registered_domain(a: str, b: str) -> bool:
    return registered_domain(domain_of(a)) == registered_domain(domain_of(b))


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


def is_excluded_url(url: str) -> bool:
    domain = domain_of(url)
    return not domain or any(x in domain for x in EXCLUDED_DOMAINS)


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


def soup_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_instagram(soup: BeautifulSoup) -> str:
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "instagram.com" in href.lower():
            parsed = urlparse(href)
            handle = parsed.path.strip("/").split("/")[0]
            return f"@{handle.lower()}" if handle else ""
    return ""


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
        digits = re.sub(r"\D+", "", match.group(1))
        if len(digits) >= 10:
            if digits.startswith("90") and len(digits) == 12:
                return "+" + digits
            if digits.startswith("0") and len(digits) == 11:
                return "+9" + digits
            if len(digits) == 10:
                return "+90" + digits
            return "+" + digits if match.group(1).strip().startswith("+") else digits
    return ""


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


def infer_name(title: str, soup: BeautifulSoup, domain: str) -> str:
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        text = title_tag.get_text(" ", strip=True)
    else:
        text = title or domain
    text = re.sub(r"\s+\|.*$|\s+-\s+.*$", "", text).strip()
    return text or domain


def infer_stars(text: str) -> str:
    hay = norm(text)
    for n in (2, 3, 4):
        patterns = [f"{n} star", f"{n}-star", f"{n} yıldız", f"{n} yildiz", f"{n} stars"]
        if any(p in hay for p in patterns):
            return f"{n}-star"
    if "5 star" in hay or "5-star" in hay or "5 yıldız" in hay or "5 yildiz" in hay:
        return "5-star"
    return "not found"


def infer_type(text: str, query: str) -> str:
    hay = norm(text + " " + query)
    if "apart" in hay or "aparthotel" in hay:
        return "apart hotel"
    if "boutique" in hay or "butik" in hay:
        return "boutique hotel"
    if "suite" in hay:
        return "suite hotel"
    if "beach" in hay:
        return "beach hotel"
    if "city" in hay:
        return "city hotel"
    return "hotel"


def foreign_signal(text: str) -> str:
    hay = norm(text)
    signals = []
    for lang in ("english", "deutsch", "russian", "русский", "arabic", "français"):
        if lang in hay:
            signals.append(lang)
    if "airport" in hay or "transfer" in hay:
        signals.append("airport/transfer wording")
    if "eur" in hay or "euro" in hay or "usd" in hay:
        signals.append("foreign currency wording")
    return ", ".join(signals[:4]) or "touristic Antalya hotel website"


def integration_point(text: str) -> str:
    hay = norm(text)
    if "reservation" in hay or "rezervasyon" in hay or "booking" in hay:
        return "reservation confirmation / pre-arrival email"
    if "whatsapp" in hay or "check-in" in hay or "check in" in hay:
        return "WhatsApp check-in / pre-arrival message"
    if "reception" in hay or "front office" in hay or "frontoffice" in hay:
        return "reception QR / front-office handoff"
    return "reservation email / reception QR"


def score_fit(text: str, email: str, stars: str, hotel_type: str) -> int:
    hay = norm(text)
    score = 50
    if email:
        score += 20
    if stars in {"2-star", "3-star", "4-star"}:
        score += 12
    if hotel_type in {"boutique hotel", "apart hotel", "suite hotel", "city hotel"}:
        score += 12
    if any(x in hay for x in ("english", "deutsch", "russian", "airport", "reservation", "booking")):
        score += 6
    return min(100, score)


def inspect_candidate(session: requests.Session, candidate: Candidate, max_pages: int, sleep_seconds: float) -> Lead | None:
    response = request_get(session, candidate.url)
    if response is None:
        return None
    homepage = response.url
    official_reg = registered_domain(domain_of(homepage))
    soup = BeautifulSoup(response.text, "lxml")
    pages = [homepage]
    pages += [u for u in candidate_contact_links(homepage, soup, max_pages=max_pages - 1) if u not in pages]

    checked, texts = [], []
    emails: list[tuple[str, str, str]] = []
    phone = ""
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
        for email, kind in extract_emails(r.text, s):
            # Accept email only if visibly found on the hotel website page. It may be a general or free mailbox, but no guessed pattern emails.
            if registered_domain(domain_of(r.url)) == official_reg:
                emails.append((email, r.url, kind))

    if not checked:
        return None
    combined = " ".join(texts)
    hay = norm(candidate.title + " " + homepage + " " + combined[:5000])
    if not any(s in hay for s in HOTEL_SIGNALS):
        return None
    if any(s in hay for s in NEGATIVE_SIGNALS) and not any(s in hay for s in ("hotel", "otel", "apart", "boutique", "butik")):
        return None

    best_email, email_url, email_kind = "", "", ""
    if emails:
        def email_score(item: tuple[str, str, str]) -> int:
            email, url, kind = item
            local, domain = email.split("@", 1)
            local = local.lower()
            score = 0
            if registered_domain(domain) == official_reg:
                score += 50
            if kind == "mailto":
                score += 20
            if local in {"reservation", "reservations", "sales", "booking"}:
                score += 15
            elif local in {"info", "contact", "reception", "frontoffice"}:
                score += 10
            if domain in COMMON_FREE_EMAIL_DOMAINS:
                score -= 5
            return score
        best_email, email_url, email_kind = max(emails, key=email_score)
    if not best_email:
        return None

    name = infer_name(candidate.title, soup, domain_of(homepage))
    stars = infer_stars(combined)
    hotel_type = infer_type(combined, candidate.query)
    # Main target is 2/3/4-star + boutique/apart. If star not found but type is boutique/apart/suite, still keep.
    if stars == "5-star" and hotel_type not in {"boutique hotel", "apart hotel", "suite hotel"}:
        return None
    if stars == "not found" and hotel_type not in {"boutique hotel", "apart hotel", "suite hotel"}:
        return None

    fit = score_fit(combined, best_email, stars, hotel_type)
    return Lead(
        run_date=today(),
        hotel_name=name,
        district_city=candidate.district_city,
        hotel_type=hotel_type,
        stars=stars,
        website=homepage,
        instagram=instagram,
        phone_whatsapp=phone,
        email=best_email,
        email_status="source_visible_hotel_email",
        email_source_url=email_url,
        source_links="; ".join(checked[:8]),
        contact_source=f"official website page / {email_kind}",
        first_contact_channel="email",
        foreign_tourist_signal=foreign_signal(combined),
        integration_point=integration_point(combined),
        fit_score=fit,
        status="A_APPROVED",
        qc_note="Email found on crawled hotel website page; no guessed email; decision-maker not required.",
    )


def collect_candidates(session: requests.Session, max_queries: int, results_per_query: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen_domains: set[str] = set()
    for query in SEARCH_QUERIES[:max_queries]:
        district_city = query.split(" official", 1)[0].split(" resmi", 1)[0]
        urls = search_brave(session, query, results_per_query) or search_duckduckgo(session, query, results_per_query)
        for url in urls:
            reg = registered_domain(domain_of(url))
            if not reg or reg in seen_domains:
                continue
            seen_domains.add(reg)
            candidates.append(Candidate(title=reg, url=url, district_city=district_city, query=query))
        time.sleep(0.4)
    return candidates


def write_outputs(leads: list[Lead], stats: dict[str, object]) -> None:
    run_date = today()
    approved_dir = ROOT / "leads" / "approved"
    report_dir = ROOT / "reports"
    approved_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = approved_dir / f"{run_date}-antalya-email-hotels.csv"
    report_path = report_dir / f"{run_date}-antalya-email-hotels-brief.md"

    leads = sorted(leads, key=lambda x: (x.fit_score, x.hotel_type in {"boutique hotel", "apart hotel"}), reverse=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_row())

    type_counts = Counter(lead.hotel_type for lead in leads)
    star_counts = Counter(lead.stars for lead in leads)
    district_counts = Counter(lead.district_city for lead in leads)

    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"# TouristNetTR — Antalya Email-Ready Hotel Leads — {run_date}\n\n")
        f.write("## Result\n\n")
        f.write(f"- Approved email-ready hotels: {len(leads)}\n")
        f.write(f"- Candidates collected: {stats.get('candidates_collected', 0)}\n")
        f.write(f"- Candidates inspected: {stats.get('candidates_inspected', 0)}\n")
        f.write(f"- Duplicate domains skipped: {stats.get('duplicates_skipped', 0)}\n")
        f.write(f"- Output CSV: `{csv_path.relative_to(ROOT)}`\n\n")
        f.write("## Scope\n\n")
        f.write("Antalya province only. Priority: 2/3/4-star, boutique, apart, suite and small/medium hotels with source-visible emails. Decision-maker data is not required.\n\n")
        f.write("## Type Mix\n")
        for key, count in type_counts.most_common():
            f.write(f"- {key}: {count}\n")
        f.write("\n## Star Mix\n")
        for key, count in star_counts.most_common():
            f.write(f"- {key}: {count}\n")
        f.write("\n## District / Query Mix\n")
        for key, count in district_counts.most_common(20):
            f.write(f"- {key}: {count}\n")
        f.write("\n## Top Leads\n\n")
        f.write("| Hotel | District | Type | Stars | Email | Score | Website |\n")
        f.write("|---|---|---|---|---|---:|---|\n")
        for lead in leads[:40]:
            f.write(f"| {lead.hotel_name.replace('|', ' ')} | {lead.district_city.replace('|', ' ')} | {lead.hotel_type} | {lead.stars} | {lead.email} | {lead.fit_score} | {lead.website} |\n")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-queries", type=int, default=int(os.getenv("MAX_QUERIES", "120")))
    parser.add_argument("--results-per-query", type=int, default=int(os.getenv("RESULTS_PER_QUERY", "10")))
    parser.add_argument("--max-candidates", type=int, default=int(os.getenv("MAX_CANDIDATES", "500")))
    parser.add_argument("--max-approved", type=int, default=int(os.getenv("MAX_APPROVED", "300")))
    parser.add_argument("--max-pages-per-site", type=int, default=int(os.getenv("MAX_PAGES_PER_SITE", "7")))
    parser.add_argument("--sleep-seconds", type=float, default=float(os.getenv("CRAWL_SLEEP_SECONDS", "0.2")))
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 TouristNetTR Antalya Hotel Email Crawler/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    candidates = collect_candidates(session, args.max_queries, args.results_per_query)[: args.max_candidates]
    leads: list[Lead] = []
    seen_domains: set[str] = set()
    inspected = 0
    duplicates = 0

    for candidate in candidates:
        if len(leads) >= args.max_approved:
            break
        domain = registered_domain(domain_of(candidate.url))
        if domain in seen_domains:
            duplicates += 1
            continue
        inspected += 1
        lead = inspect_candidate(session, candidate, args.max_pages_per_site, args.sleep_seconds)
        if lead is None:
            continue
        seen_domains.add(domain)
        leads.append(lead)

    write_outputs(leads, {
        "candidates_collected": len(candidates),
        "candidates_inspected": inspected,
        "duplicates_skipped": duplicates,
    })
    print(f"APPROVED_EMAIL_READY_HOTELS={len(leads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
