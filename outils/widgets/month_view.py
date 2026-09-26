from datetime import date

from rich.text import Text
from textual.widget import Widget

from ..months import WEEKS_SHOWN, month_weeks, weekday_labels

# Each day sits in a four-column cell, its two digits with a space either side, so today's
# highlight has room around the number and the columns read apart
CELL = 4
MONTH_WIDTH = 7 * CELL
# The name, a blank row, the day names, the dashed rule under them, then the weeks
MONTH_HEIGHT = 4 + WEEKS_SHOWN
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
    }

    DEFAULT_CSS = f"""
    MonthView {{
        width: {MONTH_WIDTH};
        height: {MONTH_HEIGHT};
    }}
    """

    def __init__(self, year: int, month: int, first_weekday: int, today: date, **kwargs) -> None:
        super().__init__(**kwargs)
        self.year = year
        self.month = month
        self.first_weekday = first_weekday
        self.today = today

    def show(self, year: int, month: int) -> None:
        self.year = year
        self.month = month
        self.refresh()

    def _style(self, name: str):
        return self.get_component_rich_style(f"month--{name}")

    def render(self) -> Text:
        """Past days and past months in grey, today as a block, what is to come in plain text."""
        this_month = (self.today.year, self.today.month)
        shown = (self.year, self.month)
        title_style = "title-current" if shown == this_month else "title-past" if shown < this_month else "title"
        title = f"{date(self.year, self.month, 1):%B} {self.year}".center(MONTH_WIDTH).rstrip()
        text = Text()
        text.append(title, style=self._style(title_style))
        text.append("\n\n")
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
                if shown_day == self.today:
                    style = self._style("today")
                elif shown_day < self.today:
                    style = self._style("past")
                else:
                    style = ""
                text.append(f" {day:2} ", style=style)
        return text
