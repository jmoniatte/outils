import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ouikit.help_screen import HelpScreen
from ouikit.theme_picker import ThemePicker
from textual.widgets import TabbedContent

from outils.app import OutilsApp
from outils.config import Config
from outils.ipinfo import IpInfoError
from outils.weather import WeatherError
from outils.widgets import CalendarView


class AppTest(unittest.TestCase):
    def run_app(self, body, mode="calendar", config=None):
        async def main():
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"),
                # The modes that ask a service get no answer: the tests never reach the network
                patch("outils.widgets.weather_view.forecast", side_effect=WeatherError("offline")) as self.forecast,
                patch("outils.widgets.ip_view.fetch", side_effect=IpInfoError("offline")) as self.fetch,
            ):
                app = OutilsApp(mode, config or Config(theme="onedark"))
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await body(app, pilot)

        asyncio.run(main())

    def test_opens_on_the_mode_named_and_tab_moves_to_the_next(self):
        for mode in ("calendar", "weather", "ip"):
            async def body(app, pilot, mode=mode):
                tabs = app.query_one("#modes", TabbedContent)
                self.assertEqual(app.query_one("#app-title").render().plain, "outils")
                self.assertEqual([str(tabs.get_tab(f"{name}-mode").label) for name in ("calendar", "weather", "ip")], ["Calendar", "Weather", "IP"])
                self.assertEqual(app.mode, mode)

            with self.subTest(mode=mode):
                self.run_app(body, mode)

        async def body(app, pilot):
            # Only the mode on show asks its service, and only the first time
            self.assertEqual((self.forecast.call_count, self.fetch.call_count), (0, 0))
            self.assertIsInstance(app.focused, CalendarView)
            shown = []
            for _ in range(4):
                await pilot.press("tab")
                await pilot.pause()
                shown.append((app.mode, app.focused))
            self.assertEqual([mode for mode, _ in shown], ["weather", "ip", "calendar", "weather"])
            # The calendar keeps focus for its arrows; nothing else takes it, so ?, t and q work
            self.assertEqual([type(focused).__name__ for _, focused in shown], ["NoneType", "NoneType", "CalendarView", "NoneType"])
            await app.workers.wait_for_complete()
            self.assertEqual((self.forecast.call_count, self.fetch.call_count), (1, 1))
            # Help lists the keys of the mode on show, and tab does not switch under it
            await pilot.press("question_mark")
            await pilot.pause()
            keys = [key.render().plain for key in app.screen.query(".shortcut-key")]
            self.assertEqual(keys, ["?", "t", "y", "tab", "q"])
            await pilot.press("tab")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            self.assertEqual(app.mode, "weather")

        self.run_app(body)

    def test_a_click_on_a_tab_shows_its_mode(self):
        async def body(app, pilot):
            tabs = app.query_one("#modes", TabbedContent)
            await pilot.click(f"#{tabs.get_tab('weather-mode').id}")
            await pilot.pause()
            self.assertEqual(app.mode, "weather")
            self.assertIsNone(app.focused)
            await pilot.click(f"#{tabs.get_tab('calendar-mode').id}")
            await pilot.pause()
            self.assertIsInstance(app.focused, CalendarView)

        self.run_app(body, "ip")

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
            self.assertEqual(keys, ["←", "→", "?", "t", "y", "tab", "q"])
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
