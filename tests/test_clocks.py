import asyncio
import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tui_kit.theme import load_palette

from outils.clocks import Clock, Reading, read, suggested_zones, zone_named
from outils.config import Config
from outils.widgets import ClocksView
from outils.widgets.clocks_view import DST_ICON, fit_name

from tests.host import Host

SUMMER = datetime(2026, 9, 25, 5, 4, 30, tzinfo=UTC)
WINTER = datetime(2026, 1, 15, 5, 4, tzinfo=UTC)


def clock(name, zone):
    return Clock(name, ZoneInfo(zone))


class ReadTest(unittest.TestCase):
    def test_the_time_the_offset_and_summer_time(self):
        portland = clock("Portland", "America/Los_Angeles")
        self.assertEqual(read(portland, SUMMER), Reading("Portland", "22:04", "-07:00", True, "America/Los_Angeles"))
        self.assertEqual(read(portland, WINTER), Reading("Portland", "21:04", "-08:00", False, "America/Los_Angeles"))
        self.assertEqual(read(clock("UTC", "UTC"), SUMMER), Reading("UTC", "05:04", "+00:00", False, "UTC"))
        self.assertEqual(read(clock("Strasbourg", "Europe/Paris"), SUMMER), Reading("Strasbourg", "07:04", "+02:00", True, "Europe/Paris"))
        # Half hours, either side of UTC
        self.assertEqual(read(clock("Delhi", "Asia/Kolkata"), SUMMER).offset, "+05:30")
        self.assertEqual(read(clock("St. John's", "America/St_Johns"), WINTER).offset, "-03:30")


class ZoneTest(unittest.TestCase):
    def test_a_time_zone_is_named_case_ignored_and_a_city_is_not_one(self):
        self.assertEqual(zone_named("america/los_angeles"), clock("Los Angeles", "America/Los_Angeles"))
        self.assertEqual(zone_named(" UTC "), clock("UTC", "UTC"))
        self.assertEqual((zone_named("Paris"), zone_named("Tokyo"), zone_named("")), (None, None, None))
        # Suggested: UTC, then today's "Area/City" names, not the offsets or old aliases
        zones = suggested_zones()
        self.assertEqual(zones[0], "UTC")
        self.assertIn("America/Los_Angeles", zones)
        self.assertFalse(any(zone.startswith(("Etc/", "US/")) for zone in zones))


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
                        f"Portland            22:04   -07:00 {DST_ICON}   America/Los_Angeles",
                        f"Chicago             00:04   -05:00 {DST_ICON}   America/Chicago",
                        "UTC                 05:04   +00:00     UTC",
                        f"Strasbourg          07:04   +02:00 {DST_ICON}   Europe/Paris",
                    ],
                )
                # The sun in yellow, the offset before it in orange, the zone after it grey
                text = view.render()
                colors = {text.plain[span.start:span.end].strip(): span.style.color.triplet.hex for span in text.spans}
                palette = load_palette("onedark")
                self.assertEqual(colors[DST_ICON].lower(), palette["yellow"].lower())
                self.assertEqual(colors["-07:00"].lower(), palette["orange"].lower())
                self.assertEqual(colors["America/Los_Angeles"].lower(), palette["comment"].lower())
                now[0] = SUMMER.replace(minute=5, second=1)
                view.tick()
                self.assertEqual(view.render().plain.split("\n")[2], "UTC                 05:05   +00:00     UTC")

        asyncio.run(main())
        self.assertFalse(ClocksView([]).display)
        # A name too long for its column is cut, so the times stay lined up
        self.assertEqual((fit_name("Llanfairpwllgwyngyll"), fit_name("Rio de Janeiro")), ("Llanfairpwllgwyng…", "Rio de Janeiro"))


if __name__ == "__main__":
    unittest.main()
