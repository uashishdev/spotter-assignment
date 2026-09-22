import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from api.stations import load_stations

RANGE_MILES = 500
MPG = 10
CORRIDOR_MILES = 10
SAMPLE_MILES = 2
METERS_PER_MILE = 1609.344
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=full&geometries=geojson"
PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "spotter-fuel-route/1.0"
COORD_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class PlanError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _get_json(url, timeout=15):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        raise PlanError(f"Upstream HTTP {exc.code}", status=502) from exc
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise PlanError("Upstream request failed", status=502) from exc


def haversine_miles(lat1, lng1, lat2, lng2):
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_point(text):
    m = COORD_RE.match(text)
    if m:
        lat, lng = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise PlanError(f"Invalid coordinates: {text}")
        return lat, lng
    data = _get_json(f"{PHOTON_URL}?{urlencode({'q': text, 'limit': 1})}", timeout=10)
    features = data.get("features") or []
    if not features:
        raise PlanError(f"Could not geocode: {text}")
    lng, lat = features[0]["geometry"]["coordinates"]
    return float(lat), float(lng)


def osrm_route(lat1, lng1, lat2, lng2):
    url = OSRM_URL.format(lat1=lat1, lng1=lng1, lat2=lat2, lng2=lng2)
    data = _get_json(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise PlanError("No driving route found", status=502)
    route = data["routes"][0]
    geometry = route.get("geometry")
    if not geometry or geometry.get("type") != "LineString":
        raise PlanError("OSRM returned no LineString", status=502)
    return geometry, float(route["distance"])


def sample_route(coords, sample_miles=SAMPLE_MILES):
    if not coords:
        return [], 0.0
    last_lat, last_lng = coords[0][1], coords[0][0]
    samples = [(last_lat, last_lng, 0.0)]
    acc = 0.0
    next_at = sample_miles
    for lon, lat in coords[1:]:
        seg = haversine_miles(last_lat, last_lng, lat, lon)
        while seg > 0 and acc + seg >= next_at:
            t = (next_at - acc) / seg
            samples.append(
                (
                    last_lat + t * (lat - last_lat),
                    last_lng + t * (lon - last_lng),
                    next_at,
                )
            )
            next_at += sample_miles
        acc += seg
        last_lat, last_lng = lat, lon
    if samples[-1][2] != acc:
        samples.append((last_lat, last_lng, acc))
    return samples, acc


def corridor_stations(stations, samples, total_miles, corridor=CORRIDOR_MILES):
    lats = [s[0] for s in samples]
    lngs = [s[1] for s in samples]
    pad = corridor / 69.0
    min_lat, max_lat = min(lats) - pad, max(lats) + pad
    mid = (min_lat + max_lat) / 2
    lng_pad = corridor / max(1e-6, 69.0 * math.cos(math.radians(mid)))
    min_lng, max_lng = min(lngs) - lng_pad, max(lngs) + lng_pad
    out = []
    for st in stations:
        lat, lng = st["lat"], st["lng"]
        if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
            continue
        best_d, best_m = 1e18, 0.0
        for slat, slng, miles in samples:
            d = haversine_miles(lat, lng, slat, slng)
            if d < best_d:
                best_d, best_m = d, miles
        if best_d <= corridor and 0 < best_m <= total_miles:
            rec = dict(st)
            rec["miles_from_start"] = best_m
            out.append(rec)
    return out


def greedy_stops(stations, total_miles, tank=RANGE_MILES):
    pos = 0.0
    remaining = tank
    stops = []
    while pos + remaining < total_miles:
        reach = pos + remaining
        cand = [s for s in stations if pos < s["miles_from_start"] <= reach]
        if not cand:
            raise PlanError(
                f"No reachable fuel stop before range runs out at mile {pos:.0f}"
            )
        pick = min(cand, key=lambda s: (s["price_per_gallon"], s["miles_from_start"]))
        stops.append(pick)
        pos = pick["miles_from_start"]
        remaining = tank
    return stops


def fill_costs(stops, total_miles, tank=RANGE_MILES, mpg=MPG):
    pos = 0.0
    fuel = tank
    cost = 0.0
    out = []
    for i, stop in enumerate(stops):
        fuel = max(0.0, fuel - (stop["miles_from_start"] - pos))
        cheaper_next = (
            i + 1 < len(stops)
            and stops[i + 1]["price_per_gallon"] < stop["price_per_gallon"]
        )
        dest = stops[i + 1]["miles_from_start"] if cheaper_next else total_miles
        need = min(tank, dest - stop["miles_from_start"])
        buy_miles = max(0.0, need - fuel)
        cost += (buy_miles / mpg) * stop["price_per_gallon"]
        fuel += buy_miles
        if buy_miles > 1e-6:
            out.append(
                {
                    "name": stop["name"],
                    "lat": round(stop["lat"], 6),
                    "lng": round(stop["lng"], 6),
                    "price_per_gallon": round(stop["price_per_gallon"], 2),
                    "miles_from_start": round(stop["miles_from_start"], 2),
                }
            )
        pos = stop["miles_from_start"]
    return out, round(cost, 2)


def plan_route(start, finish):
    slat, slng = parse_point(start)
    flat, flng = parse_point(finish)
    geometry, meters = osrm_route(slat, slng, flat, flng)
    total_miles = meters / METERS_PER_MILE
    samples, path_miles = sample_route(geometry["coordinates"])
    if path_miles > 0:
        k = total_miles / path_miles
        samples = [(lat, lng, m * k) for lat, lng, m in samples]
    nearby = corridor_stations(load_stations(), samples, total_miles)
    stops = greedy_stops(nearby, total_miles)
    fuel_stops, total_cost = fill_costs(stops, total_miles)
    map_url = (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route="
        f"{quote(f'{slat},{slng};{flat},{flng}')}"
    )
    return {
        "distance_miles": round(total_miles, 2),
        "fuel_stops": fuel_stops,
        "total_fuel_cost_usd": total_cost,
        "route_geojson": geometry,
        "map_url": map_url,
    }