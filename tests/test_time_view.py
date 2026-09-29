import asyncio
import time
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from tui_kit.theme import load_palette

from outils.config import Config
from outils.weather import Place, WeatherError
from outils.widgets import TimeView
from outils.widgets.clocks_view import NAME_WIDTH

from tests.host import Host, settle

NOW = datetime(2026, 9, 25, 5, 4, tzinfo=UTC)


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
            # It opens on now, the date here, in the box and under it
            self.assertLessEqual(abs(datetime.fromisoformat(box.value).timestamp() - time.time()), 2)
            self.assertTrue(box.has_class("-found"))
            self.assertEqual(details.render().plain.split("\n")[3], f"{view.local_label:<{NAME_WIDTH}}{box.value}")
            self.assertEqual(box.value, datetime.fromisoformat(box.value).astimezone().isoformat())
            self.assertTrue(details.render().plain.startswith(f"{'Relative':<{NAME_WIDTH}}now\n"))
            # The box starts where the values do, under the clocks' times
            self.assertEqual(box.region.x, details.region.x + NAME_WIDTH)
            # Clicked first: while the box has focus, now no longer fills it
            await pilot.click("#epoch-input")
            box.value = ""
            await pilot.press(*"1790222400", "enter")
            await pilot.pause()
            lines = details.render().plain.split("\n")
            self.assertEqual(lines[1:3], [f"{'Seconds':<{NAME_WIDTH}}1790222400", f"{'UTC':<{NAME_WIDTH}}2026-09-24T04:00:00+00:00"])
            # The box lets go, so ?, t and q work again, and turns blue; the values stay plain
            self.assertIsNone(app.focused)
            self.assertTrue(app.query_one("#epoch-input").has_class("-found"))
            text = details.render()
            self.assertEqual([text.plain[span.start:span.end].strip() for span in text.spans], ["Relative", "Seconds", "UTC", view.local_label])
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
            self.assertLessEqual(abs(datetime.fromisoformat(box.value).timestamp() - time.time()), 2)
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
            self.assertLessEqual(abs(datetime.fromisoformat(box.value).timestamp() - time.time()), 2)
            self.assertFalse(now_button.visible)
            self.assertIsNone(app.focused)

        self.run_view(body)

    def test_a_city_typed_in_the_last_row_shows_its_time_there(self):
        tokyo = Place("Tokyo", "Tokyo", "Japan", 35.7, 139.7, "Asia/Tokyo", "JP")

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
            self.assertEqual(row.region.x, box.region.x + NAME_WIDTH)
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
            self.assertEqual(row.render().style.color.triplet.hex.lower(), load_palette("onedark")["red"].lower())
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

    def test_a_city_or_time_zone_typed_in_the_last_label_shows_the_date_there(self):
        quebec = Place("Québec", "Quebec", "Canada", 46.8, -71.2, "America/Toronto", "CA")

        async def body(app, pilot, view):
            value = app.query_one("#zone-value")
            box = app.query_one("#zone-input")
            # The box in the label column, the value in the values' column
            details = app.query_one("#epoch-details")
            self.assertEqual((box.region.x, value.region.x), (details.region.x, details.region.x + NAME_WIDTH))

            async def enter(widget, text):
                await pilot.click(widget)
                app.query_one(widget).value = ""
                await pilot.press(*text, "enter")
                await settle(app, pilot)

            await enter("#epoch-input", "2026-10-02T16:00+02:00")
            with patch("outils.widgets.time_view.find_place", return_value=quebec):
                await enter("#zone-input", "Quebec")
            # The box shows the zone it resolves to
            self.assertEqual((box.value, str(value.render())), ("America/Toronto", "2026-10-02T10:00:00-04:00"))
            # A new date shows there too; a time zone needs no lookup
            await enter("#epoch-input", "2026-10-02T12:00:00Z")
            self.assertEqual(str(value.render()), "2026-10-02T08:00:00-04:00")
            with patch("outils.widgets.time_view.find_place") as find:
                await enter("#zone-input", "asia/tokyo")
            find.assert_not_called()
            self.assertEqual((box.value, str(value.render())), ("Asia/Tokyo", "2026-10-02T21:00:00+09:00"))
            # A failure shows in red in the value's place
            with patch("outils.widgets.time_view.find_place", side_effect=WeatherError("Open-Meteo does not know 'Nowhere'")):
                await enter("#zone-input", "Nowhere")
            self.assertEqual((str(value.render()), value.has_class("-error")), ("Open-Meteo does not know 'Nowhere'", True))
            # An empty box empties the value
            await enter("#zone-input", "")
            self.assertEqual((str(value.render()), value.has_class("-error")), ("", False))

        self.run_view(body)

    def test_how_far_from_now_keeps_up_with_the_time(self):
        async def body(app, pilot, view):
            details = app.query_one("#epoch-details")
            view.moment = NOW
            view.measure(NOW)
            self.assertEqual(details.render().plain.split("\n")[0], f"{'Relative':<{NAME_WIDTH}}now")
            view.measure(NOW.replace(second=2))
            self.assertEqual(details.render().plain.split("\n")[0], f"{'Relative':<{NAME_WIDTH}}2 seconds ago")
            view.measure(NOW.replace(minute=6))
            self.assertEqual(details.render().plain.split("\n")[0], f"{'Relative':<{NAME_WIDTH}}2 minutes ago")

        self.run_view(body)


if __name__ == "__main__":
    unittest.main()
