import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from outils import weather
from outils.weather import IMPERIAL, METRIC, Place, WeatherError, describe, find_place, parse_forecast, pick_place, sky_spans, weather_spans

VICTORIA_BRAZIL = {"name": "Vitória", "latitude": -20.3, "longitude": -40.3, "country_code": "BR", "country": "Brazil", "admin1": "Espírito Santo"}
VICTORIA_BC = {"name": "Victoria", "latitude": 48.4, "longitude": -123.4, "country_code": "CA", "country": "Canada", "admin1": "British Columbia", "timezone": "America/Vancouver"}
VICTORIA_HK = {"name": "Victoria", "latitude": 22.3, "longitude": 114.1, "country_code": "HK", "admin1": "Central and Western"}
RESULTS = [VICTORIA_BRAZIL, VICTORIA_BC, VICTORIA_HK]
PLACE = Place("Victoria", "British Columbia", "Canada", 48.4, -123.4, "America/Vancouver", "CA")
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
        "weather_code": [0, 3, 3, None, 61, 63, 3],
        "temperature_2m": [12.0, 11.8, 11.6, None, 10.9, 10.7, 10.4],
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
            # The last are entries from before places had a time zone, then a country code
            before = {"name": "Victoria", "region": "British Columbia", "country": "Canada", "latitude": 48.4, "longitude": -123.4}
            for entry in ({"name": "Victoria"}, ["Victoria"], "Victoria", before, {**before, "timezone": "America/Vancouver"}):
                cache.write_text(json.dumps({"Victoria, BC": entry}))
                self.assertEqual(find_place("Victoria, BC", cache), PLACE)
            self.assertEqual(get.call_count, 5)
        for answer in ([], {"results": [{"name": "Victoria"}]}, {"results": ["Victoria"]}):
            with tempfile.TemporaryDirectory() as tmp, patch("outils.weather.ask", return_value=answer):
                with self.assertRaisesRegex(WeatherError, "answer outils cannot read"):
                    find_place("Victoria, BC", Path(tmp) / "places.json")


def spans_of(chances, codes=None, temperatures=None):
    """The spans of tomorrow, 2026-09-25, with these chances, codes and temperatures by hour."""
    hourly = {
        "time": [f"2026-09-25T{hour:02}:00" for hour in range(24)],
        "precipitation_probability": chances,
        "weather_code": codes or [61] * 24,
        "temperature_2m": temperatures or [10.0] * 24,
    }
    return weather_spans(parse_forecast(PLACE, {**FORECAST, "hourly": hourly}), 1)


def sky_of(codes, chances=None):
    """The sky spans and the rain spans of tomorrow, 2026-09-25, with these codes and chances by hour."""
    hourly = {
        "time": [f"2026-09-25T{hour:02}:00" for hour in range(24)],
        "precipitation_probability": chances or [0] * 24,
        "weather_code": codes,
        "temperature_2m": [15.0] * 24,
    }
    found = parse_forecast(PLACE, {**FORECAST, "daily": {**FORECAST["daily"], "weather_code": [0, 3]}, "hourly": hourly})
    return sky_spans(found, 1), weather_spans(found, 1)


class ForecastTest(unittest.TestCase):
    def test_parse_forecast_reads_now_and_every_day(self):
        result = parse_forecast(PLACE, FORECAST)
        self.assertEqual((result.current.temperature, result.current.is_day, result.current.code), (11.6, False, 0))
        self.assertEqual([day.day for day in result.days], [date(2026, 9, 24), date(2026, 9, 25)])
        self.assertEqual(result.days[1].high, 13.2)
        self.assertEqual(result.current.time, datetime(2026, 9, 24, 21, 15))
        self.assertEqual((result.hours[3].time, result.hours[3].rain_chance), (datetime(2026, 9, 24, 22), None))

    def test_a_dry_day_is_named_by_most_of_its_daytime_hours_not_its_worst(self):
        # Clear all day, thin cloud from 5pm: Open-Meteo's daily code says Overcast
        codes = [0] * 17 + [3] * 5 + [0, 1]
        daily = {**FORECAST["daily"], "weather_code": [61, 3]}
        hourly = {
            "time": [f"2026-09-25T{hour:02}:00" for hour in range(24)],
            "precipitation_probability": [0] * 24, "weather_code": codes, "temperature_2m": [15.0] * 24,
        }
        days = parse_forecast(PLACE, {**FORECAST, "daily": daily, "hourly": hourly}).days
        self.assertEqual([day.code for day in days], [61, 0])
        # A tie goes to the cloudier; rain keeps the daily code
        codes = [0] * 14 + [2] * 10
        hourly["weather_code"] = codes
        self.assertEqual(parse_forecast(PLACE, {**FORECAST, "daily": daily, "hourly": hourly}).days[1].code, 2)
        daily["weather_code"] = [61, 63]
        self.assertEqual(parse_forecast(PLACE, {**FORECAST, "daily": daily, "hourly": hourly}).days[1].code, 63)

    def test_a_dry_day_says_when_its_sky_is_the_opposite_of_its_words(self):
        # Clear, overcast from 6pm to 10pm, the window's end; noon to 3pm is too short, 11pm past the window
        self.assertEqual(sky_of([0] * 12 + [3] * 3 + [0] * 3 + [3] * 6)[0], [("overcast", 18, 22)])
        # Overcast most of the day, clear 7am to 11am and 6pm to 10pm
        self.assertEqual(sky_of([3] * 7 + [0] * 4 + [3] * 7 + [1] * 6)[0], [("clear", 7, 11), ("clear", 18, 22)])
        # Partly cloudy hours are not clear; rain spans are there for the view to show first
        sky, rain = sky_of([2] * 12 + [3] * 12, [0] * 12 + [80] * 12)
        self.assertEqual((sky, rain), ([], [("rain", 12, None)]))

    def test_rain_is_likely_in_spans_of_hours_of_40_percent_or_more(self):
        result = parse_forecast(PLACE, FORECAST)
        self.assertEqual((result.hours[4].code, result.hours[4].temperature), (61, 10.9))
        # Today counts from the hour begun (21:00): 5 % and none given, so not likely
        self.assertEqual(weather_spans(result, 0), [])
        # Likely from midnight, the start of the day, to the end of 2am
        self.assertEqual(weather_spans(result, 1), [("rain", None, 3)])
        wetter = parse_forecast(PLACE, {**FORECAST, "hourly": {**FORECAST["hourly"], "precipitation_probability": [0, 0, 50, 90, 0, 70, 0]}})
        self.assertEqual((weather_spans(wetter, 0), weather_spans(wetter, 1)), ([("rain", None, 23)], [("rain", 1, 2)]))

        wet, dry = 80, 0
        # 8am to 1pm and 6pm to 10pm; the dry hour at 10am is too short to split them
        self.assertEqual(spans_of([dry] * 8 + [wet, wet, dry, wet, wet] + [dry] * 5 + [wet] * 4 + [dry] * 2), [("rain", 8, 13), ("rain", 18, 22)])
        # Three spans: the shortest dry spell (2am to 5am, not 7am to noon) is closed
        self.assertEqual(spans_of([wet] * 2 + [dry] * 3 + [wet] * 2 + [dry] * 5 + [wet] * 2 + [dry] * 10), [("rain", None, 7), ("rain", 12, 14)])
        self.assertEqual(spans_of([wet] * 24), [("rain", None, None)])

    def test_snow_and_storms_are_spans_of_their_own(self):
        wet, dry = 80, 0
        chances = [dry] * 17 + [wet] + [dry] * 2 + [wet] * 2 + [dry] * 2
        # Each hour's kind by its code: rain at 5pm, snow from 8pm to 10pm
        self.assertEqual(spans_of(chances, [3] * 17 + [61] + [3] * 2 + [73, 71] + [3] * 2), [("rain", 17, 18), ("snow", 20, 22)])
        # A likely hour with a dry code: snow at 1°C or under, else rain; the kinds are not joined
        # across a one-hour dry spell
        self.assertEqual(spans_of(chances, [3] * 24, [5.0] * 20 + [1.0, 0.5] + [0.0] * 2), [("rain", 17, 18), ("snow", 20, 22)])
        # Three kinds: two of them close up, as the one that matters most
        chances = [dry] * 6 + [wet] * 2 + [dry] * 2 + [wet] * 2 + [dry] * 8 + [wet] * 2 + [dry] * 2
        codes = [3] * 6 + [61] * 2 + [3] * 2 + [95] * 2 + [3] * 8 + [73] * 2 + [3] * 2
        self.assertEqual(spans_of(chances, codes), [("storm", 6, 12), ("snow", 20, 22)])

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
