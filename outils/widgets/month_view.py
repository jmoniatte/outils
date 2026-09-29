from collections.abc import Callable
from datetime import date

from rich.style import Style
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from ..months import WEEKS_SHOWN, month_weeks, weekday_labels

# Each day sits in a four-column cell, its two digits with a space either side, so today's
# highlight has room around the number and the columns read apart
CELL = 4
MONTH_WIDTH = 7 * CELL
# The name, the day names, the dashed rule under them, then the weeks
MONTH_HEIGHT = 3 + WEEKS_SHOWN
# Nerd Font's cake, a birthday's, as the calendar's events line has it
CAKE = "\U000f00eb"
# Saturday and Sunday, as calendar counts days
WEEKEND = (5, 6)


class MonthView(Widget):
    """One month laid out like cal, with room to read it: its name, the day names over a rule,
    then a row per week.

    The colors come from TCSS through the component classes, so a theme change repaints it.
    """

    COMPONENT_CLASSES = {
        "month--title",
        "month--title-current",
        "month--title-past",
        "month--weekdays",
        "month--weekend",
        "month--rule",
        "month--past",
        "month--today",
        "month--picked",
        "month--marked",
        "month--birthday",
    }

    class DayClicked(Message):
        def __init__(self, day: date) -> None:
            super().__init__()
            self.day = day

    DEFAULT_CSS = f"""
    MonthView {{
        width: {MONTH_WIDTH};
        height: {MONTH_HEIGHT};
    }}
    """

    def __init__(
        self,
        year: int,
        month: int,
        first_weekday: int,
        today: date,
        picked: date | None = None,
        marked: Callable[[date], str | None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        # Which color a day has from today on: "birthday" for a birthday from the config,
        # "marked" (yellow) for another event (a full moon, DST, a holiday), None for none
        self.marked = marked or (lambda day: None)
        self.year = year
        self.month = month
        self.first_weekday = first_weekday
        self.today = today
        self.picked = picked

    def show(self, year: int, month: int, today: date, picked: date | None = None) -> None:
        self.year = year
        self.month = month
        self.today = today
        self.picked = picked
        self.refresh()

    def day_at(self, x: int, y: int) -> date | None:
        """The day drawn at x, y inside the month, None over its name, the day names or an empty cell."""
        week, column = y - (MONTH_HEIGHT - WEEKS_SHOWN), x // CELL
        if not (0 <= week < WEEKS_SHOWN and 0 <= column < 7):
            return None
        day = month_weeks(self.year, self.month, self.first_weekday)[week][column]
        return date(self.year, self.month, day) if day else None

    def on_click(self, event: events.Click) -> None:
        offset = event.get_content_offset(self)
        day = offset and self.day_at(offset.x, offset.y)
        if day:
            self.post_message(self.DayClicked(day))

    def _style(self, name: str):
        return self.get_component_rich_style(f"month--{name}")

    def render(self) -> Text:
        """Past days and past months in grey, today as a block, what is to come in plain text, a
        day with an event yellow, a birthday's cake in place of its number."""
        this_month = (self.today.year, self.today.month)
        shown = (self.year, self.month)
        title_style = "title-current" if shown == this_month else "title-past" if shown < this_month else "title"
        title = f"{date(self.year, self.month, 1):%B} {self.year}".center(MONTH_WIDTH).rstrip()
        text = Text()
        text.append(title, style=self._style(title_style))
        text.append("\n")
        # The weekend shows in the day names only, so grey in the numbers always means past
        for column, label in enumerate(weekday_labels(self.first_weekday)):
            is_weekend = (self.first_weekday + column) % 7 in WEEKEND
            text.append(f" {label} ", style=self._style("weekend" if is_weekend else "weekdays"))
        # Dashed like tui-kit's titles, and only as wide as the day names, not the padding either side
        text.append("\n " + "-" * (MONTH_WIDTH - 2), style=self._style("rule"))
        for week in month_weeks(self.year, self.month, self.first_weekday):
            text.append("\n")
            for day in week:
                if not day:
                    text.append(" " * CELL)
                    continue
                shown_day = date(self.year, self.month, day)
                kind = self.marked(shown_day)
                # A birthday shows its cake in place of its number, past or not
                label = f"{CAKE:>2}" if kind == "birthday" else f"{day:2}"
                if shown_day == self.today:
                    style = self._style("today")
                elif shown_day < self.today:
                    # Grey always means past, marked or not
                    style = self._style("picked" if shown_day == self.picked else "past")
                else:
                    style = self._style("picked") if shown_day == self.picked else Style()
                    if kind:
                        # Its color only: the component style carries the widget's background too, which would hide the picked cell's
                        style += Style(color=self._style(kind).color)
                text.append(f" {label} ", style=style)
        return text
