# Fuel route API

Python 3.12+. POST `/api/route/` — US start/finish in, driving route + cheap fuel stops out.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/api/route/ in a browser for the DRF form. curl still gets JSON.

```bash
curl -s http://127.0.0.1:8000/api/route/ \
  -H 'Content-Type: application/json' \
  -d '{"start":"41.8781,-87.6298","finish":"40.7128,-74.0060"}'
```

Pass `"lat,lng"` to skip geocoding (Photon is used only for place names). Routing is one call to the public OSRM demo: `https://router.project-osrm.org`.

Vehicle: 500 mile tank, 10 mpg, start full (that fuel is not billed). Stops: cheapest station still reachable before empty. At a stop, fill only enough to reach the next cheaper stop, or the finish if this price is better, capped at 50 gallons. Trips ≤500 miles return no stops and $0.

`data/fuel-prices.csv` is the OPIS list plus Census 2025 place/cousub centroids for city+state. Rows without a US match are omitted. Duplicate OPIS IDs keep the lowest price.
