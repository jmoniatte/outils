import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ouikit.help_screen import HelpScreen
from ouikit.theme_picker import ThemePicker

from outils.app import OutilsApp
from outils.config import Config
from outils.ipinfo import IpInfoError
from outils.weather import WeatherError
from outils.widgets import CalendarView, WeatherView


class AppTest(unittest.TestCase):
    def run_app(self, body, mode="calendar", config=None):
        async def main():
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"),
                # The modes that ask a service get no answer: the tests never reach the network
                patch("outils.widgets.weather_view.forecast", side_effect=WeatherError("offline")),
                patch("outils.widgets.ip_view.fetch", side_effect=IpInfoError("offline")),
            ):
                app = OutilsApp(mode, config or Config(theme="onedark"))
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await body(app, pilot)

        asyncio.run(main())

    def test_each_mode_shows_only_its_own_view_and_names_it_in_the_header(self):
        for mode, view, other, label in (("calendar", CalendarView, WeatherView, "Calendar"), ("weather", WeatherView, CalendarView, "Weather")):
            async def body(app, pilot, view=view, other=other, label=label):
                self.assertEqual(app.query_one("#app-title").render().plain, "outils")
                self.assertEqual(app.query_one("#mode-name").render().plain, label)
                self.assertEqual(len(app.query(view)), 1)
                self.assertEqual(len(app.query(other)), 0)

            with self.subTest(mode=mode):
                self.run_app(body, mode)

    def test_every_mode_ends_with_a_rule_and_close_at_the_bottom_left(self):
        for mode in ("calendar", "weather", "ip"):
            async def body(app, pilot):
                footer = app.query_one("#app-footer")
                close = app.query_one("#btn-close")
                self.assertEqual(footer.region.bottom, app.size.height)
                self.assertEqual(close.region.y, app.size.height - 1)
                self.assertEqual(close.region.x, 1)
                self.assertEqual(footer.styles.border_top[0], "solid")
                # Clicking it quits, and it never takes focus from the mode
                await pilot.click("#btn-close")
                await pilot.pause()
                self.assertFalse(app.is_running)

            with self.subTest(mode=mode):
                self.run_app(body, mode)

    def test_help_lists_every_key_and_t_opens_the_theme_picker(self):
        async def body(app, pilot):
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            keys = [key.render().plain for key in app.screen.query(".shortcut-key")]
            self.assertEqual(keys, ["←", "→", "?", "t", "y", "q"])
            await pilot.press("escape", "t")
            await pilot.pause()
            self.assertIsInstance(app.screen, ThemePicker)

        self.run_app(body)

    def test_config_warnings_show_in_the_header(self):
        async def body(app, pilot):
            header = app.query_one("HeaderNotification")
            self.assertEqual(header.render().plain, "Config file is not valid YAML: oops")
            self.assertTrue(header.has_class("-warning"))

        self.run_app(body, config=Config(warnings=["Config file is not valid YAML: oops"]))


if __name__ == "__main__":
    unittest.main()
