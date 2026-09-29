import asyncio
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.widget import Widget
from textual.suggester import SuggestFromList
from textual.widgets import Button, Input, Static
from tui_kit.shortcuts import ACTIONS

from .. import public_holidays
from ..click_only import quick_button
from ..clocks import clock_change
from ..config import Config
from ..months import shift_month
from ..sky import FULL_MOON, Sun, full_moon, sun
from ..weather import Place, WeatherError, find_place
from .lookup_box import GAP, LookupBox, completed, lookup_row
from .month_view import CAKE, MonthView

# Nerd Font's sunrise and sunset, as the Weather tab's icons are, and a clock
SUNRISE, SUNSET, CLOCK, HOLIDAY = "\U000f059c", "\U000f059b", "\U000f0150", "\U000f09d3"


class DayEvents(Widget):
    """On its own line over the months, everything found for the day picked, three spaces apart, the
    config's birthdays first: "󰃫 Mom (60)   󰖔 Full moon   󰅐 DST ends   󰧓 Veterans Day"; empty on most days."""

    COMPONENT_CLASSES = {"day--icon", "day--birthday"}

    DEFAULT_CSS = """
    DayEvents {
        width: auto;
        height: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.birthdays: list[str] = []
        self.full = False
        self.change = timedelta()
        self.holidays: list[str] = []

    def show(self, birthdays: list[str], full: bool, change: timedelta, holidays: list[str]) -> None:
        self.birthdays, self.full, self.change, self.holidays = birthdays, full, change, holidays
        # Its width follows the text's, to stay centered
        self.refresh(layout=True)

    def render(self) -> Text:
        icon = self.get_component_rich_style("day--icon")
        # Birthdays first
        events = [Text(CAKE, style=self.get_component_rich_style("day--birthday")) + Text(f" {name}") for name in self.birthdays]
        if self.full:
            events.append(Text(FULL_MOON, style=icon) + Text(" Full moon"))
        if self.change:
            events.append(Text(CLOCK, style=icon) + Text(f" DST {'starts' if self.change > timedelta() else 'ends'}"))
        for holiday in self.holidays:
            events.append(Text(HOLIDAY, style=icon) + Text(f" {holiday}"))
        return Text("   ").join(events)


class DaySun(Widget):
    """When the sun rises and sets on the day picked, on its own line under it:
    "󰖜 7:05am   󰖛 6:57pm"; nothing until the place is found, or on a day it never rises."""

    COMPONENT_CLASSES = {"day--icon"}

    DEFAULT_CSS = """
    DaySun {
        width: auto;
        height: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sun: Sun | None = None

    def show(self, sun: Sun | None) -> None:
        self.sun = sun
        self.refresh(layout=True)

    def render(self) -> Text:
        line = Text()
        if self.sun and self.sun.rise:
            icon = self.get_component_rich_style("day--icon")
            line.append(SUNRISE, style=icon)
            line.append(f" {_clock(self.sun.rise)}   ")
            line.append(SUNSET, style=icon)
            line.append(f" {_clock(self.sun.set)}")
        return line


def _clock(time: datetime) -> str:
    """"7:05am", to the nearest minute."""
    hour, minute = divmod(time.hour * 60 + time.minute + round(time.second / 60), 60)
    return f"{hour % 12 or 12}:{minute:02}{'am' if hour % 24 < 12 else 'pm'}"


class CalendarView(Vertical, can_focus=True):
    """Several months side by side, the one in focus first, over a City box, under the day picked in
    full, its sunrise and sunset, and what is found for it (a full moon, a clock change, holidays),
    with an arrow each side of the months' names to step back or forward. The sun, the clock changes and the holidays are the city's.

    before and after say how many months flank the one in focus. It starts on today's month, and
    follows today into the next month when it was on show. A click on a day picks it; today is
    picked at first.
    """

    # Shown at the bottom right, over the footer's rule: the words, then the link; the city is
    # Open-Meteo's
    CREDIT = ("Data by", "https://open-meteo.com")

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
        self.locations = config.locations
        self.birthdays = config.birthdays
        # The city in the box, found the first time the tab shows: the first of the config's
        # locations until another is typed
        self.place: Place | None = None

    def compose(self) -> ComposeResult:
        # As wide as the months and their arrows, so the date, the sun and the events center over them
        with Vertical(id="calendar-body"):
            with Center():
                yield Static(self.date_text, id="calendar-date")
            with Center():
                yield DaySun(id="calendar-sun")
            with Center():
                yield DayEvents(id="calendar-events")
            # The arrows on the months' name row, one each side
            with Horizontal(id="calendar-months"):
                yield quick_button("←", "btn-previous", "tinted -green step-button")
                for year, month in self.months():
                    yield MonthView(year, month, self.first_weekday, self.today, self.picked, self.notable)
                yield quick_button("→", "btn-next", "tinted -green step-button")
        # Under the months: the calendar comes first, the city is seldom changed
        box = LookupBox(
            self.locations[0],
            placeholder="City, or City, Region or Country",
            suggester=SuggestFromList(self.locations, case_sensitive=False),
            id="calendar-city",
        )
        # No label, the placeholder and the place say what it is; the box stays where the label would push it
        yield lookup_row("", box, label_width=len("City") + GAP)
        yield quick_button("Today", "btn-today", "tinted -green")

    def on_mount(self) -> None:
        self._show_today_button()
        # outils stays open for days, so a new day must reach the calendar without a restart
        self.set_interval(60, self.check_today)

    def tab_shown(self) -> None:
        self.check_today()
        # Found the first time its tab shows, so opening another tab costs no lookup
        if not self.asked:
            self.asked = True
            self.load(self.locations[0])

    def check_today(self) -> None:
        self.set_today(date.today())

    def set_today(self, today: date) -> None:
        """Move today there, taking the month in focus along if it was today's."""
        if today == self.today:
            return
        followed = (self.year, self.month) == (self.today.year, self.today.month)
        if self.picked == self.today:
            self.picked = today
            self.show_day()
        self.today = today
        self.show_month(*((today.year, today.month) if followed else (self.year, self.month)))
        # A day picked by hand can become today
        self._show_today_button()

    @on(Input.Submitted, "#calendar-city")
    def _city_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        typed = event.value.strip()
        city = completed(typed, self.locations)
        if city != typed:
            event.input.value = city
        if city:
            self.load(city)

    @work(exclusive=True, group="place")
    async def load(self, location: str) -> None:
        """Find location, cached once found here or on the Weather tab, so seldom a request; the
        city on show stays until it is found. Until a first is found, there is no sun, no holiday,
        and the full moon and DST are by the system's clock."""
        try:
            self.place = await asyncio.to_thread(find_place, location)
        except WeatherError as error:
            self.app.notify(str(error), severity="error", timeout=10)
            return
        self.query_one(LookupBox).show_found(self.place.label)
        self.show_day()
        # The yellow days follow the city: its holidays, its DST, the full moon in its time zone
        self.show_month(self.year, self.month)

    @property
    def zone(self) -> ZoneInfo | None:
        """The place's time zone, None for the system's until it is found."""
        return ZoneInfo(self.place.timezone) if self.place else None

    def notable(self, day: date) -> str | None:
        """How the calendar marks day: "birthday" for a birthday from the config, "marked" for a full
        moon, a clock change or a public holiday, None for none."""
        if any(birthday.falls_on(day) for birthday in self.birthdays):
            return "birthday"
        zone = self.zone
        if full_moon(day, zone) or clock_change(day, zone) or public_holidays.on(day, self.place):
            return "marked"
        return None

    def show_day(self) -> None:
        """The day picked, its sun and its events over the buttons, in the place's time."""
        place, zone = self.place, self.zone
        self.query_one("#calendar-date", Static).update(self.date_text)
        birthdays = [birthday.label(self.picked) for birthday in self.birthdays if birthday.falls_on(self.picked)]
        self.query_one(DayEvents).show(birthdays, full_moon(self.picked, zone), clock_change(self.picked, zone), public_holidays.on(self.picked, self.place))
        self.query_one(DaySun).show(sun(self.picked, place.latitude, place.longitude, zone) if place else None)
        self._show_today_button()

    def _show_today_button(self) -> None:
        # Only when it would do something; hidden, not removed, so the rows stay where they are
        self.query_one("#btn-today").visible = self.picked != self.today

    @property
    def date_text(self) -> str:
        return f"{self.picked:%A, %B} {self.picked.day}, {self.picked.year}"

    def months(self) -> list[tuple[int, int]]:
        """The (year, month) shown, left to right."""
        return [shift_month(self.year, self.month, delta) for delta in range(-self.before, self.after + 1)]

    def show_month(self, year: int, month: int) -> None:
        """Put that month in focus, and its neighbours around it."""
        self.year, self.month = year, month
        for view, (shown_year, shown_month) in zip(self.query(MonthView), self.months()):
            view.show(shown_year, shown_month, self.today, self.picked)

    def action_shift(self, delta: int) -> None:
        """Move every month by delta: -1 is the previous month, 1 the next. A day picked that leaves
        the view moves along, to the same day of the nearest month shown (the 28th for a 31st in
        February)."""
        self.show_month(*shift_month(self.year, self.month, delta))
        shown = self.months()
        picked = (self.picked.year, self.picked.month)
        if picked not in shown:
            year, month = shown[0] if picked < shown[0] else shown[-1]
            self.pick(self.picked.replace(year=year, month=month, day=min(self.picked.day, monthrange(year, month)[1])))

    @on(MonthView.DayClicked)
    def _day_clicked(self, event: MonthView.DayClicked) -> None:
        event.stop()
        self.pick(event.day)

    def pick(self, day: date) -> None:
        """Highlight day and show it in full."""
        self.picked = day
        self.show_month(self.year, self.month)
        self.show_day()

    @on(Button.Pressed, "#btn-previous")
    def _previous(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(-1)

    @on(Button.Pressed, "#btn-today")
    def _today(self, event: Button.Pressed) -> None:
        event.stop()
        self.go_today()

    def go_today(self) -> None:
        """Today's month in focus, and today picked."""
        self.show_month(self.today.year, self.today.month)
        if self.picked != self.today:
            self.pick(self.today)

    @on(Button.Pressed, "#btn-next")
    def _next(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_shift(1)
