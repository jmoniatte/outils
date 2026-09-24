import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ouikit.help_screen import HelpScreen
from ouikit.theme_picker import ThemePicker

from outils.app import OutilsApp
from outils.config import Config
from outils.widgets import CalendarView, WeatherView


class AppTest(unittest.TestCase):
    def run_app(self, body, mode="calendar", config=None):
        async def main():
            with tempfile.TemporaryDirectory() as tmp, patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"):
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

    def test_help_lists_every_key_and_t_opens_the_theme_picker(self):
        async def body(app, pilot):
            await pilot.press("question_mark")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            keys = [key.render().plain for key in app.screen.query(".shortcut-key")]
            self.assertEqual(keys, ["←", "→", "?", "t", "q"])
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
