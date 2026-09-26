import asyncio
import unittest
from datetime import date
from unittest.mock import patch

from outils.config import Config
from outils.widgets import CalendarView, MonthView
from tests.host import Host

TODAY = date(2026, 9, 24)


def lines(month: MonthView) -> list[str]:
    return month.render().plain.split("\n")


def spans(month: MonthView, name: str) -> list[str]:
    """The text drawn in one of the month's component styles."""
    text = month.render()
    style = month.get_component_rich_style(f"month--{name}")
    return [text.plain[span.start:span.end] for span in text.spans if span.style == style]


def title_kind(month: MonthView) -> str:
    """Which of the title styles the month's name is drawn in."""
    style = month.render().spans[0].style
    return next(name for name in ("title-current", "title-past", "title") if style == month.get_component_rich_style(f"month--{name}"))


def past_days(month: MonthView) -> list[int]:
    """The days drawn in the past style."""
    return [int(cell) for cell in spans(month, "past") if cell.strip().isdigit()]


class CalendarViewTest(unittest.TestCase):
    def run_view(self, body, config=Config(), **months):
        async def main():
            app = Host(CalendarView(config, today=TODAY, **months))
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
            self.assertEqual(app.view.footnote, "Thursday, September 24, 2026")

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
            self.assertEqual(view.footnote, "Friday, September 25, 2026")
            # Today's month in focus follows today into the next one
            view.set_today(date(2026, 10, 1))
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 10), (2026, 11)])
            self.assertEqual([spans(m, "today") for m in months], [["  1 "], []])
            self.assertEqual([title_kind(m) for m in months], ["title-current", "title"])
            # A month picked by hand stays, with today redrawn
            view.action_shift(-2)
            view.set_today(date(2026, 11, 1))
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 8), (2026, 9)])
            self.assertEqual([title_kind(m) for m in months], ["title-past", "title-past"])
            self.assertTrue(app.query_one("#btn-today").visible)
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

    def test_previous_today_and_next_buttons_move_the_months(self):
        async def body(app, pilot):
            view = app.view
            today = app.query_one("#btn-today")
            self.assertFalse(today.visible)
            # Today's month on show, even second, leaves nothing to go back to
            await pilot.click("#btn-previous")
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 8), (2026, 9)])
            self.assertFalse(today.visible)
            await pilot.click("#btn-next")
            await pilot.pause()
            # Quick clicks each count
            await pilot.click("#btn-next")
            await pilot.click("#btn-next")
            await pilot.pause()
            self.assertEqual(view.months(), [(2026, 11), (2026, 12)])
            self.assertTrue(today.visible)
            await pilot.click("#btn-previous")
            await pilot.pause()
            self.assertEqual((view.year, view.month), (2026, 10))
            await pilot.click("#btn-today")
            await pilot.pause()
            self.assertEqual((view.year, view.month), (2026, 9))
            self.assertFalse(today.visible)
            self.assertEqual([spans(m, "today") for m in app.query(MonthView)], [[" 24 "], []])

        self.run_view(body)

    def test_the_arrow_keys_move_the_months_and_the_buttons_sit_over_them(self):
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
            # Each label shows whole, not wrapped down to its arrow
            nav = "".join(segment.text for segment in app.screen._compositor.render_strips()[app.query_one("#btn-previous").region.y])
            self.assertIn("← Previous", nav)
            self.assertIn("Next →", nav)
            months = list(app.query(MonthView))
            previous, today, following = (app.query_one(f"#btn-{name}").region for name in ("previous", "today", "next"))
            self.assertEqual(previous.x, months[0].region.x)
            self.assertEqual(following.right, months[-1].region.right)
            self.assertLessEqual(abs((today.x + today.right) - (months[0].region.x + months[-1].region.right)), 1)

        self.run_view(body)


if __name__ == "__main__":
    unittest.main()
