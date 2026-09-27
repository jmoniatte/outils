import asyncio
from time import time

from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input

from ..click_only import quick_button
from ..config import Config
from ..weather import (
    IMPERIAL,
    METRIC,
    WIND_LABELS,
    Forecast,
    WeatherError,
    describe,
    forecast,
    rain_window,
    speed,
    temperature,
)
from .lookup_box import LookupBox, lookup_row

# The day's label, its icon and words (as wide as the week's longest, and two spaces), then its high
# and low and its facts. "Wednesday" and three spaces
DAY_LABEL = 12
# Between the temperatures and the facts
GAP = " " * 4
# A difference in temperature worth saying, by units (°C, °F): how it feels against what it is,
# and a day's high against the day before's
NOTICEABLE = {METRIC: 3, IMPERIAL: 5}
# Wind strong enough to be worth saying, by units
STRONG_WIND = {METRIC: 30, IMPERIAL: 20}
# Seconds a forecast stays on show before the tab, shown again, asks for a new one
MAX_AGE = 60 * 60


class WeatherView(Vertical):
    """A box to type a city in, then its forecast; it opens on the config's location.

    Once found, the place shows in the box in full and in blue ("Portland, Oregon, United
    States"), so the box says both what to type and where the forecast is for. The box only has
    focus once clicked, so ?, t and q keep working until then, and it lets go after Enter, or
    Escape. °C and °F beside the box switch the units, the one in use in blue.
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
        box = LookupBox(self.config.location, placeholder="City, or City, Region or Country", id="weather-city")
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
        city = event.value.strip()
        if city:
            self.load(city)

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
    """The weather now, then a row per day, today first, with its facts: when it is likely to rain,
    how much warmer or cooler than the day before. Where it is for shows in the city box.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {
        "weather--temperature",
        "weather--dim",
        "weather--high",
        "weather--low",
        "weather--rain",
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

    def render(self) -> Text:
        if self.forecast is None:
            return Text(self.message, style=self._style("dim"))
        return Text("\n").join([self._now_line(), Text(), *self._day_lines()])

    def _now_line(self) -> Text:
        """The weather now on one line; how it feels and the wind only when they matter."""
        units = self.config.units
        now = self.forecast.current
        words, icon = describe(now.code, now.is_day)
        line = Text(f"{icon}   ")
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
        lines = []
        # The first day is today where the place is; a week never repeats a day name, so the name alone is enough
        for index, day in enumerate(days):
            words, icon = describe(day.code)
            label = f"{day.day:%A}" if index else "Today"
            line = Text(f"{label:<{DAY_LABEL}}{icon}   {words:<{description}}")
            line.append(f"{round(temperature(day.high, units)):>3}°", style=self._style("high"))
            line.append(" / ", style=self._style("dim"))
            line.append(f"{round(temperature(day.low, units)):>3}°", style=self._style("low"))
            line.append(GAP)
            line.append_text(Text(" · ", style=self._style("dim")).join(self._facts(index)))
            lines.append(line)
        return lines

    def _facts(self, index: int) -> list[Text]:
        """What is worth knowing about the day at index, each in its color: when it rains, or that it
        is dry; how much warmer or cooler than the day before, when it is noticeable."""
        days, units = self.forecast.days, self.config.units
        window = rain_window(self.forecast, index)
        facts = [Text(_rain(window, units), style=self._style("rain")) if window else Text("Dry", style=self._style("dim"))]
        if index:
            difference = round(temperature(days[index].high, units)) - round(temperature(days[index - 1].high, units))
            if abs(difference) >= NOTICEABLE[units]:
                warmer = difference > 0
                change = f"{abs(difference)}° {'warmer' if warmer else 'cooler'}"
                facts.append(Text(change, style=self._style("high" if warmer else "low")))
        return facts


def _rain(window: tuple[int | None, int | None], units: str) -> str:
    """"Rain 3pm – 9pm", "Rain after 6pm", "Rain until 9am" or "Rain all day"."""
    start, end = window
    if start is None and end is None:
        return "Rain all day"
    if start is None:
        return f"Rain until {_hour(end, units)}"
    if end is None:
        return f"Rain after {_hour(start, units)}"
    return f"Rain {_hour(start, units)} – {_hour(end, units)}"


def _hour(hour: int, units: str) -> str:
    """"15h" in metric; "3pm" in imperial, which goes with the 12-hour clock."""
    if units == METRIC:
        return f"{hour}h"
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
