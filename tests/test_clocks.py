import asyncio
import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from textual.app import App, ComposeResult

from outils.app import load_stylesheet
from outils.clocks import Clock, Reading, read
from outils.config import Config
from outils.widgets import ClocksView
from outils.widgets.clocks_view import DST_ICON
from ouikit.theme import load_palette

SUMMER = datetime(2026, 9, 25, 5, 4, 30, tzinfo=UTC)
WINTER = datetime(2026, 1, 15, 5, 4, tzinfo=UTC)


def clock(name, zone):
    return Clock(name, ZoneInfo(zone))


class ReadTest(unittest.TestCase):
    def test_the_time_the_offset_and_summer_time(self):
        portland = clock("Portland", "America/Los_Angeles")
        self.assertEqual(read(portland, SUMMER), Reading("Portland", "22:04", "-07:00", True))
        self.assertEqual(read(portland, WINTER), Reading("Portland", "21:04", "-08:00", False))
        self.assertEqual(read(clock("UTC", "UTC"), SUMMER), Reading("UTC", "05:04", "+00:00", False))
        self.assertEqual(read(clock("Strasbourg", "Europe/Paris"), SUMMER), Reading("Strasbourg", "07:04", "+02:00", True))
        # Half hours, either side of UTC
        self.assertEqual(read(clock("Delhi", "Asia/Kolkata"), SUMMER).offset, "+05:30")
        self.assertEqual(read(clock("St. John's", "America/St_Johns"), WINTER).offset, "-03:30")


class Host(App):
    CSS = load_stylesheet()

    def __init__(self, view: ClocksView) -> None:
        super().__init__()
        self.view = view

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield self.view


class ClocksViewTest(unittest.TestCase):
    def test_a_row_per_clock_redrawn_when_the_minute_turns(self):
        now = [SUMMER]
        view = ClocksView(Config().clocks, lambda: now[0])

        async def main():
            async with Host(view).run_test(size=(60, 8)) as pilot:
                await pilot.pause()
                self.assertEqual(
                    view.render().plain.split("\n"),
                    [
                        f"Portland     22:04   -07:00 {DST_ICON}",
                        f"Chicago      00:04   -05:00 {DST_ICON}",
                        "UTC          05:04   +00:00",
                        f"Strasbourg   07:04   +02:00 {DST_ICON}",
                    ],
                )
                # The sun in yellow, the offset before it in orange
                text = view.render()
                colors = {text.plain[span.start:span.end].strip(): span.style.color.triplet.hex for span in text.spans}
                palette = load_palette("onedark")
                self.assertEqual(colors[DST_ICON].lower(), palette["yellow"].lower())
                self.assertEqual(colors["-07:00"].lower(), palette["orange"].lower())
                now[0] = SUMMER.replace(minute=5, second=1)
                view.tick()
                self.assertEqual(view.render().plain.split("\n")[2], "UTC          05:05   +00:00")

        asyncio.run(main())
        self.assertFalse(ClocksView([]).display)


if __name__ == "__main__":
    unittest.main()
