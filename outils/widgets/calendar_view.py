from datetime import date

from ouikit.shortcuts import ACTIONS
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from ..config import Config
from ..months import shift_month
from .month_view import MonthView


class CalendarView(Vertical, can_focus=True):
    """Several months side by side, the one in focus first, under Previous, Today and Next.

    before and after say how many months flank the one in focus. It starts on today's month.
    """

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

    def compose(self) -> ComposeResult:
        # As wide as the months, so the buttons sit over their outer edges and their middle
        with Vertical(id="calendar-body"):
            with Horizontal(id="calendar-nav"):
                yield self._button("← Previous", "btn-previous")
                yield Static("", classes="spacer")
                yield self._button("Today", "btn-today")
                yield Static("", classes="spacer")
                yield self._button("Next →", "btn-next")
            with Horizontal(id="calendar-months"):
                for year, month in self.months():
                    yield MonthView(year, month, self.first_weekday, self.today)

    def _button(self, label: str, id: str) -> Button:
        button = Button(label, id=id)
        button.can_focus = False  # A click must not pull focus off the calendar and its keys
        # Textual ignores clicks during the press flash; every click must move a month
        button.active_effect_duration = 0
        return button

    def on_mount(self) -> None:
        self._update_today_button()

    def months(self) -> list[tuple[int, int]]:
        """The (year, month) shown, left to right."""
        return [shift_month(self.year, self.month, delta) for delta in range(-self.before, self.after + 1)]

    def show_month(self, year: int, month: int) -> None:
        """Put that month in focus, and its neighbours around it."""
        self.year, self.month = year, month
        for view, (shown_year, shown_month) in zip(self.query(MonthView), self.months()):
            view.show(shown_year, shown_month)
        self._update_today_button()

    def action_shift(self, delta: int) -> None:
        """Move every month by delta: -1 is the previous month, 1 the next."""
        self.show_month(*shift_month(self.year, self.month, delta))

    def _update_today_button(self) -> None:
        # Nothing to go back to while today's month is on show; hidden, not removed,
        # so it keeps its place and the other buttons do not move
        self.query_one("#btn-today", Button).visible = (self.today.year, self.today.month) not in self.months()

    @on(Button.Pressed, "#btn-previous")
    def _previous(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(-1)

    @on(Button.Pressed, "#btn-next")
    def _next(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(1)

    @on(Button.Pressed, "#btn-today")
    def _today(self, event: Button.Pressed) -> None:
        event.stop()
        self.show_month(self.today.year, self.today.month)
