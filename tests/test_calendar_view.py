import asyncio
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from outils.config import Birthday, Config
from outils.weather import Place, WeatherError
from outils.widgets import CalendarView, MonthView
from tests.host import Host, settle

TODAY = date(2026, 9, 24)
PORTLAND = Place("Portland", "Oregon", "United States", 45.52, -122.68, "America/Los_Angeles", "US")


def lines(month: MonthView) -> list[str]:
    return month.render().plain.split("\n")


def spans(month: MonthView, name: str) -> list[str]:
    """The text drawn in one of the month's component styles."""
    text = month.render()
    style = month.get_component_rich_style(f"month--{name}")
    return [text.plain[span.start:span.end] for span in text.spans if span.style == style]


def yellow(month: MonthView) -> list[str]:
    """The days drawn in the marked color."""
    text = month.render()
    color = month.get_component_rich_style("month--marked").color
    return [text.plain[span.start:span.end] for span in text.spans if span.style.color == color]


def title_kind(month: MonthView) -> str:
    """Which of the title styles the month's name is drawn in."""
    style = month.render().spans[0].style
    return next(name for name in ("title-current", "title-past", "title") if style == month.get_component_rich_style(f"month--{name}"))


def past_days(month: MonthView) -> list[int]:
    """The days drawn in the past style."""
    return [int(cell) for cell in spans(month, "past") if cell.strip().isdigit()]


class CalendarViewTest(unittest.TestCase):
    def run_view(self, body, config=Config(), place=PORTLAND, **months):
        async def main():
            app = Host(CalendarView(config, today=TODAY, **months))
            # Its tab showing reads the date
            with (
                patch("outils.widgets.calendar_view.date") as clock,
                patch("outils.widgets.calendar_view.find_place", side_effect=place if isinstance(place, Exception) else None, return_value=place) as self.find_place,
            ):
                clock.today.return_value = TODAY
                async with app.run_test(size=(90, 16)) as pilot:
                    await pilot.pause()
                    await body(app, pilot)

        asyncio.run(main())

    def test_this_month_and_the_next_laid_out_like_cal(self):
        async def body(app, pilot):
            months = list(app.query(MonthView))
            self.assertEqual([(m.year, m.month) for m in months], [(2026, 9), (2026, 10)])
            self.assertEqual(
                lines(months[0]),
                [
                    "       September 2026",
                    "",
                    " Mo  Tu  We  Th  Fr  Sa  Su ",
                    " --------------------------",
                    "      1   2   3   4   5   6 ",
                    "  7   8   9  10  11  12  13 ",
                    " 14  15  16  17  18  19  20 ",
                    " 21  22  23  24  25  26  27 ",
                    " 28  29  30                 ",
                    "                            ",
                ],
            )
            # Today is a whole cell, the space either side of the number included
            self.assertEqual([spans(m, "today") for m in months], [[" 24 "], []])
            # Today's month has its name stand out, a month wholly past is grey
            self.assertEqual([title_kind(m) for m in months], ["title-current", "title"])
            # Days before today are grey, today and what follows are not; weekend or not makes no difference
            self.assertEqual([len(past_days(m)) for m in months], [23, 0])
            self.assertEqual(past_days(months[0])[-1], 23)
            # The weekend shows in the day names instead
            self.assertEqual([label.strip() for label in spans(months[0], "weekend") if not label.strip().isdigit()], ["Sa", "Su"])
            # Side by side, four columns apart: a two-column margin plus each cell's own space
            self.assertEqual(months[1].region.x - months[0].region.right, 2)
            self.assertEqual(months[0].region.y, months[1].region.y)
            self.assertLessEqual(months[1].region.right - months[0].region.x, 58)
            self.assertEqual(str(app.query_one("#calendar-date").render()), "Thursday, September 24, 2026")

        self.run_view(body)

    def test_shift_moves_every_month_and_today_only_shows_in_its_own(self):
        async def body(app, pilot):
            view = app.view
            view.action_shift(1)
            await pilot.pause()
            months = list(app.query(MonthView))
            self.assertEqual([(m.year, m.month) for m in months], [(2026, 10), (2026, 11)])
            self.assertEqual([spans(m, "today") for m in months], [[], []])
            # The name that stands out follows today's month, not the one in focus
            self.assertEqual([title_kind(m) for m in months], ["title", "title"])
            view.action_shift(-10)
            await pilot.pause()
            self.assertEqual(view.months(), [(2025, 12), (2026, 1)])
            self.assertEqual(lines(months[1])[0], "        January 2026")

        self.run_view(body)

    def test_a_new_day_moves_today_and_follows_it_to_a_new_month_unless_another_was_picked(self):
        async def body(app, pilot):
            view = app.view
            view.set_today(date(2026, 9, 25))
            await pilot.pause()
            months = list(app.query(MonthView))
            self.assertEqual([spans(m, "today") for m in months], [[" 25 "], []])
            # The date follows today while today is picked
            self.assertEqual(str(app.query_one("#calendar-date").render()), "Friday, September 25, 2026")
            # Today's month in focus follows today into the next one
            view.set_today(date(2026, 10, 1))
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 10), (2026, 11)])
            self.assertEqual([spans(m, "today") for m in months], [["  1 "], []])
            self.assertEqual([title_kind(m) for m in months], ["title-current", "title"])
            # A month picked by hand stays, with today redrawn; the day picked came along to September 1,
            # so it stays too
            view.action_shift(-2)
            view.set_today(date(2026, 11, 1))
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 8), (2026, 9)])
            self.assertEqual([title_kind(m) for m in months], ["title-past", "title-past"])
            self.assertEqual(str(app.query_one("#calendar-date").render()), "Tuesday, September 1, 2026")
            # Showing the tab reads the date again
            with patch("outils.widgets.calendar_view.date") as clock:
                clock.today.return_value = date(2026, 11, 2)
                view.tab_shown()
            self.assertEqual(view.today, date(2026, 11, 2))

        self.run_view(body)

    def test_the_week_start_and_the_number_of_months_come_from_the_caller(self):
        async def body(app, pilot):
            months = list(app.query(MonthView))
            self.assertEqual(len(months), 5)
            self.assertEqual((months[2].year, months[2].month), (2026, 9))
            self.assertEqual(lines(months[2])[2], " Su  Mo  Tu  We  Th  Fr  Sa ")

        self.run_view(body, Config(week_start=6), before=2, after=2)

    def test_previous_and_next_move_the_months_and_the_day_picked_follows_when_it_leaves_them(self):
        async def body(app, pilot):
            view = app.view
            await pilot.click("#btn-previous")
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 8), (2026, 9)])
            await pilot.click("#btn-next")
            await pilot.pause()
            # Quick clicks each count
            await pilot.click("#btn-next")
            await pilot.click("#btn-next")
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 11), (2026, 12)])
            await pilot.click("#btn-previous")
            await pilot.pause()
            self.assertEqual((view.year, view.month), (2026, 10))
            # September 24 left with September, to the same day of November; it stays while shown
            self.assertEqual(view.picked, date(2026, 11, 24))
            self.assertEqual(str(app.query_one("#calendar-date").render()), "Tuesday, November 24, 2026")
            self.assertIs(app.focused, view)
            # Back past it, it comes along the other way; a 31st becomes the month's last day
            view.pick(date(2026, 10, 31))
            await pilot.press("left", "left")
            await pilot.pause()
            self.assertEqual((view.months(), view.picked), ([(2026, 8), (2026, 9)], date(2026, 9, 30)))

        self.run_view(body)

    def test_the_arrow_keys_move_the_months_and_the_buttons_sit_beside_their_names(self):
        async def body(app, pilot):
            view = app.view
            self.assertIs(app.focused, view)
            await pilot.press("left", "left", "left", "left", "left", "left", "left", "left", "left")
            self.assertEqual((view.year, view.month), (2025, 12))
            await pilot.press("right")
            self.assertEqual((view.year, view.month), (2026, 1))
            # A click leaves the keys working
            await pilot.click("#btn-next")
            self.assertIs(app.focused, view)
            # On the names' row, two columns from the months
            months = list(app.query(MonthView))
            previous, following = (app.query_one(f"#btn-{name}").region for name in ("previous", "next"))
            self.assertEqual((previous.y, following.y), (months[0].region.y, months[0].region.y))
            self.assertEqual((months[0].region.x - previous.right, following.x - months[-1].region.right), (2, 2))
            # Each arrow in the middle of its button, and nothing after it pushed aside
            row = "".join(segment.text for segment in app.screen._compositor.render_strips()[previous.y])
            self.assertEqual((row.index("←"), row.index("→")), (previous.x + 1, following.x + 1))
            title = lines(months[0])[0]
            self.assertEqual(row.index(title.strip()), months[0].region.x + len(title) - len(title.strip()))

        self.run_view(body)

    def test_a_day_clicked_is_picked(self):
        async def body(app, pilot):
            view = app.view
            await settle(app, pilot)
            self.assertEqual(view.picked, TODAY)
            months = list(app.query(MonthView))
            self.assertEqual(months[0].day_at(0, 4), None)
            self.assertEqual(months[0].day_at(5, 4), date(2026, 9, 1))
            self.assertEqual(months[1].day_at(9, 9), None)
            self.assertEqual(months[1].day_at(4, 4), None)
            # Row 8 is the week of October 26, its second column the 27th
            await pilot.click(months[1], offset=(5, 8))
            await settle(app, pilot)
            self.assertEqual(view.picked, date(2026, 10, 27))
            self.assertEqual([spans(m, "picked") for m in months], [[], [" 27 "]])
            # The day names are no day
            await pilot.click(months[1], offset=(5, 2))
            await settle(app, pilot)
            self.assertEqual(view.picked, date(2026, 10, 27))
            # Today, clicked, is picked again
            await pilot.click(months[0], offset=(13, 7))
            await settle(app, pilot)
            self.assertEqual(view.picked, TODAY)
            self.assertEqual([spans(m, "picked") for m in months], [[], []])

        self.run_view(body)

    def test_the_day_picked_shows_in_full_over_its_sun_and_its_events(self):
        async def body(app, pilot):
            await settle(app, pilot)
            date_line, sun_line = app.query_one("#calendar-date"), app.query_one("#calendar-sun")
            self.assertEqual(self.find_place.call_args.args, ("Portland, OR",))
            self.assertEqual(str(date_line.render()), "Thursday, September 24, 2026")
            self.assertEqual(sun_line.render().plain, "\U000f059c 7:00am   \U000f059b 7:05pm")
            events = app.query_one("#calendar-events")
            self.assertEqual(events.render().plain, "")
            # A line each, the date, the sun and the events, over the buttons
            self.assertEqual(sun_line.region.y, date_line.region.y + 1)
            self.assertEqual(app.query_one("#calendar-events").region.y, sun_line.region.y + 1)
            # Then the months, the arrows on their names' row
            self.assertEqual(app.query_one("#btn-previous").region.y, sun_line.region.y + 2)
            # Full on October 26 at 4:12 UTC: the 25th in Portland
            await pilot.click(list(app.query(MonthView))[1], offset=(25, 7))
            await settle(app, pilot)
            self.assertEqual(str(date_line.render()), "Sunday, October 25, 2026")
            self.assertEqual(events.render().plain, "\U000f0f62 Full moon")
            self.assertEqual(sun_line.render().plain, "\U000f059c 7:40am   \U000f059b 6:09pm")

            # Clocks go back on November 1 in Portland; everything on a day, comma separated
            app.view.pick(date(2026, 11, 1))
            await settle(app, pilot)
            self.assertEqual(events.render().plain, "\U000f0150 DST ends")
            events.show(["Mom"], True, timedelta(hours=1), ["Easter Sunday"])
            self.assertEqual(events.render().plain, "\U000f00eb Mom • \U000f0f62 Full moon • \U000f0150 DST starts • \U000f09d3 Easter Sunday")

            # The days with an event are yellow: the full moons on September 26 and October 25 (Oregon
            # has no Columbus Day on the 12th), not a past one
            months = list(app.query(MonthView))
            self.assertEqual([yellow(m) for m in months], [[" 26 "], [" 25 "]])
            app.view.set_today(date(2026, 9, 27))
            await settle(app, pilot)
            self.assertEqual([yellow(m) for m in months], [[], [" 25 "]])
            # Picked, it keeps the picked cell's background, in yellow
            await pilot.click(months[1], offset=(25, 7))
            await settle(app, pilot)
            text = months[1].render()
            style = next(span.style for span in text.spans if text.plain[span.start:span.end] == " 25 ")
            picked, marked = (months[1].get_component_rich_style(f"month--{name}") for name in ("picked", "marked"))
            self.assertEqual((style.bgcolor, style.color), (picked.bgcolor, marked.color))

        self.run_view(body)

    def test_the_city_typed_gives_the_sun_dst_and_holidays(self):
        strasbourg = Place("Strasbourg", "Grand Est", "France", 48.58, 7.75, "Europe/Paris", "FR")

        async def body(app, pilot):
            await settle(app, pilot)
            events, box = app.query_one("#calendar-events"), app.query_one("#calendar-city")
            self.assertEqual((box.value, box.has_class("-found")), ("Portland, Oregon, United States", True))
            # No label, but the box where "City" and its gap would put it
            label = app.query_one("#calendar .lookup-label")
            self.assertEqual((str(label.render()), box.region.x - label.region.x), ("", 6))
            app.view.pick(date(2026, 11, 11))
            await settle(app, pilot)
            self.assertEqual(events.render().plain, "\U000f09d3 Veterans Day")
            # Another city, typed: its country's holidays, its sun
            self.find_place.return_value = strasbourg
            await pilot.click(box)
            await pilot.press(*"Strasbourg", "enter")
            await settle(app, pilot)
            self.assertEqual(self.find_place.call_args.args, ("Strasbourg",))
            self.assertEqual(box.value, "Strasbourg, Grand Est, France")
            self.assertEqual(events.render().plain, "\U000f09d3 Armistice")
            self.assertEqual(app.query_one("#calendar-sun").render().plain, "\U000f059c 7:30am   \U000f059b 4:56pm")
            # DST ends there a week before Portland
            app.view.pick(date(2026, 10, 25))
            await settle(app, pilot)
            self.assertEqual(events.render().plain, "\U000f0150 DST ends")
            app.view.pick(date(2026, 11, 26))
            await settle(app, pilot)
            self.assertEqual(events.render().plain, "")

        self.run_view(body)

    def test_birthdays_show_a_cake_and_come_first_in_the_events(self):
        # October 25 is a full moon in 2026
        birthdays = [Birthday("Mom", 10, 25, 1966), Birthday("Léa", 10, 12)]

        async def body(app, pilot):
            await settle(app, pilot)
            months = list(app.query(MonthView))
            # Their cake in place of their number, yellow like other events
            text = months[1].render()
            self.assertEqual(yellow(months[1]), ["  \U000f00eb "] * 2)
            self.assertNotIn(" 12 ", text.plain)
            app.view.pick(date(2026, 10, 25))
            await settle(app, pilot)
            self.assertEqual(app.query_one("#calendar-events").render().plain, "\U000f00eb Mom (60) • \U000f0f62 Full moon")

        self.run_view(body, Config(birthdays=birthdays))

    def test_without_the_place_there_is_no_sun(self):
        async def body(app, pilot):
            await settle(app, pilot)
            self.assertEqual(app.query_one("#calendar-sun").render().plain, "")

        self.run_view(body, place=WeatherError("offline"))


if __name__ == "__main__":
    unittest.main()
