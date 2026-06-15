# TouristNetTR — Antalya Hotel Mail List

Run date: 2026-06-15
Repository: yasarcamus/zipkin

## Goal

Find Antalya hotels that have a visible hotel email address.

## Include only

- Antalya province hotels
- 2-star hotels
- 3-star hotels
- 4-star hotels
- Boutique hotels
- Apart hotels

## Exclude

- 5-star resorts unless clearly boutique/apart style
- Villas
- Airbnb / property management
- Incoming agencies / DMCs / tour operators
- Real estate offices
- Restaurants / cafes / shops
- Clinics
- Hostels / dorms / campsites
- OTAs and directories such as Booking, Expedia, Agoda, Hotels.com, Otelz, Neredekal

## Rules

- If the hotel has an email, add it.
- If there is no email, skip it.
- Do not require decision maker data.
- Do not require phone.
- Do not require LinkedIn.
- Do not score leads.
- Do not write integration point.
- Do not force exactly 10 records.
- Do not write a failure report if the count is low.
- Do not invent or pattern-generate emails.

## CSV columns

hotel_name,district,hotel_type,stars,website,email,email_source_url,phone,instagram,source_urls,note

## Output

`leads/approved/2026-06-15-antalya-mail-hotels.csv`
