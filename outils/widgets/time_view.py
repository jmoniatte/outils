import asyncio
from datetime import UTC, datetime

from rich.style import Style
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Button, Input, Rule, Static

from ..click_only import quick_button
from ..clocks import Clock, find_zone, suggested_zones, zone_named
from ..config import Config
from ..epoch import LABELS, EpochError, parse, rows, seconds
from ..weather import WeatherError, find_place
from .clocks_view import NAME_WIDTH, ClocksView, fit_name
from .lookup_box import LookupBox, LookupDetails, completed, lookup_row


def find_clock(location: str) -> tuple[Clock, str]:
    """A clock for location and what its box shows once found: a time zone ("Europe/Paris", "UTC")
    as it is, with no request, else a city through Open-Meteo, in full. Blocks; a failure is a WeatherError."""
    clock = zone_named(location)
    if clock is not None:
        return clock, clock.zone.key
    place = find_place(location)
    zone = find_zone(place.timezone)
    if zone is None:
        raise WeatherError(f"Open-Meteo gives no time zone for {place.label}")
    return Clock(place.name, zone), place.label


class EpochDetails(LookupDetails):
    """The epoch's rows, with the In zone's row red when it could not be found; the values line up
    with the clocks' times, so an In zone's name has room."""

    def __init__(self) -> None:
        super().__init__(LABELS, id="epoch-details")
        self.label_width = NAME_WIDTH
        self.error_row: int | None = None

    def value_style(self, index: int) -> Style | str:
        return self.get_component_rich_style("lookup--error") if index == self.error_row else ""


class TimeView(Vertical):
    """The time now in the config's clocks, a row each, then a row whose name is a box to add a
    city's; then under a rule a box that turns an epoch timestamp into a date, or an ISO 8601 date into
    a timestamp, with beside it a city or time zone to show the date in as well.

    The city's time zone comes from Open-Meteo's geocoding, as the weather's place does, and is
    cached with it; the box completes the weather's cities. The city is not saved.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(id="time")
        self.clocks = config.clocks
        self.locations = config.locations
        # What the city boxes suggest: the weather's cities, then the time zones
        self.suggestions = [*self.locations, *suggested_zones()]
        # Until something is converted, the box and its rows follow now, second by second
        self.following = True
        # What the box was last given, to tell when it was edited
        self.shown = ""
        # What the box names, None when it names nothing
        self.moment: datetime | None = None
        # The In box's zone, shown as one more row; or in its place that it is being looked up, or why not
        self.extra: Clock | None = None
        self.extra_note = ""
        self.extra_error = False

    def compose(self) -> ComposeResult:
        details = EpochDetails()
        yield ClocksView(self.clocks)
        city = LookupBox(
            placeholder="Add a city or zone",
            suggester=SuggestFromList(self.suggestions, case_sensitive=False),
            id="city-input",
        )
        yield Horizontal(city, ClocksView([], names=False, id="city-clock"), id="city-row")
        yield Rule(id="time-rule")
        box = LookupBox(placeholder="Timestamp or ISO 8601 date", id="epoch-input")
        zone = LookupBox(placeholder="City or time zone", suggester=SuggestFromList(self.suggestions, case_sensitive=False), id="zone-input")
        now = quick_button("Now", "btn-now", "tinted -green")
        yield lookup_row("Epoch", box, now, Static("In", classes="lookup-label", id="zone-label"), zone, label_width=details.label_width)
        yield details

    def _completed(self, typed: str) -> str:
        """What Enter looks up: the weather city the box completes, or the time zone once a "/" is
        typed; else what was typed, so "Eu" is still a town in France, not Europe/Amsterdam."""
        city = completed(typed, self.locations)
        return completed(typed, suggested_zones()) if city == typed and "/" in typed else city

    def on_mount(self) -> None:
        # One timer for both, so how far from now is never drawn before now moves on
        self.set_interval(1, self.tick)

    def tab_shown(self) -> None:
        self.follow_now()

    def tick(self) -> None:
        if not self.follow_now() and self.moment:
            self.measure(datetime.now(UTC))

    def follow_now(self) -> bool:
        """Show now, unless the box is in use; say whether it did."""
        # Held while the box is being typed in, or holds an edit not yet converted
        box = self.query_one("#epoch-input", LookupBox)
        live = self.following and self.screen.focused is not box and box.value in ("", self.shown)
        if live:
            self.convert("")
        # Nothing to go back to while it follows now; hidden, not removed, so it keeps its place
        self.query_one("#btn-now", Button).visible = not live
        return live

    @on(Button.Pressed, "#btn-now")
    def _now(self, event: Button.Pressed) -> None:
        event.stop()
        self.following = True
        self.screen.set_focus(None)
        self.convert("")
        self.follow_now()

    @on(Input.Submitted, "#city-input")
    def _city_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        city = self._completed(event.value.strip())
        if not city:
            # An empty box takes the city away
            self.workers.cancel_group(self, "city")
            self.query_one("#city-clock", ClocksView).show_city(None)
            return
        event.input.value = city
        self.find_city(city)

    @work(exclusive=True, group="city")
    async def find_city(self, location: str) -> None:
        """Show location's time on the box's row, its short name in the box."""
        clocks = self.query_one("#city-clock", ClocksView)
        clocks.show_city(None, f"Looking up {location}...")
        try:
            clock, _ = await asyncio.to_thread(find_clock, location)
        except WeatherError as error:
            clocks.show_city(None, str(error), error=True)
            return
        clocks.show_city(clock)
        self.query_one("#city-input", LookupBox).show_found(clock.name)

    @on(Input.Submitted, "#zone-input")
    def _zone_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        location = self._completed(event.value.strip())
        self.workers.cancel_group(self, "zone")
        self.extra = None
        if location:
            event.input.value = location
            self.find_extra(location)
        else:
            # An empty box takes the row away
            self._note("")

    @work(exclusive=True, group="zone")
    async def find_extra(self, location: str) -> None:
        """Show the moment in location too, its place in full in the box."""
        self._note("Looking up...")
        try:
            clock, found = await asyncio.to_thread(find_clock, location)
        except WeatherError as error:
            self._note(str(error), error=True)
            return
        self.extra = clock
        self.query_one("#zone-input", LookupBox).show_found(found)
        self._note("")

    def _note(self, text: str, error: bool = False) -> None:
        self.extra_note, self.extra_error = text, error
        if self.moment is not None:
            self.measure(datetime.now(UTC))

    @on(Input.Submitted, "#epoch-input")
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        # An empty box goes back to following now
        self.following = not event.value.strip()
        self.convert(event.value)
        self.follow_now()

    def convert(self, text: str) -> None:
        """Show what text names, or why it names nothing; an empty text is now."""
        # Whole seconds: now needs no fraction
        now = datetime.now(UTC).replace(microsecond=0)
        try:
            self.moment = parse(text, now)
        except EpochError as error:
            self.moment = None
            self.query_one(LookupDetails).show([], str(error))
            return
        # Like the IP tab: what was converted, in blue, the seconds for now
        self.shown = text.strip() or seconds(self.moment)
        self.query_one("#epoch-input", LookupBox).show_found(self.shown)
        self.measure(now)

    def measure(self, now: datetime) -> None:
        """Show the moment a row each, how far from now measured from now; the In zone's after Local."""
        details = self.query_one(EpochDetails)
        found = rows(self.moment, now, extra=(fit_name(self.extra.name), self.extra.zone) if self.extra else None)
        details.error_row = None
        if self.extra_note:
            found.insert(3, ("In", self.extra_note))
            details.error_row = 3 if self.extra_error else None
        details.show(found)
