import asyncio
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Input

from outils.app import OutilsApp, load_stylesheet
from outils.config import Config
from outils.weather import IMPERIAL, METRIC, WeatherError, parse_forecast
from outils.widgets import WeatherView
from outils.widgets.weather_view import ForecastView
from tui_kit.theme import load_palette

from test_weather import FORECAST, PLACE

VICTORIA = parse_forecast(PLACE, METRIC, FORECAST)


class Host(App):
    CSS = load_stylesheet()
    AUTO_FOCUS = None

    def __init__(self, view: WeatherView) -> None:
        super().__init__()
        self.view = view
        self.messages: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield self.view

    def notify(self, message, **kwargs) -> None:
        self.messages.append(message)


def shown(app: App) -> list[str]:
    return [line.rstrip() for line in app.query_one(ForecastView).render().plain.split("\n")]


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


class WeatherViewTest(unittest.TestCase):
    def run_view(self, config, body, **patches):
        async def main():
            app = Host(WeatherView(config, today=date(2026, 9, 24)))
            with patch("outils.widgets.weather_view.forecast", **patches) as fetch:
                async with app.run_test(size=(90, 24)) as pilot:
                    await settle(app, pilot)
                    await body(app, pilot, fetch)

        asyncio.run(main())

    def test_shows_the_place_the_weather_now_and_a_row_per_day(self):
        async def body(app, pilot, fetch):
            fetch.assert_called_once_with("Victoria, BC", METRIC)
            # The place found shows in the box, in full and in blue
            city = app.query_one("#weather-city", Input)
            self.assertEqual(city.value, "Victoria, British Columbia, Canada")
            self.assertTrue(city.has_class("-found"))
            self.assertEqual(city.styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            lines = shown(app)
            self.assertIn("12°C   Clear", lines[0])
            self.assertEqual(lines[1], "    Feels like 9°C  ·  Wind 8 km/h  ·  Humidity 65 %  ·  Rain 0 mm")
            self.assertTrue(lines[3].startswith("Today"))
            self.assertIn("Light rain", lines[3])
            self.assertIn("18° /   9°      79 %      6.5 mm", lines[3])
            # A day with no chance of rain given shows a dash
            self.assertTrue(lines[4].startswith("Friday      "))
            self.assertIn("  – %", lines[4])

        self.run_view(Config(location="Victoria, BC"), body, return_value=VICTORIA)

    def test_a_city_typed_in_the_box_is_looked_up_and_the_box_lets_go(self):
        async def body(app, pilot, fetch):
            self.assertIsNone(app.focused)
            city = app.query_one("#weather-city", Input)
            self.assertTrue(city.has_class("-found"))
            await pilot.click("#weather-city")
            self.assertIs(app.focused, city)
            # Clicked, it is plain text to type over
            self.assertFalse(city.has_class("-found"))
            city.value = ""
            await pilot.press(*"Victoria, BC", "enter")
            await settle(app, pilot)
            self.assertEqual(fetch.call_args_list[-1].args, ("Victoria, BC", METRIC))
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

    def test_c_and_f_switch_the_units_the_one_in_use_in_blue(self):
        async def body(app, pilot, fetch):
            celsius, fahrenheit = app.query_one("#units-metric"), app.query_one("#units-imperial")
            blue = app.get_css_variables()["blue"].lower()
            self.assertTrue(celsius.has_class("-selected"))
            self.assertEqual(celsius.styles.color.hex.lower(), blue)
            self.assertNotEqual(fahrenheit.styles.color.hex.lower(), blue)
            await pilot.click("#units-imperial")
            await settle(app, pilot)
            # The same place asked again, in the other units, and the box keeps it
            self.assertEqual(fetch.call_args_list[-1].args, ("Victoria, BC", IMPERIAL))
            self.assertEqual((celsius.has_class("-selected"), fahrenheit.has_class("-selected")), (False, True))
            self.assertIn("°F", shown(app)[0])
            self.assertIsNone(app.focused)
            # The one in use asks nothing
            await pilot.click("#units-imperial")
            await settle(app, pilot)
            self.assertEqual(fetch.call_count, 2)

        self.run_view(Config(location="Victoria, BC"), body, side_effect=lambda location, units: parse_forecast(PLACE, units, FORECAST))

    def test_an_error_shows_in_the_view_and_the_header(self):
        async def body(app, pilot, fetch):
            self.assertEqual(shown(app), ["Cannot reach Open-Meteo: no network"])
            self.assertEqual(app.messages, ["Cannot reach Open-Meteo: no network"])

        self.run_view(Config(location="Victoria, BC"), body, side_effect=WeatherError("Cannot reach Open-Meteo: no network"))


class WeatherModeTest(unittest.TestCase):
    def test_the_app_keys_work_until_the_box_is_clicked(self):
        async def main():
            app = OutilsApp("weather", Config(theme="onedark"))
            with patch("outils.widgets.weather_view.forecast", return_value=VICTORIA) as fetch:
                async with app.run_test(size=(90, 24)) as pilot:
                    await settle(app, pilot)
                    # Portland, OR when the config names nowhere
                    fetch.assert_called_once_with("Portland, OR", METRIC)
                    self.assertIsNone(app.focused)
                    await pilot.press("question_mark")
                    await pilot.pause()
                    self.assertEqual(type(app.screen).__name__, "OutilsHelpScreen")

        asyncio.run(main())

    def test_the_units_picked_are_saved_to_the_config(self):
        async def main():
            with tempfile.TemporaryDirectory() as tmp:
                config_file = Path(tmp) / "config.yaml"
                config_file.write_text("theme: onedark\nlocation: Victoria, BC\n")
                app = OutilsApp("weather", Config(theme="onedark"))
                with patch("outils.widgets.weather_view.forecast", return_value=VICTORIA), patch("outils.app.CONFIG_FILE", config_file):
                    async with app.run_test(size=(90, 24)) as pilot:
                        await settle(app, pilot)
                        await pilot.click("#units-imperial")
                        await settle(app, pilot)
                self.assertEqual(config_file.read_text(), "theme: onedark\nlocation: Victoria, BC\nunits: imperial\n")

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
