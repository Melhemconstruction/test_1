#!/usr/bin/env python3
"""Collect nutritionists / dietitians / nutrition clinics in Mount Lebanon via the
Google Places API (New) Text Search, and write them to a CSV.

Usage:
    export GOOGLE_PLACES_API_KEY=...
    python3 mount_lebanon_nutritionists.py              # all districts
    python3 mount_lebanon_nutritionists.py Matn Baabda  # selected districts

Each district rectangle is searched; any rectangle whose query returns the API's
60-result cap is split into four and searched again, so dense areas are not cut off.
"""
import csv
import json
import os
import sys
import time
import urllib.request

API_URL = "https://places.googleapis.com/v1/places:searchText"
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")

# Approximate bounding boxes: (south, west, north, east). Overlaps are harmless,
# results are de-duplicated by place id.
DISTRICTS = {
    "Baabda":   (33.75, 35.47, 33.89, 35.76),
    "Matn":     (33.82, 35.52, 33.98, 35.86),
    "Keserwan": (33.92, 35.58, 34.11, 35.96),
    "Jbeil":    (34.02, 35.60, 34.31, 36.06),
    "Aley":     (33.69, 35.44, 33.86, 35.76),
    "Chouf":    (33.45, 35.34, 33.76, 35.76),
}

QUERIES = [
    "nutritionist",
    "dietitian",
    "nutrition clinic",
    "diététicienne",
    "أخصائي تغذية",
]

FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "nextPageToken",
])

MIN_CELL_DEG = 0.02  # ~2 km; stop subdividing below this


def search(query, box, page_token=None):
    s, w, n, e = box
    body = {
        "textQuery": query,
        "pageSize": 20,
        "locationRestriction": {"rectangle": {
            "low": {"latitude": s, "longitude": w},
            "high": {"latitude": n, "longitude": e},
        }},
    }
    if page_token:
        body["pageToken"] = page_token
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": FIELDS,
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            sys.exit(f"Places API error {err.code}: {err.read().decode()}")


def search_box(query, box, found, district):
    places, token = [], None
    while True:
        resp = search(query, box, token)
        places.extend(resp.get("places", []))
        token = resp.get("nextPageToken")
        if not token:
            break
        time.sleep(2)  # page tokens need a moment to become valid
    for p in places:
        found.setdefault(p["id"], (p, district))

    s, w, n, e = box
    if len(places) >= 60 and (n - s) > MIN_CELL_DEG:
        mid_lat, mid_lng = (s + n) / 2, (w + e) / 2
        for sub in [(s, w, mid_lat, mid_lng), (s, mid_lng, mid_lat, e),
                    (mid_lat, w, n, mid_lng), (mid_lat, mid_lng, n, e)]:
            search_box(query, sub, found, district)


def locality(place):
    for comp in place.get("addressComponents", []):
        if "locality" in comp.get("types", []):
            return comp.get("longText", "")
    return ""


def main():
    if not API_KEY:
        sys.exit("Set GOOGLE_PLACES_API_KEY first.")
    names = sys.argv[1:] or list(DISTRICTS)
    unknown = [d for d in names if d not in DISTRICTS]
    if unknown:
        sys.exit(f"Unknown district(s): {unknown}. Choose from {list(DISTRICTS)}")

    found = {}
    for district in names:
        for q in QUERIES:
            print(f"{district}: '{q}'", file=sys.stderr)
            search_box(q, DISTRICTS[district], found, district)
        print(f"  total so far: {len(found)}", file=sys.stderr)

    out = "mount_lebanon_nutritionists.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["name", "category", "district_searched", "town", "address",
                     "phone", "phone_international", "website", "google_maps",
                     "rating", "reviews", "status", "lat", "lng", "place_id"])
        for pid, (p, district) in sorted(found.items(),
                                         key=lambda kv: (kv[1][1], kv[1][0].get("displayName", {}).get("text", ""))):
            loc = p.get("location", {})
            wr.writerow([
                p.get("displayName", {}).get("text", ""),
                p.get("primaryTypeDisplayName", {}).get("text", ""),
                district,
                locality(p),
                p.get("formattedAddress", ""),
                p.get("nationalPhoneNumber", ""),
                p.get("internationalPhoneNumber", ""),
                p.get("websiteUri", ""),
                p.get("googleMapsUri", ""),
                p.get("rating", ""),
                p.get("userRatingCount", ""),
                p.get("businessStatus", ""),
                loc.get("latitude", ""),
                loc.get("longitude", ""),
                pid,
            ])
    print(f"Wrote {len(found)} places to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
