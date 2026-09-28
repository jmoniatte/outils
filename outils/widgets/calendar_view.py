import asyncio
import random
from datetime import date

from rich.text import Text
from textual import on, work
from textual.events import Click
from textual.app import ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Center, Horizontal, Vertical
from textual.widgets import Button, Static
from tui_kit.shortcuts import ACTIONS

from ..click_only import quick_button
from ..config import Config
from ..history import Event, HistoryError, events
from ..months import shift_month
from .month_view import MonthView

# The most an event takes under the months, so the pop-up never needs more rows
HISTORY_LINES = 3


class CalendarView(Vertical, can_focus=True):
    """Several months side by side, the one in focus first, under today's date and Previous and
    Next, then something that happened on the day picked, in a past year, from Wikipedia.

    before and after say how many months flank the one in focus. It starts on today's month, and
    follows today into the next month when it was on show. A click on a day picks it; today is
    picked at first, and a click on the date goes back to it.
    """

    # Its date takes the blank row under the tabs, so it adds no row
    UNDER_TABS = True
    # Shown at the bottom right, over the footer's rule: the words, then the link
    CREDIT = ("Data by", "https://wikimedia.org")

    BINDINGS = [
        Binding("left", "shift(-1)", "Previous month", key_display="←", group=ACTIONS),
        Binding("right", "shift(1)", "Next month", key_display="→", group=ACTIONS),
    ]

    def __init__(self, config: Config, today: date | None = None, before: int = 0, after: int = 1) -> None:
        super().__init__(id="calendar")
        self.today = today or date.today()
        self.first_weekday = config.week_start
        self.before = before
        self.after = after
        self.year = self.today.year
        self.month = self.today.month
        self.picked = self.today
        self.asked = False
        # Wikipedia's events by (month, day): a day clicked again costs no request
        self.history: dict[tuple[int, int], list[Event]] = {}
        self.event: Event | None = None

    def compose(self) -> ComposeResult:
        # As wide as the months, so the buttons sit over their outer edges and their middle
        with Vertical(id="calendar-body"):
            with Center():
                yield Static(self.today_text, id="calendar-today")
            with Horizontal(id="calendar-nav"):
                yield quick_button("← Previous", "btn-previous", "tinted -green step-button")
                yield Static("", classes="spacer")
                yield quick_button("Next →", "btn-next", "tinted -green step-button")
            with Horizontal(id="calendar-months"):
                for year, month in self.months():
                    yield MonthView(year, month, self.first_weekday, self.today, self.picked)
        # Out of the months' box, so it takes the tab's whole width
        with Horizontal(id="calendar-history"):
            yield Static("", id="history-year")
            yield Static("", id="history-text")

    def on_mount(self) -> None:
        # outils stays open for days, so a new day must reach the calendar without a restart
        self.set_interval(60, self.check_today)

    def tab_shown(self) -> None:
        self.check_today()
        # Asked the first time its tab shows, so opening another tab costs no request
        if not self.asked:
            self.asked = True
            self.show_history()

    def check_today(self) -> None:
        self.set_today(date.today())

    def set_today(self, today: date) -> None:
        """Move today there, taking the month in focus along if it was today's."""
        if today == self.today:
            return
        followed = (self.year, self.month) == (self.today.year, self.today.month)
        if self.picked == self.today:
            self.picked = today
            if self.asked:
                self.show_history()
        self.today = today
        self.show_month(*((today.year, today.month) if followed else (self.year, self.month)))
        self.query_one("#calendar-today", Static).update(self.today_text)

    @property
    def today_text(self) -> str:
        """Today in full, shown over the buttons."""
        return f"{self.today:%A, %B} {self.today.day}, {self.today.year}"

    def months(self) -> list[tuple[int, int]]:
        """The (year, month) shown, left to right."""
        return [shift_month(self.year, self.month, delta) for delta in range(-self.before, self.after + 1)]

    def show_month(self, year: int, month: int) -> None:
        """Put that month in focus, and its neighbours around it."""
        self.year, self.month = year, month
        for view, (shown_year, shown_month) in zip(self.query(MonthView), self.months()):
            view.show(shown_year, shown_month, self.today, self.picked)

    def action_shift(self, delta: int) -> None:
        """Move every month by delta: -1 is the previous month, 1 the next."""
        self.show_month(*shift_month(self.year, self.month, delta))

    @on(MonthView.DayClicked)
    def _day_clicked(self, event: MonthView.DayClicked) -> None:
        event.stop()
        self.pick(event.day)

    def pick(self, day: date) -> None:
        """Highlight day and show something that happened on it."""
        self.picked = day
        self.show_month(self.year, self.month)
        self.show_history()

    @work(exclusive=True)
    async def show_history(self) -> None:
        """Something that happened on the day picked, another one each time it is picked again.

        The answer is waited for in a thread, so the calendar works meanwhile.
        """
        key = (self.picked.month, self.picked.day)
        if key not in self.history:
            self.event = None
            self._show_history("", f"Asking Wikipedia about {self.picked:%B} {self.picked.day}...", "-waiting")
            try:
                self.history[key] = await asyncio.to_thread(events, *key)
            except HistoryError as error:
                self._show_history("", str(error), "-error")
                return
        choices = [event for event in self.history[key] if event != self.event] or self.history[key]
        self.event = random.choice([event for event in choices if self._lines(event.text, self._text_width(event)) <= HISTORY_LINES] or choices)
        self._show_event()

    def on_resize(self) -> None:
        # A new width wraps the event anew; it may no longer need cutting, or need it now
        if self.event:
            self._show_event()

    def _show_event(self) -> None:
        self._show_history(str(self.event.year), self._fit(self.event.text, self._text_width(self.event)))

    def _text_width(self, event: Event) -> int:
        """The room left for the event's text beside its year."""
        # Before its first layout, or while its tab hides, the view has no width: the window's is near enough
        return (self.content_size.width or self.app.size.width) - len(str(event.year)) - 1

    def _lines(self, text: str, width: int) -> int:
        return len(Text(text).wrap(self.app.console, max(width, 1)))

    def _fit(self, text: str, width: int) -> str:
        """text, cut at a word with "…" when it would take more than HISTORY_LINES lines."""
        words = text.split()
        while len(words) > 1 and self._lines(text, width) > HISTORY_LINES:
            words.pop()
            text = " ".join(words) + "…"
        return text

    def _show_history(self, year: str, text: str, state: str = "") -> None:
        try:
            year_label = self.query_one("#history-year", Static)
        except NoMatches:
            # Wikipedia answered as the app closed, its widgets already gone
            return
        year_label.update(year)
        year_label.display = bool(year)
        label = self.query_one("#history-text", Static)
        label.update(text)
        label.set_class(state == "-waiting", "-waiting")
        label.set_class(state == "-error", "-error")

    @on(Button.Pressed, "#btn-previous")
    def _previous(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(-1)

    @on(Button.Pressed, "#btn-next")
    def _next(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(1)

    def on_click(self, event: Click) -> None:
        if event.widget is self.query_one("#calendar-today"):
            self.go_today()

    def go_today(self) -> None:
        """Today's month in focus, and today picked."""
        self.show_month(self.today.year, self.today.month)
        # Back on today, its event too; one already on show stays
        if self.picked != self.today:
            self.pick(self.today)
