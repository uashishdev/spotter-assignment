from django.test import SimpleTestCase

from api.route import PlanError, corridor_stations, fill_costs, greedy_stops, sample_route


class GreedyFuelTests(SimpleTestCase):
    def test_picks_cheapest_reachable_and_fill_to_next(self):
        stations = [
            {"name": "pricey", "lat": 40.0, "lng": -88.0, "price_per_gallon": 5.0, "miles_from_start": 80},
            {"name": "cheap", "lat": 40.5, "lng": -86.0, "price_per_gallon": 2.5, "miles_from_start": 400},
            {"name": "next", "lat": 41.0, "lng": -82.0, "price_per_gallon": 3.0, "miles_from_start": 700},
        ]
        stops = greedy_stops(stations, 950)
        self.assertEqual([s["name"] for s in stops], ["cheap", "next"])
        fuel_stops, cost = fill_costs(stops, 950)
        self.assertEqual(len(fuel_stops), 2)
        self.assertAlmostEqual(cost, 115.0)

    def test_gap_over_range_errors(self):
        stations = [
            {"name": "only", "lat": 0, "lng": 0, "price_per_gallon": 3.0, "miles_from_start": 100},
        ]
        with self.assertRaises(PlanError) as ctx:
            greedy_stops(stations, 700)
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("range runs out", str(ctx.exception))

    def test_corridor_keeps_nearby_station(self):
        coords = [[-90.0, 40.0], [-80.0, 40.0]]
        samples, total = sample_route(coords)
        stations = [
            {"name": "on-route", "lat": 40.05, "lng": -85.0, "price_per_gallon": 3.1},
            {"name": "far", "lat": 42.0, "lng": -85.0, "price_per_gallon": 1.0},
        ]
        nearby = corridor_stations(stations, samples, total, corridor=10)
        self.assertEqual([s["name"] for s in nearby], ["on-route"])
        self.assertGreater(nearby[0]["miles_from_start"], 0)
