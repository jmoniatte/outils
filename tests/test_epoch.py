import asyncio
import time
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from tui_kit.theme import load_palette

from outils.config import Config
from outils.epoch import EpochError, parse, relative, rows
from outils.weather import Place, WeatherError
from outils.widgets import TimeView

from tests.host import Host, settle

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

    def test_an_extra_zone_is_a_row_after_local_labelled_by_its_name(self):
        moment = parse("2026-10-02T16:00+02:00", NOW, PORTLAND)
        found = rows(moment, NOW, PORTLAND, extra=("Québec", ZoneInfo("America/Toronto")))
        self.assertEqual([label for label, _ in found], ["Seconds", "UTC", "Local", "Québec", "Relative"])
        self.assertEqual(found[3][1], "2026-10-02T10:00:00-04:00")

    def test_relative_takes_the_largest_unit(self):
        self.assertEqual(relative(datetime(2026, 9, 25, 7, 5, tzinfo=UTC), NOW), "in 2 hours")
        self.assertEqual(relative(datetime(2026, 9, 25, 5, 3, tzinfo=UTC), NOW), "1 minute ago")
        self.assertEqual(relative(datetime(2020, 1, 1, tzinfo=UTC), NOW), "6 years ago")


class TimeViewTest(unittest.TestCase):
    def run_view(self, body, config=None):
        async def main():
            app = Host(TimeView(config or Config()))
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
            self.assertEqual(details.render().plain.split("\n")[0], f"{'Seconds':<20}{box.value}")
            self.assertTrue(details.render().plain.endswith(f"{'Relative':<20}now"))
            # The box starts where the values do, under the clocks' times
            self.assertEqual(box.region.x, details.region.x + 20)
            # Clicked first: while the box has focus, now no longer fills it
            await pilot.click("#epoch-input")
            box.value = ""
            await pilot.press(*"1790222400", "enter")
            await pilot.pause()
            lines = details.render().plain.split("\n")
            self.assertEqual(lines[:2], [f"{'Seconds':<20}1790222400", f"{'UTC':<20}2026-09-24T04:00:00+00:00"])
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

    def test_a_city_typed_in_the_last_row_shows_its_time_there(self):
        tokyo = Place("Tokyo", "Tokyo", "Japan", 35.7, 139.7, "Asia/Tokyo")

        async def body(app, pilot, view):
            row = app.query_one("#city-clock")
            box = app.query_one("#city-input")
            # The box sits in the name column, under the names, and its row's time under theirs
            self.assertEqual(box.region.x, app.query_one("#clocks").region.x)
            self.assertFalse(row.display)
            with patch("outils.widgets.time_view.find_place", return_value=tokyo) as find:
                # The weather's cities complete, and Enter takes the completion
                await pilot.click("#city-input")
                await pilot.press(*"tok", "enter")
                await settle(app, pilot)
            find.assert_called_once_with("Tokyo, Japan")
            self.assertEqual(row.region.x, box.region.x + 20)
            self.assertTrue(row.render().plain.endswith("   +09:00     Asia/Tokyo"))
            # The short name, in blue as what a box found; the box lets go
            self.assertEqual((box.value, box.has_class("-found"), app.focused), ("Tokyo", True, None))
            # A failure shows in red in its place
            with patch("outils.widgets.time_view.find_place", side_effect=WeatherError("Open-Meteo does not know 'Nowhere'")):
                await pilot.click("#city-input")
                box.value = ""
                await pilot.press(*"Nowhere", "enter")
                await settle(app, pilot)
            self.assertEqual(row.render().plain, "Open-Meteo does not know 'Nowhere'")
            self.assertEqual(row.render().spans[-1].style.color.triplet.hex.lower(), load_palette("onedark")["red"].lower())
            # A time zone needs no lookup, and is named after its city
            with patch("outils.widgets.time_view.find_place") as find:
                await pilot.click("#city-input")
                box.value = ""
                # Time zones are suggested after the weather's cities; Enter takes one once a "/" is typed
                self.assertEqual(await box.suggester.get_suggestion("asia/tok"), "Asia/Tokyo")
                self.assertEqual(await box.suggester.get_suggestion("tok"), "Tokyo, Japan")
                self.assertEqual((view._completed("Eu"), view._completed("tokyo")), ("Eu", "Tokyo, Japan"))
                await pilot.press(*"europe/berl", "enter")
                await settle(app, pilot)
            find.assert_not_called()
            self.assertTrue(row.render().plain.endswith("Europe/Berlin"))
            self.assertEqual(box.value, "Berlin")
            # An empty box takes it away
            await pilot.click("#city-input")
            box.value = ""
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(row.display)

        self.run_view(body, Config(locations=["Portland, OR", "Tokyo, Japan"]))

    def test_the_in_box_shows_the_date_in_a_city_or_time_zone_too(self):
        quebec = Place("Québec", "Quebec", "Canada", 46.8, -71.2, "America/Toronto")

        async def body(app, pilot, view):
            details = app.query_one("#epoch-details")

            async def enter(box, text):
                await pilot.click(box)
                app.query_one(box).value = ""
                await pilot.press(*text, "enter")
                await settle(app, pilot)

            await enter("#epoch-input", "2026-10-02T16:00+02:00")
            with patch("outils.widgets.time_view.find_place", return_value=quebec):
                await enter("#zone-input", "Quebec")
            lines = details.render().plain.split("\n")
            self.assertEqual(lines[1:4], [f"{'UTC':<20}2026-10-02T14:00:00+00:00", lines[2], f"{'Québec':<20}2026-10-02T10:00:00-04:00"])
            self.assertTrue(lines[4].startswith("Relative"))
            self.assertEqual(app.query_one("#zone-input").value, "Québec, Quebec, Canada")
            # A time zone needs no lookup
            with patch("outils.widgets.time_view.find_place") as find:
                await enter("#zone-input", "asia/tokyo")
            find.assert_not_called()
            self.assertEqual(details.render().plain.split("\n")[3], f"{'Tokyo':<20}2026-10-02T23:00:00+09:00")
            # A failure shows in red in the row's place, the rest stays
            with patch("outils.widgets.time_view.find_place", side_effect=WeatherError("Open-Meteo does not know 'Nowhere'")):
                await enter("#zone-input", "Nowhere")
            text = details.render()
            self.assertEqual(text.plain.split("\n")[3], f"{'In':<20}Open-Meteo does not know 'Nowhere'")
            self.assertEqual(text.spans[-2].style.color.triplet.hex.lower(), load_palette("onedark")["red"].lower())
            # An empty box takes the row away
            await enter("#zone-input", "")
            self.assertEqual(len(details.render().plain.split("\n")), 4)

        self.run_view(body)

    def test_how_far_from_now_keeps_up_with_the_time(self):
        async def body(app, pilot, view):
            details = app.query_one("#epoch-details")
            view.moment = NOW
            view.measure(NOW)
            self.assertTrue(details.render().plain.endswith(f"{'Relative':<20}now"))
            view.measure(NOW.replace(second=2))
            self.assertTrue(details.render().plain.endswith(f"{'Relative':<20}2 seconds ago"))
            view.measure(NOW.replace(minute=6))
            self.assertTrue(details.render().plain.endswith(f"{'Relative':<20}2 minutes ago"))

        self.run_view(body)


if __name__ == "__main__":
    unittest.main()
