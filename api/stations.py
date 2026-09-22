import csv
import re
from functools import lru_cache

from django.conf import settings

_HEADER = re.compile(r"[^a-z0-9]+")


def _norm(header):
    """Lowercase a CSV header so 'Retail Price' and 'lat' match the same way."""
    return _HEADER.sub(" ", header.strip().lower()).strip()


def _detect(fieldnames):
    """Find the name, lat, lng, and price columns. Names vary by file."""
    cols = {_norm(h): h for h in fieldnames}
    lat = cols.get("lat") or cols.get("latitude")
    lng = cols.get("lng") or cols.get("lon") or cols.get("long") or cols.get("longitude")
    price = next((cols[k] for k in cols if "price" in k), None)
    name = cols.get("truckstop name") or cols.get("name") or cols.get("station") or cols.get("truckstop")
    sid = cols.get("opis truckstop id") or cols.get("id")
    if not all([lat, lng, price, name]):
        raise RuntimeError("fuel CSV needs name, lat/lng, and price columns")
    return {"lat": lat, "lng": lng, "price": price, "name": name, "id": sid}


@lru_cache(maxsize=1)
def load_stations():
    """Read the fuel CSV once and keep it in memory. Same truck-stop id keeps the cheaper price."""
    path = settings.FUEL_PRICES_CSV
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        mapping = _detect(reader.fieldnames)
        by_id = {}
        extra = []
        for row in reader:
            try:
                lat = float(row[mapping["lat"]])
                lng = float(row[mapping["lng"]])
                price = float(row[mapping["price"]])
            except (TypeError, ValueError):
                continue
            station = {
                "name": (row.get(mapping["name"]) or "").strip() or "Unknown",
                "lat": lat,
                "lng": lng,
                "price_per_gallon": price,
            }
            raw_id = row.get(mapping["id"]) if mapping["id"] else None
            if raw_id:
                prev = by_id.get(raw_id)
                if prev is None or price < prev["price_per_gallon"]:
                    by_id[raw_id] = station
            else:
                extra.append(station)
        return list(by_id.values()) + extra
