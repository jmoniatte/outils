import asyncio
from time import time

from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Button, Input

from ..click_only import quick_button
from ..config import Config
from ..weather import (
    IMPERIAL,
    METRIC,
    SKIES,
    WIND_LABELS,
    Forecast,
    Span,
    WeatherError,
    describe,
    forecast,
    speed,
    temperature,
    weather_spans,
)
from .lookup_box import LookupBox, lookup_row

# The day's label, its icon and words (as wide as the week's longest, and two spaces), then its high
# and low, how much it changed, and when it rains. "Wednesday" and three spaces
DAY_LABEL = 12
# Before when it rains
GAP = " " * 4
# "↑ 4°", "↓12°": the change from the day before's high
CHANGE_WIDTH = 4
# On each side of the change: its arrow and color set it apart already
CHANGE_GAP = " " * 2
# A difference in temperature worth saying, by units (°C, °F): how it feels against what it is,
# and a day's high against the day before's
NOTICEABLE = {METRIC: 3, IMPERIAL: 5}
# Wind strong enough to be worth saying, by units
STRONG_WIND = {METRIC: 30, IMPERIAL: 20}
# Days in a week: after that the names come back
WEEK = 7
# Seconds a forecast stays on show before the tab, shown again, asks for a new one
MAX_AGE = 60 * 60


class WeatherView(Vertical):
    """A box to type a city in, then its forecast; it opens on the config's first city.

    Once found, the place shows in the box in full and in blue ("Portland, Oregon, United
    States"), so the box says both what to type and where the forecast is for. The box only has
    focus once clicked, so ?, t and q keep working until then, and it lets go after Enter, or
    Escape. Typing completes the config's cities, in grey: → takes the rest, and so does Enter.
    °C and °F beside the box switch the units, the one in use in blue.
    """

    class UnitsChanged(Message):
        """°C or °F was picked; the app saves it to the config."""

        def __init__(self, units: str) -> None:
            super().__init__()
            self.units = units

    # Shown at the bottom right, over the footer's rule: the words, then the link. Open-Meteo's
    # data is CC BY 4.0, which asks for it
    CREDIT = ("Data by", "https://open-meteo.com")

    def __init__(self, config: Config) -> None:
        super().__init__(id="weather")
        self.config = config
        # What was last asked for, asked again once the forecast is old; empty until the tab shows
        self.location = ""
        # When the forecast on show came; wall time, since a night's suspend must count
        self.loaded_at = 0.0

    def compose(self) -> ComposeResult:
        buttons = [quick_button(label, f"units-{units}") for units, label in ((METRIC, "°C"), (IMPERIAL, "°F"))]
        box = LookupBox(
            self.config.location,
            placeholder="City, or City, Region or Country",
            suggester=SuggestFromList(self.config.locations, case_sensitive=False),
            id="weather-city",
        )
        yield lookup_row("City", box, Horizontal(*buttons, id="weather-units"))
        yield ForecastView(self.config)

    def on_mount(self) -> None:
        self._show_units()

    def _show_units(self) -> None:
        for units in (METRIC, IMPERIAL):
            self.query_one(f"#units-{units}", Button).set_class(units == self.config.units, "-selected")

    @on(Button.Pressed, "#weather-units Button")
    def _units_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        units = event.button.id.removeprefix("units-")
        if units == self.config.units:
            return
        self.config.units = units
        self._show_units()
        # The forecast is always metric: only redrawn, never asked again
        self.query_one(ForecastView).refresh(layout=True)
        self.post_message(self.UnitsChanged(units))

    def tab_shown(self) -> None:
        # Asked the first time its tab shows, so opening another tab costs no request, then again once old
        if time() - self.loaded_at > MAX_AGE:
            self.load(self.location or self.config.location)

    @on(Input.Submitted, "#weather-city")
    def _city_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        typed = event.value.strip()
        city = self._saved(typed)
        if city != typed:
            # The city completed shows in full while it is looked up, until the place found replaces it
            event.input.value = city
        if city:
            self.load(city)

    def _saved(self, typed: str) -> str:
        """The config's city that what was typed begins, as the box completes it, so Enter takes
        what it shows; else what was typed."""
        if typed:
            for city in self.config.locations:
                if city.casefold().startswith(typed.casefold()):
                    return city
        return typed

    @work(exclusive=True)
    async def load(self, location: str) -> None:
        """Ask Open-Meteo for location, keeping what is on show until the answer comes."""
        self.location = location
        view = self.query_one(ForecastView)
        if view.forecast is None:
            view.show(None, f"Asking Open-Meteo for the weather in {location}...")
        try:
            found = await asyncio.to_thread(forecast, location)
        except WeatherError as error:
            view.show(None, str(error))
            self.app.notify(str(error), severity="error", timeout=10)
            return
        self.loaded_at = time()
        self.query_one(LookupBox).show_found(found.place.label)
        view.show(found)


class ForecastView(Widget):
    """The weather now, then a row per day, today first: how much warmer or cooler than the day
    before, then when rain, snow or a storm is likely. Where it is for shows in the city box.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {
        "weather--temperature",
        "weather--dim",
        "weather--high",
        "weather--low",
        *(f"weather--sky-{sky}" for sky in set(SKIES.values())),
    }

    def __init__(self, config: Config) -> None:
        super().__init__(id="forecast")
        # Read for its units when drawing: °C or °F is only a redraw
        self.config = config
        self.forecast: Forecast | None = None
        # Shown, dim, while there is no forecast: that it is coming, or why it did not
        self.message = ""

    def show(self, found: Forecast | None, message: str = "") -> None:
        self.forecast = found
        self.message = message
        self.refresh(layout=True)

    def _style(self, name: str) -> Style:
        return self.get_component_rich_style(f"weather--{name}")

    def _icon(self, icon: str) -> Text:
        """The icon in its sky's color: a yellow sun or moon, blue rain."""
        return Text(icon, style=self._style(f"sky-{SKIES[icon]}"))

    def render(self) -> Text:
        if self.forecast is None:
            return Text(self.message, style=self._style("dim"))
        return Text("\n").join([self._now_line(), Text(), *self._day_lines()])

    def _now_line(self) -> Text:
        """The weather now on one line; how it feels and the wind only when they matter."""
        units = self.config.units
        now = self.forecast.current
        words, icon = describe(now.code, now.is_day)
        line = self._icon(icon) + Text("   ")
        # Degrees only, like the rest: °C or °F beside the city says which
        line.append(f"{round(temperature(now.temperature, units))}°", style=self._style("temperature"))
        line.append(f"   {words}")
        extras = []
        feels_like = temperature(now.feels_like, units)
        if abs(feels_like - temperature(now.temperature, units)) >= NOTICEABLE[units]:
            extras.append(f"feels like {round(feels_like)}°")
        wind = speed(now.wind, units)
        if wind >= STRONG_WIND[units]:
            extras.append(f"wind {round(wind)} {WIND_LABELS[units]}")
        if extras:
            line.append("   " + " · ".join(extras), style=self._style("dim"))
        return line

    def _day_lines(self) -> list[Text]:
        days = self.forecast.days
        units = self.config.units
        # As narrow as the week allows
        description = max(len(describe(day.code)[0]) for day in days) + 2
        # A column only when some day has a change worth saying
        changes = [self._change(index) for index in range(len(days))]
        lines = []
        # Today first, then by name: in a list read in order, a name that comes back is plainly the next week's
        for index, day in enumerate(days):
            words, icon = describe(day.code)
            label = f"{day.day:%A}" if index else "Today"
            line = Text(f"{label:<{DAY_LABEL}}") + self._icon(icon) + Text(f"   {words:<{description}}")
            line.append(f"{round(temperature(day.high, units)):>3}°", style=self._style("high"))
            line.append(" / ", style=self._style("dim"))
            line.append(f"{round(temperature(day.low, units)):>3}°", style=self._style("low"))
            gap = GAP
            if any(changes):
                line.append(CHANGE_GAP)
                line.append_text(changes[index] or Text(" " * CHANGE_WIDTH))
                gap = CHANGE_GAP
            # Every row is as wide up to here, whatever it says after
            rule = line.cell_len
            # Nothing on a dry day, as for a day with no change worth saying
            spans = weather_spans(self.forecast, index)
            if spans:
                line.append(gap)
                line.append_text(self._spans(spans))
            lines.append(line)
        # A plain rule where the names come back, to mark next week; it stops before when it rains,
        # so it does not change with it
        if len(lines) > WEEK:
            lines.insert(WEEK, Text("─" * rule, style=self._style("dim")))
        return lines

    def _change(self, index: int) -> Text | None:
        """How much warmer or cooler the day at index is than the day before, by the highs, when it is
        noticeable: "↑ 4°" orange, "↓12°" cyan."""
        if not index:
            return None
        days, units = self.forecast.days, self.config.units
        difference = round(temperature(days[index].high, units)) - round(temperature(days[index - 1].high, units))
        if abs(difference) < NOTICEABLE[units]:
            return None
        warmer = difference > 0
        return Text(f"{'↑' if warmer else '↓'}{abs(difference):>2}°", style=self._style("high" if warmer else "low"))

    def _spans(self, spans: list[Span]) -> Text:
        """Each span in its kind's color, as its icon is: "Rain 5pm–6pm, snow 8pm–10pm"."""
        return Text(", ", style=self._style("dim")).join(Text(words, style=self._style(f"sky-{kind}")) for kind, words in _said(spans))


def _said(spans: list[Span]) -> list[tuple[str, str]]:
    """Each span's kind and words, the kind said only where it changes: "Rain 8am–1pm", "6pm–10pm",
    "snow after 11pm"; "Rain all day" for a span over the whole day."""
    said = []
    for number, (kind, start, end) in enumerate(spans):
        when = "all day" if start is None and end is None else _span(start, end)
        name = kind if number else kind.capitalize()
        said.append((kind, when if number and kind == spans[number - 1].kind else f"{name} {when}"))
    return said


def _span(start: int | None, end: int | None) -> str:
    if start is None:
        return f"until {_hour(end)}"
    if end is None:
        return f"after {_hour(start)}"
    return f"{_hour(start)}–{_hour(end)}"


def _hour(hour: int) -> str:
    """"3pm": the 12-hour clock, whatever the units."""
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
