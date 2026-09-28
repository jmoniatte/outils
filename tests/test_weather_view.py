import asyncio
import tempfile
import unittest
from time import time
from pathlib import Path
from unittest.mock import call, patch

from textual.app import App
from textual.widgets import Input

from outils.app import OutilsApp
from outils.config import Config
from outils.weather import Span, WeatherError, parse_forecast
from outils.widgets import WeatherView
from outils.widgets.weather_view import MAX_AGE, ForecastView, _said

from tests.host import Host, settle
from tests.test_weather import FORECAST, PLACE

VICTORIA = parse_forecast(PLACE, FORECAST)


def shown(app: App) -> list[str]:
    return [line.rstrip() for line in app.query_one(ForecastView).render().plain.split("\n")]



class WeatherViewTest(unittest.TestCase):
    def run_view(self, config, body, **patches):
        async def main():
            app = Host(WeatherView(config))
            with patch("outils.widgets.weather_view.forecast", **patches) as fetch:
                async with app.run_test(size=(89, 23)) as pilot:
                    await settle(app, pilot)
                    await body(app, pilot, fetch)

        asyncio.run(main())

    def test_shows_the_place_the_weather_now_and_a_row_per_day(self):
        async def body(app, pilot, fetch):
            fetch.assert_called_once_with("Victoria, BC")
            # The place found shows in the box, in full and in blue
            city = app.query_one("#weather-city", Input)
            self.assertEqual(city.value, "Victoria, British Columbia, Canada")
            self.assertTrue(city.has_class("-found"))
            self.assertEqual(city.styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            lines = shown(app)
            # How it feels (2° off) and the wind (8 km/h) are not worth saying
            self.assertTrue(lines[0].endswith("12°   Clear"))
            # Each icon in its sky's color: a clear night's moon yellow, rain blue
            view = app.query_one(ForecastView)
            rows = view.render().split("\n")
            yellow, blue = (app.get_css_variables()[name].lower() for name in ("yellow", "blue"))
            self.assertEqual(rows[0].get_style_at_offset(app.console, 0).color.triplet.hex, yellow)
            self.assertEqual(rows[2].get_style_at_offset(app.console, 12).color.triplet.hex, blue)
            self.assertTrue(lines[2].startswith("Today"))
            self.assertIn("Light rain", lines[2])
            # Today is dry from now on; no day before it to compare with
            self.assertTrue(lines[2].endswith("18° /   9°"))
            # The days are named from the forecast's own dates, today at the place first; Friday's
            # high is 5° under Thursday's, enough to say
            self.assertTrue(lines[3].startswith("Friday      "))
            self.assertTrue(lines[3].endswith("13° /  11°  ↓ 5°  Rain until 3am"))

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=VICTORIA)

    def test_the_rule_before_next_week_stops_before_when_it_rains(self):
        daily = {
            "time": [f"2026-10-{day:02}" for day in range(1, 9)],
            "weather_code": [0] * 8,
            "temperature_2m_max": [17.0] * 8,
            "temperature_2m_min": [9.0] * 8,
        }
        week = parse_forecast(PLACE, {**FORECAST, "daily": daily})

        async def body(app, pilot, fetch):
            lines = shown(app)
            self.assertEqual(lines[2 + 7], "─" * len(lines[2]))

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=week)

    def test_the_change_column_is_left_out_when_no_day_has_one(self):
        steady = parse_forecast(PLACE, {**FORECAST, "daily": {**FORECAST["daily"], "temperature_2m_max": [17.6, 17.0]}})

        async def body(app, pilot, fetch):
            self.assertTrue(shown(app)[3].endswith("17° /  11°    Rain until 3am"))

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=steady)

    def test_how_it_feels_and_the_wind_show_when_they_matter(self):
        windy = parse_forecast(PLACE, {**FORECAST, "current": {**FORECAST["current"], "apparent_temperature": 5.0, "wind_speed_10m": 42.0}})

        async def body(app, pilot, fetch):
            self.assertTrue(shown(app)[0].endswith("Clear   feels like 5° · wind 42 km/h"))

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=windy)

    def test_a_city_typed_in_the_box_is_looked_up_and_the_box_lets_go(self):
        async def body(app, pilot, fetch):
            self.assertIsNone(app.focused)
            city = app.query_one("#weather-city", Input)
            self.assertTrue(city.has_class("-found"))
            await pilot.click("#weather-city", offset=(10, 0))
            self.assertIs(app.focused, city)
            # Clicked, it is plain text, all selected, so typing replaces it; a second click places the cursor
            self.assertFalse(city.has_class("-found"))
            self.assertEqual(city.selected_text, city.value)
            await pilot.click("#weather-city", offset=(10, 0))
            self.assertEqual(city.selected_text, "")
            city.select_all()
            await pilot.press(*"Victoria, BC", "enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args_list[-1].args, ("Victoria, BC",))
            self.assertIsNone(app.focused)
            # An empty box asks nothing
            city.value = "  "
            await pilot.click("#weather-city")
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_count, 2)
            # Escape leaves the box without looking anything up, and without quitting
            await pilot.click("#weather-city")
            await pilot.press("escape")
            self.assertIsNone(app.focused)
            self.assertTrue(app.is_running)
            self.assertEqual(fetch.call_count, 2)

        self.run_view(Config(), body, return_value=VICTORIA)

    def test_the_box_completes_the_config_cities_and_enter_takes_them(self):
        async def body(app, pilot, fetch):
            city = app.query_one("#weather-city", Input)
            await pilot.click("#weather-city")
            city.value = ""
            # What the box shows while the city is looked up
            looking_up = []
            fetch.side_effect = lambda location: looking_up.append(city.value) or VICTORIA
            await pilot.press(*"chi", "enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args_list[-1].args, ("Chicago, IL",))
            self.assertEqual(looking_up, ["Chicago, IL"])
            # → takes the rest too; anything else is looked up as typed
            await pilot.click("#weather-city")
            city.value = ""
            await pilot.press(*"str", "right")
            self.assertEqual(city.value, "Strasbourg, FR")
            city.value = "Tokyo"
            await pilot.press("enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args_list[-1].args, ("Tokyo",))

        self.run_view(Config(locations=["Victoria, BC", "Chicago, IL", "Strasbourg, FR"]), body, return_value=VICTORIA)

    def test_c_and_f_switch_the_units_the_one_in_use_in_blue(self):
        async def body(app, pilot, fetch):
            celsius, fahrenheit = app.query_one("#units-metric"), app.query_one("#units-imperial")
            blue = app.get_css_variables()["blue"].lower()
            self.assertTrue(celsius.has_class("-selected"))
            self.assertEqual(celsius.styles.color.hex.lower(), blue)
            self.assertNotEqual(fahrenheit.styles.color.hex.lower(), blue)
            await pilot.click("#units-imperial")
            await settle(app, pilot)
            # Converted here, with no new request: 11.6°C is 53°F, and Thursday's high 64°F
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual((celsius.has_class("-selected"), fahrenheit.has_class("-selected")), (False, True))
            self.assertIn("53°", shown(app)[0])
            self.assertIn(" 64° ", shown(app)[2])
            self.assertIsNone(app.focused)

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=VICTORIA)

    def test_a_forecast_older_than_max_age_is_asked_again_when_the_tab_shows(self):
        async def body(app, pilot, fetch):
            view = app.view
            view.tab_shown()
            await settle(app, pilot)
            self.assertEqual(fetch.call_count, 1)
            with patch("outils.widgets.weather_view.time", return_value=time() + MAX_AGE + 1):
                view.tab_shown()
                await settle(app, pilot)
            self.assertEqual(fetch.call_args_list, [call("Victoria, BC")] * 2)

        self.run_view(Config(locations=["Victoria, BC"]), body, return_value=VICTORIA)

    def test_an_error_shows_in_the_view_and_the_footer(self):
        async def body(app, pilot, fetch):
            self.assertEqual(shown(app), ["Cannot reach Open-Meteo: no network"])
            self.assertEqual(app.messages, ["Cannot reach Open-Meteo: no network"])

        self.run_view(Config(locations=["Victoria, BC"]), body, side_effect=WeatherError("Cannot reach Open-Meteo: no network"))


class SpansTest(unittest.TestCase):
    def test_each_span_is_said_with_its_kind_where_it_changes(self):
        def said(spans):
            return ", ".join(words for kind, words in _said([Span(*span) for span in spans]))

        self.assertEqual(said([("rain", 8, 13), ("rain", 18, 22)]), "Rain 8am–1pm, 6pm–10pm")
        self.assertEqual(said([("rain", 17, 18), ("snow", 20, 22)]), "Rain 5pm–6pm, snow 8pm–10pm")
        self.assertEqual(said([("storm", None, 9), ("rain", 18, None)]), "Storm until 9am, rain after 6pm")
        self.assertEqual(said([("rain", 15, 21)]), "Rain 3pm–9pm")
        self.assertEqual(said([("snow", None, None)]), "Snow all day")
        self.assertEqual([kind for kind, words in _said([Span("rain", 1, 2), Span("snow", 5, 6)])], ["rain", "snow"])


class WeatherModeTest(unittest.TestCase):
    def test_the_app_keys_work_until_the_box_is_clicked(self):
        async def main():
            app = OutilsApp("weather", Config(theme="onedark"))
            with patch("outils.widgets.weather_view.forecast", return_value=VICTORIA) as fetch:
                async with app.run_test(size=(89, 23)) as pilot:
                    await settle(app, pilot)
                    # Portland, OR when the config names nowhere
                    fetch.assert_called_once_with("Portland, OR")
                    self.assertIsNone(app.focused)
                    await pilot.press("question_mark")
                    await pilot.pause()
                    self.assertEqual(type(app.screen).__name__, "OutilsHelpScreen")

        asyncio.run(main())

    def test_tab_in_the_box_takes_the_suggestion_and_switches_tabs_elsewhere(self):
        async def main():
            app = OutilsApp("weather", Config(theme="onedark", locations=["Portland, OR", "Corvallis, OR"]))
            with patch("outils.widgets.weather_view.forecast", return_value=VICTORIA):
                async with app.run_test(size=(89, 23)) as pilot:
                    await settle(app, pilot)
                    city = app.query_one("#weather-city", Input)
                    await pilot.click("#weather-city")
                    await pilot.press(*"cor")
                    await pilot.pause()
                    await pilot.press("tab")
                    self.assertEqual((city.value, app.mode, app.focused), ("Corvallis, OR", "weather", city))
                    # With nothing to take, it stays in the box
                    await pilot.press("tab")
                    self.assertEqual((app.mode, app.focused), ("weather", city))
                    await pilot.press("escape", "tab")
                    self.assertNotEqual(app.mode, "weather")

        asyncio.run(main())

    def test_the_units_picked_are_saved_to_the_config(self):
        async def main():
            with tempfile.TemporaryDirectory() as tmp:
                config_file = Path(tmp) / "config.yaml"
                config_file.write_text("theme: onedark\nlocation: Victoria, BC\n")
                app = OutilsApp("weather", Config(theme="onedark"))
                with patch("outils.widgets.weather_view.forecast", return_value=VICTORIA), patch("outils.app.CONFIG_FILE", config_file):
                    async with app.run_test(size=(89, 23)) as pilot:
                        await settle(app, pilot)
                        await pilot.click("#units-imperial")
                        await settle(app, pilot)
                self.assertEqual(config_file.read_text(), "theme: onedark\nlocation: Victoria, BC\nunits: imperial\n")

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
