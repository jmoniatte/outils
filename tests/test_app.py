import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tui_kit.help_screen import HelpScreen
from tui_kit.theme_picker import ThemePicker
from textual.widgets import TabbedContent

from outils.app import MODES, FooterMessage, OutilsApp
from outils.config import Config
from outils.ipinfo import IpInfoError
from outils.nmcli import Scan
from outils.pactl import SINK, Device, Mixer
from outils.weather import WeatherError
from outils.widgets import CalendarView


SPEAKERS = Device(SINK, 1, "laptop", "Laptop speakers", 80, False, default=True)


def help_keys(app) -> dict[str, list[str]]:
    """Help's keys by column title: General, then the tab's name in capitals."""
    return {
        str(column.query_one(".section-title").render()).replace("GENERAL", "General"): [
            key.render().plain for key in column.query(".shortcut-key")
        ]
        for column in app.screen.query(".shortcuts-section")
    }


def screen_row(app, y: int) -> str:
    """The text on row y of the screen."""
    return "".join(segment.text for segment in app.screen._compositor.render_strips()[y])


class AppTest(unittest.TestCase):
    def run_app(self, body, mode="calendar", config=None):
        async def main():
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"),
                # The modes that ask a service get no answer: the tests never reach the network
                patch("outils.widgets.weather_view.forecast", side_effect=WeatherError("offline")) as self.forecast,
                patch("outils.widgets.ip_view.fetch", side_effect=IpInfoError("offline")) as self.fetch,
                # Nor the Dropbox client on this computer
                patch("outils.widgets.dropbox_view.status", return_value="Up to date"),
                patch("outils.widgets.dropbox_view.recent", return_value=[]),
                # Nor pactl and bluetoothctl: one output in use, no headphones
                patch("outils.pactl.mixer", return_value=Mixer(outputs=[SPEAKERS])) as self.mixer,
                patch("outils.bluetooth.headsets", return_value=[]),
                # Nor nmcli: Wi-Fi on, nothing in range
                patch("outils.nmcli.wifi_enabled", return_value=True),
                patch("outils.nmcli.connectivity", return_value="full"),
                patch("outils.nmcli.scan", return_value=Scan([], [])) as self.scan,
            ):
                app = OutilsApp(mode, config or Config(theme="onedark"))
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    await body(app, pilot)

        asyncio.run(main())

    def test_opens_on_the_mode_named_and_tab_moves_to_the_next(self):
        for mode in MODES:
            async def body(app, pilot, mode=mode):
                tabs = app.query_one("#modes", TabbedContent)
                # No title bar: the tabs are the first row
                self.assertFalse(app.query("#app-header"))
                self.assertEqual(tabs.region.y, 0)
                self.assertEqual([str(tabs.get_tab(f"{name}-mode").label) for name in MODES], ["Calendar", "Time", "Weather", "IP", "Sound", "Wi-Fi", "Dropbox", "Life", "Snake"])
                self.assertEqual(app.mode, mode)

            with self.subTest(mode=mode):
                self.run_app(body, mode)

        async def body(app, pilot):
            # Only the mode on show asks its service, and only the first time
            self.assertEqual((self.forecast.call_count, self.fetch.call_count, self.mixer.call_count, self.scan.call_count), (0, 0, 0, 0))
            self.assertIsInstance(app.focused, CalendarView)
            shown = []
            for _ in range(10):
                await pilot.press("tab")
                await pilot.pause()
                await app.workers.wait_for_complete()
                await pilot.pause()
                shown.append((app.mode, app.focused))
            self.assertEqual([mode for mode, _ in shown], ["time", "weather", "ip", "sound", "wifi", "dropbox", "life", "snake", "calendar", "time"])
            # The calendar, Sound's cards, Wi-Fi's list, Dropbox, Life and Snake keep focus for their keys; nothing else takes it, so ?, t and q work
            self.assertEqual([type(focused).__name__ for _, focused in shown], ["NoneType", "NoneType", "NoneType", "DeviceCard", "NetworksTable", "DropboxView", "LifeView", "SnakeView", "CalendarView", "NoneType"])
            # Hidden, Sound asks pactl no more
            calls = self.mixer.call_count
            await pilot.pause(2.5)
            self.assertEqual(self.mixer.call_count, calls)
            await app.workers.wait_for_complete()
            self.assertEqual((self.forecast.call_count, self.fetch.call_count), (1, 1))
            # Help lists the keys of the mode on show, and tab does not switch under it
            await pilot.press("question_mark")
            await pilot.pause()
            # Time has no keys of its own: its column is empty, but keeps its width
            self.assertEqual(help_keys(app), {"General": ["?", "t", "y", "tab", "q"], "TIME": []})
            self.assertEqual(app.screen.query_one("#shortcuts-time").size.width, 24)
            await pilot.press("tab")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)
            self.assertEqual(app.mode, "time")

        self.run_app(body)

    def test_weather_and_ip_credit_their_service_over_the_rule_with_a_link(self):
        async def body(app, pilot):
            credit = app.query_one("#mode-credit")
            link = app.query_one("#mode-credit-link")
            self.assertFalse(credit.display)
            for text, url in (("Data by open-meteo.com", "https://open-meteo.com"), ("Data by ipinfo.io", "https://ipinfo.io")):
                await pilot.press("tab")
                await pilot.pause()
                self.assertTrue(credit.display)
                line = screen_row(app, credit.region.y)
                self.assertEqual(line.rstrip(), " " * (app.size.width - 1 - len(text)) + text)
                self.assertEqual(credit.region.bottom, app.query_one("#app-footer-bar").region.y)
                self.assertEqual(link.url, url)
            # Blue, underlined only under the mouse
            self.assertEqual(link.styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            self.assertFalse(link.styles.text_style.underline)
            await pilot.hover("#mode-credit-link")
            await pilot.pause()
            self.assertTrue(link.styles.text_style.underline)
            # A click opens the site and leaves focus where it was
            with patch.object(app, "open_url") as open_url:
                await pilot.click("#mode-credit-link")
                await pilot.pause()
            open_url.assert_called_once_with("https://ipinfo.io")
            self.assertIsNone(app.focused)

        # The tab before the weather, which has no credit either
        self.run_app(body, "time")

    def test_the_calendar_shows_today_in_full_where_the_credits_go_then_the_next_tab_does_not(self):
        async def body(app, pilot):
            credit = app.query_one("#mode-credit")
            today = app.query_one(CalendarView).today
            text = f"{today:%A, %B} {today.day}, {today.year}"
            self.assertTrue(credit.display)
            self.assertFalse(app.query_one("#mode-credit-link").display)
            label = app.query_one("#mode-credit-text")
            self.assertEqual(label.styles.color.hex.lower(), app.get_css_variables()["blue"].lower())
            line = screen_row(app, credit.region.y)
            self.assertEqual(line.rstrip(), " " * (app.size.width - 1 - len(text)) + text)
            await pilot.press("tab")
            await pilot.pause()
            self.assertFalse(credit.display)
            await pilot.press("tab")
            await pilot.pause()
            self.assertTrue(app.query_one("#mode-credit-link").display)
            # A credit's words stay grey
            self.assertEqual(label.styles.color.hex.lower(), app.get_css_variables()["comment"].lower())

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
        for mode in MODES:
            async def body(app, pilot):
                footer = app.query_one("#app-footer")
                close = app.query_one("#btn-close")
                self.assertEqual(footer.region.bottom, app.size.height)
                self.assertEqual(close.region.y, app.size.height - 1)
                self.assertEqual(close.region.x, 1)
                self.assertEqual(app.query_one("#app-footer-bar").styles.border_top[0], "solid")
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
            # The keys every tab shares on the left, the tab's own on the right under its name
            self.assertEqual(help_keys(app), {"General": ["?", "t", "y", "tab", "q"], "CALENDAR": ["←", "→"]})
            columns = list(app.screen.query(".shortcuts-section"))
            self.assertEqual([column.id for column in columns], ["shortcuts-general", "shortcuts-calendar"])
            self.assertLess(columns[0].region.x, columns[1].region.x)
            await pilot.press("escape", "t")
            await pilot.pause()
            self.assertIsInstance(app.screen, ThemePicker)

        self.run_app(body)

    def test_a_message_that_fits_stays_on_one_line(self):
        async def body(app, pilot):
            app.notify("Playing on a device with a much longer name than any real one would have here")
            await pilot.pause()
            self.assertEqual(app.query_one(FooterMessage).size.height, 1)

        self.run_app(body)

    def test_a_message_takes_helps_place_on_the_right_until_it_clears(self):
        async def body(app, pilot):
            message = app.query_one(FooterMessage)
            help_button = app.query_one("#btn-help")
            self.assertEqual(message.render().plain, "Config file is not valid YAML: oops")
            self.assertTrue(message.has_class("-warning"))
            self.assertFalse(help_button.display)
            # On the last row, ending where Help ends, on the right
            bar = app.query_one("#app-footer-bar")
            self.assertEqual((message.region.right, message.region.y), (bar.content_region.right, app.size.height - 1))
            self.assertEqual(message.styles.text_align, "right")
            message.clear_notification()
            # Help comes back only once the message is off the screen
            self.assertFalse(help_button.display)
            await pilot.pause()
            await pilot.pause()
            self.assertTrue(help_button.display)
            self.assertEqual(help_button.region.right, bar.content_region.right)
            self.assertFalse(message.display)
            # Help opens the shortcuts, and never takes focus from the mode
            await pilot.click("#btn-help")
            await pilot.pause()
            self.assertIsInstance(app.screen, HelpScreen)

        self.run_app(body, config=Config(warnings=["Config file is not valid YAML: oops"]))


if __name__ == "__main__":
    unittest.main()
