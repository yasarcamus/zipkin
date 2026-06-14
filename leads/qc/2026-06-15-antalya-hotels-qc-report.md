# TouristNetTR Antalya Hotel Leads QC Report — 2026-06-15

## Executive Summary

Strict QC completed for `leads/raw/2026-06-15-antalya-hotels-raw.csv`.

Result: the raw file is clean on scope but weak on email readiness. All retained records are Antalya province hotel/accommodation businesses with official-source evidence. None had a verified direct email in the raw file, so none were marked bulk-email ready.

## Counts

| Status | Meaning | Count |
|---|---:|---:|
| A_APPROVED | Verified hotel + safe email/contact evidence for direct outbound email | 0 |
| B_CONTACT_FIRST | Good Antalya hotel lead, but use website form / phone / Instagram first | 74 |
| C_QUARANTINE | Needs extra verification before use | 0 |
| D_REJECT | Out of scope / unsafe / duplicate / weak evidence | 0 |
| Total raw candidates reviewed |  | 74 |

## QC Rules Applied

Rejected categories were: non-Antalya businesses, agencies, DMCs, tour operators, Airbnb/villa/property management, generic real estate, standalone villas/daily rentals without clear hotel operations, small phone shops, Western Union/döviz-style shops, restaurants/cafes/markets, clinics, OTAs, blogs/directories, duplicates, records without source evidence, guessed emails, and domain-mail mismatches.

## Decision Logic

Every retained record met these minimum criteria:

- Antalya province location present in `district_city`.
- Hotel/accommodation operation clear from name/type and official source URL.
- Source was official website or official brand website, not a directory/OTA/blog.
- No raw record contained a copied/verified email; therefore all were downgraded from possible A-tier to `B_CONTACT_FIRST`.

## Email Risk

Do not bulk email this file as-is. The raw file intentionally left emails blank and marked `no_email_verified`. That is good hygiene. It prevents another bounce-heavy run.

Safe first contact path:

1. Website contact form where available.
2. Phone / WhatsApp to identify guest relations, front office, sales, or revenue contact.
3. Instagram DM only for boutique hotels or when the site/form path is weak.
4. Direct email only after it appears on an official hotel/brand contact page or is confirmed by staff.

## Best Leads To Prioritize First

| Priority | Hotel | District | Reason | First channel |
|---:|---|---|---|---|
| 1 | Maxx Royal Kemer Resort | Kemer | Ultra-luxury, high foreign tourist fit | Website form / phone |
| 2 | Maxx Royal Belek Golf Resort | Belek / Serik | Ultra-luxury Belek resort | Website form / phone |
| 3 | Regnum Carya | Belek / Serik | Premium golf/luxury audience | Website form / phone |
| 4 | Titanic Mardan Palace | Kundu / Aksu | Ultra-luxury VIP-heavy resort | Website form / phone |
| 5 | Rixos Premium Belek | Belek / Serik | Large international brand | Website form / phone |
| 6 | Lara Barut Collection | Lara / Muratpaşa | Strong beachfront foreign guest flow | Website form / phone |
| 7 | Kempinski Hotel The Dome Belek | Belek / Serik | International luxury brand | Official form / phone |
| 8 | The Land of Legends Kingdom Hotel | Belek / Serik | International family traffic | Website form / phone |
| 9 | Rixos Sungate | Beldibi / Kemer | Large international resort | Website form / phone |
| 10 | Akra Antalya | Muratpaşa | City resort + foreign/business guests | Website form / phone |

## Output Files Written

- `leads/approved/2026-06-15-antalya-hotels-approved.csv`
- `leads/quarantine/2026-06-15-antalya-hotels-quarantine.csv`
- `leads/rejected/2026-06-15-antalya-hotels-rejected.csv`
- `leads/qc/2026-06-15-antalya-hotels-qc-report.md`

## Bottom Line

Clean segment. No obvious garbage. But this is not a sendable email list. It is a strong contact-first hotel prospecting list. Treat the first move as relationship routing, not cold bulk email.
