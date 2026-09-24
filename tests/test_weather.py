import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from outils import weather
from outils.weather import IMPERIAL, METRIC, Place, WeatherError, describe, find_place, parse_forecast, pick_place

VICTORIA_BRAZIL = {"name": "Vitória", "latitude": -20.3, "longitude": -40.3, "country_code": "BR", "country": "Brazil", "admin1": "Espírito Santo"}
VICTORIA_BC = {"name": "Victoria", "latitude": 48.4, "longitude": -123.4, "country_code": "CA", "country": "Canada", "admin1": "British Columbia"}
VICTORIA_HK = {"name": "Victoria", "latitude": 22.3, "longitude": 114.1, "country_code": "HK", "admin1": "Central and Western"}
RESULTS = [VICTORIA_BRAZIL, VICTORIA_BC, VICTORIA_HK]
PLACE = Place("Victoria", "British Columbia", "Canada", 48.4, -123.4)
FORECAST = {
    "current": {
        "temperature_2m": 11.6, "apparent_temperature": 9.2, "relative_humidity_2m": 65,
        "precipitation": 0.0, "weather_code": 0, "wind_speed_10m": 8.2, "is_day": 0,
    },
    "daily": {
        "time": ["2026-09-24", "2026-09-25"],
        "weather_code": [61, 65],
        "temperature_2m_max": [17.6, 13.2],
        "temperature_2m_min": [9.1, 11.3],
        "precipitation_probability_max": [79, None],
        "precipitation_sum": [6.5, 19.5],
    },
}


class PickPlaceTest(unittest.TestCase):
    def test_the_name_comes_first_then_the_qualifier_in_full_or_by_initials(self):
        # Open-Meteo lists Vitória first for "Victoria"; the exact name wins
        self.assertEqual(pick_place("Victoria", RESULTS).region, "British Columbia")
        self.assertEqual(pick_place("Victoria, BC", RESULTS).country, "Canada")
        self.assertEqual(pick_place("Victoria, british columbia", RESULTS).country, "Canada")
        self.assertEqual(pick_place("Victoria, Hong Kong", RESULTS).latitude, 22.3)
        self.assertEqual(pick_place("Vitoria, Brazil", RESULTS).country, "Brazil")
        self.assertIsNone(pick_place("Nowhere", []))
        # US and Canadian postal codes, which initials cannot give; one word never matches by its first letter
        portlands = [
            {"name": "Portland", "latitude": 45.5, "longitude": -122.7, "country_code": "US", "admin1": "Oregon", "admin2": "Multnomah"},
            {"name": "Portland", "latitude": 43.7, "longitude": -70.3, "country_code": "US", "admin1": "Maine"},
        ]
        self.assertEqual(pick_place("Portland, OR", portlands).region, "Oregon")
        self.assertEqual(pick_place("Portland, me", portlands).region, "Maine")
        self.assertEqual(pick_place("Portland, M", portlands).region, "Oregon")
        # A place's own label, as the city box shows it, finds that place again
        self.assertEqual(pick_place("Portland, Maine, United States", portlands).region, "Maine")
        self.assertEqual(pick_place("Victoria, British Columbia, Canada", RESULTS).latitude, 48.4)
        self.assertEqual(PLACE.label, "Victoria, British Columbia, Canada")


class FindPlaceTest(unittest.TestCase):
    def test_a_place_is_looked_up_once_then_read_from_the_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.get_json", return_value={"results": RESULTS}) as get:
            cache = Path(tmp) / "outils" / "places.json"
            first = find_place("Victoria, BC", cache)
            second = find_place("Victoria, BC", cache)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.args[1]["name"], "Victoria")
            self.assertEqual(first, second)
            self.assertEqual(json.loads(cache.read_text())["Victoria, BC"]["region"], "British Columbia")

    def test_an_unknown_place_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.get_json", return_value={}):
            with self.assertRaisesRegex(WeatherError, "does not know 'Nowhere'"):
                find_place("Nowhere", Path(tmp) / "places.json")


class ForecastTest(unittest.TestCase):
    def test_parse_forecast_reads_now_and_every_day(self):
        result = parse_forecast(PLACE, METRIC, FORECAST)
        self.assertEqual((result.current.temperature, result.current.is_day, result.current.code), (11.6, False, 0))
        self.assertEqual([day.day for day in result.days], [date(2026, 9, 24), date(2026, 9, 25)])
        self.assertEqual([day.rain_chance for day in result.days], [79, None])
        self.assertEqual(result.days[1].high, 13.2)

    def test_units_reach_open_meteo_and_errors_become_weather_errors(self):
        with patch("outils.weather.find_place", return_value=PLACE), patch("outils.weather.get_json", return_value=FORECAST) as get:
            weather.forecast("Victoria, BC", IMPERIAL)
            self.assertEqual(get.call_args.args[1]["temperature_unit"], "fahrenheit")
            weather.forecast("Victoria, BC", METRIC)
            self.assertNotIn("temperature_unit", get.call_args.args[1])
        with patch("outils.weather.urlopen", side_effect=URLError("no network")):
            with self.assertRaisesRegex(WeatherError, "Cannot reach Open-Meteo: no network"):
                weather.get_json(weather.FORECAST_URL, {})
        with patch("outils.weather.urlopen", side_effect=HTTPError("u", 400, "Bad", {}, io.BytesIO())):
            with self.assertRaisesRegex(WeatherError, "answered 400"):
                weather.get_json(weather.FORECAST_URL, {})

    def test_describe_names_the_code_and_gives_the_moon_on_a_clear_night(self):
        self.assertEqual(describe(63)[0], "Rain")
        self.assertNotEqual(describe(0, is_day=True)[1], describe(0, is_day=False)[1])
        self.assertEqual(describe(2, is_day=False), describe(2, is_day=True))
        self.assertEqual(describe(1234)[0], "Unknown")


if __name__ == "__main__":
    unittest.main()
