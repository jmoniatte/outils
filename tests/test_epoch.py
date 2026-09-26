import asyncio
import time
import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tui_kit.theme import load_palette

from outils.config import Config
from outils.epoch import EpochError, parse, relative, rows
from outils.widgets import TimeView

from tests.host import Host

NOW = datetime(2026, 9, 25, 5, 4, tzinfo=UTC)
PORTLAND = ZoneInfo("America/Los_Angeles")


def convert(text):
    return dict(rows(parse(text, NOW, PORTLAND), NOW, PORTLAND))


class EpochTest(unittest.TestCase):
    def test_a_timestamp_is_seconds_or_milliseconds_with_13_digits(self):
        seconds = convert("1790222400")
        self.assertEqual(seconds["UTC"], "2026-09-24T04:00:00+00:00")
        self.assertEqual(seconds["Local"], "2026-09-23T21:00:00-07:00")
        self.assertEqual(seconds["Relative"], "1 day ago")
        fraction = convert("1790222400.123")
        self.assertEqual((fraction["Seconds"], fraction["UTC"], fraction["Local"]), ("1790222400.123", "2026-09-24T04:00:00.123+00:00", "2026-09-23T21:00:00.123-07:00"))
        millis = convert("1790222400123")
        self.assertEqual((millis["Seconds"], millis["UTC"]), ("1790222400.123", "2026-09-24T04:00:00.123+00:00"))
        # 12 digits are still seconds: year 5138, not 1973
        self.assertEqual(convert("100000000000")["UTC"], "5138-11-16T09:46:40+00:00")
        # Nothing longer than milliseconds
        with self.assertRaises(EpochError):
            parse("1790222400123456", NOW)
        self.assertEqual(convert("-1")["UTC"], "1969-12-31T23:59:59+00:00")
        self.assertEqual(convert("-1.5")["Seconds"], "-1.5")

    def test_a_date_is_local_time_unless_it_gives_an_offset(self):
        summer = convert("2026-09-24 15:30")
        self.assertEqual((summer["Seconds"], summer["UTC"]), ("1790289000", "2026-09-24T22:30:00+00:00"))
        self.assertEqual(convert("2026-01-15")["UTC"], "2026-01-15T08:00:00+00:00")
        self.assertEqual(convert("2026-01-15")["Local"], "2026-01-15T00:00:00-08:00")
        zulu = convert("2026-09-24T22:30Z")
        self.assertEqual(zulu["Seconds"], "1790289000")
        self.assertEqual(convert("2026-09-25T00:30:00+02:00")["Seconds"], "1790289000")
        # Empty, or now, is now
        self.assertEqual(convert("")["Relative"], "now")
        self.assertEqual(convert(" now ")["Relative"], "now")

    def test_what_is_neither_says_so(self):
        for text in ("abc", "1e5", "2026-13-01", "99999999999999999999999"):
            with self.subTest(text=text), self.assertRaises(EpochError):
                parse(text, NOW)

    def test_relative_takes_the_largest_unit(self):
        self.assertEqual(relative(datetime(2026, 9, 25, 7, 5, tzinfo=UTC), NOW), "in 2 hours")
        self.assertEqual(relative(datetime(2026, 9, 25, 5, 3, tzinfo=UTC), NOW), "1 minute ago")
        self.assertEqual(relative(datetime(2020, 1, 1, tzinfo=UTC), NOW), "6 years ago")


class TimeViewTest(unittest.TestCase):
    def run_view(self, body):
        async def main():
            app = Host(TimeView(Config()))
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await body(app, pilot, app.view)

        asyncio.run(main())

    def test_enter_in_the_box_converts_under_it_and_an_error_shows_in_red(self):
        async def body(app, pilot, view):
            details = app.query_one("#epoch-details")
            box = app.query_one("#epoch-input")
            # It opens on now, in seconds, in the box and under it
            self.assertLessEqual(abs(int(box.value) - time.time()), 2)
            self.assertTrue(box.has_class("-found"))
            self.assertEqual(details.render().plain.split("\n")[0], f"Seconds   {box.value}")
            self.assertTrue(details.render().plain.endswith("Relative  now"))
            # The box starts where the values do
            self.assertEqual(box.region.x, details.region.x + len("Relative  "))
            # Clicked first: while the box has focus, now no longer fills it
            await pilot.click("#epoch-input")
            box.value = ""
            await pilot.press(*"1790222400", "enter")
            await pilot.pause()
            lines = details.render().plain.split("\n")
            self.assertEqual(lines[:2], ["Seconds   1790222400", "UTC       2026-09-24T04:00:00+00:00"])
            # The box lets go, so ?, t and q work again, and turns blue; the values stay plain
            self.assertIsNone(app.focused)
            self.assertTrue(app.query_one("#epoch-input").has_class("-found"))
            text = details.render()
            self.assertEqual([text.plain[span.start:span.end].strip() for span in text.spans], ["Seconds", "UTC", "Local", "Relative"])
            await pilot.click("#epoch-input")
            box.value = ""
            await pilot.press(*"soon", "enter")
            await pilot.pause()
            self.assertEqual(details.render().plain, "Not a timestamp or a date such as 2026-09-24 15:30: soon")
            self.assertEqual(details.render().style.color.triplet.hex.lower(), load_palette("onedark")["red"].lower())

        self.run_view(body)

    def test_the_box_follows_now_until_it_is_used(self):
        async def body(app, pilot, view):
            box = app.query_one("#epoch-input")
            # As if a second had gone by since
            view.shown = box.value = "1"
            view.follow_now()
            self.assertLessEqual(abs(int(box.value) - time.time()), 2)
            # Not while it is typed in, nor with an edit in it
            await pilot.click("#epoch-input")
            view.shown = box.value = "1"
            view.follow_now()
            self.assertEqual(box.value, "1")
            view.screen.set_focus(None)
            box.value = "17902"
            view.follow_now()
            self.assertEqual(box.value, "17902")
            # An empty box follows again, but not once something was converted
            await pilot.click("#epoch-input")
            box.value = ""
            await pilot.press("enter")
            await pilot.pause()
            view.shown = box.value = "1"
            view.follow_now()
            self.assertNotEqual(box.value, "1")
            now_button = app.query_one("#btn-now")
            self.assertFalse(now_button.visible)
            await pilot.click("#epoch-input")
            box.value = "1790222400"
            await pilot.press("enter")
            view.follow_now()
            self.assertEqual(box.value, "1790222400")
            # Now shows once there is something to go back from, and goes back to following now
            self.assertTrue(now_button.visible)
            await pilot.click("#btn-now")
            await pilot.pause()
            self.assertLessEqual(abs(int(box.value) - time.time()), 2)
            self.assertFalse(now_button.visible)
            self.assertIsNone(app.focused)

        self.run_view(body)

    def test_how_far_from_now_keeps_up_with_the_time(self):
        async def body(app, pilot, view):
            details = app.query_one("#epoch-details")
            view.moment = NOW
            view.measure(NOW)
            self.assertTrue(details.render().plain.endswith("Relative  now"))
            view.measure(NOW.replace(second=2))
            self.assertTrue(details.render().plain.endswith("Relative  2 seconds ago"))
            view.measure(NOW.replace(minute=6))
            self.assertTrue(details.render().plain.endswith("Relative  2 minutes ago"))

        self.run_view(body)


if __name__ == "__main__":
    unittest.main()
