import asyncio
from datetime import UTC, datetime

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Button, Input, Rule, Static

from ..click_only import quick_button
from ..clocks import Clock, find_zone, local_zone_name, suggested_zones, zone_named
from ..config import Config
from ..epoch import LABELS, EpochError, iso, parse, rows
from ..weather import WeatherError, find_place
from .clocks_view import NAME_GAP, NAME_WIDTH, CityClock, ClocksView, fit_name
from .lookup_box import LookupBox, LookupDetails, completed, lookup_row


def find_clock(location: str) -> Clock:
    """A clock for location: a time zone ("Europe/Paris", "UTC") with no request, else a city
    through Open-Meteo. Blocks; a failure is a WeatherError."""
    clock = zone_named(location)
    if clock is not None:
        return clock
    place = find_place(location)
    zone = find_zone(place.timezone)
    if zone is None:
        raise WeatherError(f"Open-Meteo gives no time zone for {place.label}")
    return Clock(place.name, zone)


class TimeView(Vertical):
    """The time now in the config's clocks, a row each, then a row whose name is a box to add a
    city's; then under a rule a box that turns an epoch timestamp into a date, or an ISO 8601 date into
    a timestamp, the date shown in UTC and here, and in a city or time zone typed in the last row's label.

    The city's time zone comes from Open-Meteo's geocoding, as the weather's place does, and is
    cached with it; the box completes the weather's cities. The city is not saved.
    """

    # Shown at the bottom right, over the footer's rule: the cities are found by Open-Meteo, as on the Weather tab
    CREDIT = ("Data by", "https://open-meteo.com")

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
        # The zone typed in the last row, whose value is the moment there
        self.extra: Clock | None = None
        # Local's label: the system's time zone, so it says where here is
        self.local_label = fit_name(local_zone_name() or "Local")

    def compose(self) -> ComposeResult:
        details = LookupDetails(LABELS, id="epoch-details")
        # The values under the clocks' times, so a zone's row lines up with them
        details.label_width = NAME_WIDTH
        yield ClocksView(self.clocks)
        city = LookupBox(
            placeholder="City or time zone",
            suggester=SuggestFromList(self.suggestions, case_sensitive=False),
            id="city-input",
        )
        yield Horizontal(self._in_names(city), CityClock(), id="city-row")
        yield Rule(id="time-rule")
        box = LookupBox(placeholder="Timestamp or ISO 8601 date", id="epoch-input")
        yield lookup_row("Time", box, quick_button("Now", "btn-now", "tinted -green"), label_width=details.label_width)
        yield details
        zone = LookupBox(placeholder="City or time zone", suggester=SuggestFromList(self.suggestions, case_sensitive=False), id="zone-input")
        yield Horizontal(self._in_names(zone), Static("", id="zone-value", markup=False), id="zone-row")

    def _in_names(self, box: LookupBox) -> LookupBox:
        """box as wide as the name column, less its gap, so what follows it lines up with the times; with no line under it."""
        box.add_class("in-labels")
        box.styles.width = NAME_WIDTH - NAME_GAP
        box.styles.margin = (0, NAME_GAP, 0, 0)
        return box

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
            self.query_one(CityClock).show(None)
            return
        event.input.value = city
        self.find_city(city)

    @work(exclusive=True, group="city")
    async def find_city(self, location: str) -> None:
        """Show location's time on the box's row, its short name in the box."""
        row = self.query_one(CityClock)
        row.show(None, f"Looking up {location}...")
        try:
            clock = await asyncio.to_thread(find_clock, location)
        except WeatherError as error:
            row.show(None, str(error), error=True)
            return
        row.show(clock)
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
            # An empty box leaves the row's value empty
            self._show_extra()

    @work(exclusive=True, group="zone")
    async def find_extra(self, location: str) -> None:
        """Show the moment in location too, the time zone it resolves to in the box."""
        self._show_extra("Looking up...")
        try:
            clock = await asyncio.to_thread(find_clock, location)
        except WeatherError as error:
            self._show_extra(str(error), error=True)
            return
        self.extra = clock
        # The zone it resolves to, in blue: the date after it has that zone's offset
        self.query_one("#zone-input", LookupBox).show_found(clock.zone.key)
        self._show_extra()

    def _show_extra(self, note: str = "", error: bool = False) -> None:
        """The last row's value: the moment in the zone typed, or else note, red for an error."""
        value = self.query_one("#zone-value", Static)
        if note or self.extra is None or self.moment is None:
            value.update(note)
        else:
            value.update(iso(self.moment, self.extra.zone))
        value.set_class(error, "-error")
        value.set_class(bool(note) and not error, "-note")

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
            if self.extra is not None:
                self._show_extra()
            return
        # Like the IP tab: what was converted, in blue; now as the date here, ISO 8601
        self.shown = text.strip() or iso(self.moment)
        self.query_one("#epoch-input", LookupBox).show_found(self.shown)
        self.measure(now)

    def measure(self, now: datetime) -> None:
        """Show the moment a row each, how far from now measured from now, and in the zone typed."""
        found = [(self.local_label if label == "Local" else label, value) for label, value in rows(self.moment, now)]
        self.query_one(LookupDetails).show(found)
        if self.extra is not None:
            self._show_extra()
