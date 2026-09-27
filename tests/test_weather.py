import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from outils import weather
from outils.weather import IMPERIAL, METRIC, Place, WeatherError, describe, find_place, parse_forecast, pick_place, rain_window

VICTORIA_BRAZIL = {"name": "Vitória", "latitude": -20.3, "longitude": -40.3, "country_code": "BR", "country": "Brazil", "admin1": "Espírito Santo"}
VICTORIA_BC = {"name": "Victoria", "latitude": 48.4, "longitude": -123.4, "country_code": "CA", "country": "Canada", "admin1": "British Columbia"}
VICTORIA_HK = {"name": "Victoria", "latitude": 22.3, "longitude": 114.1, "country_code": "HK", "admin1": "Central and Western"}
RESULTS = [VICTORIA_BRAZIL, VICTORIA_BC, VICTORIA_HK]
PLACE = Place("Victoria", "British Columbia", "Canada", 48.4, -123.4)
FORECAST = {
    "current": {
        "temperature_2m": 11.6, "apparent_temperature": 9.2,
        "time": "2026-09-24T21:15", "weather_code": 0, "wind_speed_10m": 8.2, "is_day": 0,
    },
    "daily": {
        "time": ["2026-09-24", "2026-09-25"],
        "weather_code": [61, 65],
        "temperature_2m_max": [17.6, 13.2],
        "temperature_2m_min": [9.1, 11.3],
    },
    "hourly": {
        "time": ["2026-09-24T08:00", "2026-09-24T20:00", "2026-09-24T21:00", "2026-09-24T22:00", "2026-09-25T00:00", "2026-09-25T01:00", "2026-09-25T02:00"],
        "precipitation_probability": [0, 0, 5, None, 60, 70, 80],
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
        with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.ask", return_value={"results": RESULTS}) as get:
            cache = Path(tmp) / "outils" / "places.json"
            first = find_place("Victoria, BC", cache)
            second = find_place("Victoria, BC", cache)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.args[1]["name"], "Victoria")
            self.assertEqual(first, second)
            self.assertEqual(json.loads(cache.read_text())["Victoria, BC"]["region"], "British Columbia")

    def test_an_unknown_place_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.ask", return_value={}):
            with self.assertRaisesRegex(WeatherError, "does not know 'Nowhere'"):
                find_place("Nowhere", Path(tmp) / "places.json")

    def test_a_bad_cache_entry_is_asked_again_and_a_bad_answer_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.ask", return_value={"results": RESULTS}) as get:
            cache = Path(tmp) / "places.json"
            for entry in ({"name": "Victoria"}, ["Victoria"], "Victoria"):
                cache.write_text(json.dumps({"Victoria, BC": entry}))
                self.assertEqual(find_place("Victoria, BC", cache), PLACE)
            self.assertEqual(get.call_count, 3)
        for answer in ([], {"results": [{"name": "Victoria"}]}, {"results": ["Victoria"]}):
            with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.ask", return_value=answer):
                with self.assertRaisesRegex(WeatherError, "answer outils cannot read"):
                    find_place("Victoria, BC", Path(tmp) / "places.json")


class ForecastTest(unittest.TestCase):
    def test_parse_forecast_reads_now_and_every_day(self):
        result = parse_forecast(PLACE, FORECAST)
        self.assertEqual((result.current.temperature, result.current.is_day, result.current.code), (11.6, False, 0))
        self.assertEqual([day.day for day in result.days], [date(2026, 9, 24), date(2026, 9, 25)])
        self.assertEqual(result.days[1].high, 13.2)
        self.assertEqual(result.current.time, datetime(2026, 9, 24, 21, 15))
        self.assertEqual((result.hours[3].time, result.hours[3].rain_chance), (datetime(2026, 9, 24, 22), None))

    def test_rain_is_likely_from_the_first_to_the_last_hour_of_40_percent_or_more(self):
        result = parse_forecast(PLACE, FORECAST)
        # Today counts from the hour begun (21:00): 5 % and none given, so not likely
        self.assertIsNone(rain_window(result, 0))
        # Likely from midnight, the start of the day, to the end of 2am
        self.assertEqual(rain_window(result, 1), (None, 3))
        wetter = parse_forecast(PLACE, {**FORECAST, "hourly": {**FORECAST["hourly"], "precipitation_probability": [0, 0, 50, 90, 0, 70, 0]}})
        self.assertEqual((rain_window(wetter, 0), rain_window(wetter, 1)), ((None, 23), (1, 2)))

    def test_the_forecast_is_asked_in_metric_and_converted_here_and_errors_become_weather_errors(self):
        with patch("outils.weather.find_place", return_value=PLACE), patch("outils.weather.ask", return_value=FORECAST) as get:
            weather.forecast("Victoria, BC")
            self.assertNotIn("temperature_unit", get.call_args.args[1])
        self.assertEqual((weather.temperature(20, IMPERIAL), weather.temperature(20, METRIC)), (68, 20))
        self.assertAlmostEqual(weather.speed(100, IMPERIAL), 62.14, places=2)
        self.assertEqual(weather.speed(100, METRIC), 100)
        for failure, message in (
            ({"side_effect": URLError("no network")}, "Cannot reach Open-Meteo: no network"),
            ({"side_effect": HTTPError("u", 400, "Bad", {}, io.BytesIO())}, "Open-Meteo answered 400"),
            ({"return_value": io.BytesIO(b"<html>")}, "Open-Meteo did not answer with JSON"),
        ):
            with patch("outils.web.urlopen", **failure), self.assertRaisesRegex(WeatherError, message):
                weather.ask(weather.FORECAST_URL, {})

    def test_a_forecast_of_another_shape_is_an_error(self):
        daily = FORECAST["daily"]
        for answer in (
            [],
            {"current": FORECAST["current"]},
            {**FORECAST, "current": {**FORECAST["current"], "temperature_2m": None}},
            {**FORECAST, "daily": {**daily, "weather_code": [61]}},
            {**FORECAST, "daily": {**daily, "time": ["2026-09-24", "tomorrow"]}},
            {**FORECAST, "hourly": {**FORECAST["hourly"], "precipitation_probability": [0]}},
        ):
            with patch("outils.weather.find_place", return_value=PLACE), patch("outils.weather.ask", return_value=answer):
                with self.assertRaisesRegex(WeatherError, "answer outils cannot read"):
                    weather.forecast("Victoria, BC")

    def test_describe_names_the_code_and_gives_the_moon_on_a_clear_night(self):
        self.assertEqual(describe(63)[0], "Rain")
        self.assertNotEqual(describe(0, is_day=True)[1], describe(0, is_day=False)[1])
        self.assertEqual(describe(2, is_day=False), describe(2, is_day=True))
        self.assertEqual(describe(1234)[0], "Unknown")


if __name__ == "__main__":
    unittest.main()
