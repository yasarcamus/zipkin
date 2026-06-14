# TouristNetTR — Antalya Hotel-Only Night Pipeline

Run date: 2026-06-15
Repository: yasarcamus/zipkin
Scope: Antalya province hotels only.

## Hard Scope

Include only hotel/accommodation businesses in Antalya province:
- Boutique hotels
- Apart hotels
- City hotels
- Beach hotels
- Resort hotels if reachable through a clear contact path
- Thermal/spa hotels if they serve foreign tourists
- Professional accommodation businesses with visible hotel operations

Antalya province includes Antalya city, Kaleiçi/Muratpaşa, Konyaaltı, Lara/Kundu, Belek/Serik, Kemer, Side/Manavgat, Alanya, Kaş, Kalkan, Finike, Demre, Adrasan, Çıralı/Olympos, Kumluca and similar Antalya districts/tourism zones.

## Hard Exclusions

Reject:
- Non-Antalya businesses
- Incoming agencies, DMCs, tour operators
- Airbnb/villa/property management companies
- Generic real estate offices
- Standalone villas/daily rentals without hotel operation
- Small phone/communication shops
- Western Union/döviz-style shops
- Restaurants, cafes, markets
- Clinics/health tourism businesses
- Blogs, directories, OTAs, affiliate pages
- Records without source evidence

## Quality Rules

- No guessed or inferred emails.
- Mark a lead as `mail-ready` only if the email is found on an official source or a highly credible source and is not obviously mismatched with the hotel/domain.
- If email is uncertain, mark first_contact_channel as `phone/form/Instagram-first`.
- Source links are mandatory for approved records.
- Duplicate and near-duplicate hotel names must be removed.
- Chain/corporate hotels are lower priority unless a local direct contact path exists.
- Prefer fast-action independent hotels, boutique hotels, apart hotels, city hotels and professional tourism-facing hotels.

## Output Paths

Producer writes:
- `leads/raw/2026-06-15-antalya-hotels-raw.csv`

QC writes:
- `leads/approved/2026-06-15-antalya-hotels-approved.csv`
- `leads/quarantine/2026-06-15-antalya-hotels-quarantine.csv`
- `leads/rejected/2026-06-15-antalya-hotels-rejected.csv`
- `leads/qc/2026-06-15-antalya-hotels-qc-report.md`

Morning brief writes:
- `reports/2026-06-15-antalya-hotels-morning-brief.md`

## CSV Columns

hotel_name,district_city,hotel_type,website,instagram,phone_whatsapp,email,email_status,source_links,contact_source,first_contact_channel,foreign_tourist_signal,integration_point,fit_score,status,qc_note

## Status Values

- A_APPROVED: directly usable
- B_CONTACT_FIRST: good lead, but do not bulk email; use phone/form/Instagram first
- C_QUARANTINE: useful but needs manual verification
- D_REJECT: not usable

## Target

Producer should find 60 raw candidates.
QC should approve only strong records; do not fill quota with weak data.
Morning brief should give counts, top 10 leads and today's action plan.
