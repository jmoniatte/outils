import asyncio
from time import time

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input

from ..click_only import quick_button
from ..config import Config
from ..weather import IMPERIAL, METRIC, UNIT_LABELS, Forecast, WeatherError, describe, forecast
from .lookup_box import LookupBox, lookup_row

# The day's label, its icon and words, then its high and low, its chance of rain and how much.
# "Wednesday" and three spaces
DAY_LABEL = 12
# "Thunderstorm, hail" and four spaces
DESCRIPTION = 22
# Between the numbers' columns
GAP = " " * 5
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
        # What was last asked for, so a change of units asks for it again; empty until the tab shows
        self.location = ""
        # When the forecast on show came; wall time, since a night's suspend must count
        self.loaded_at = 0.0

    def compose(self) -> ComposeResult:
        buttons = [quick_button(label, f"units-{units}") for units, label in ((METRIC, "°C"), (IMPERIAL, "°F"))]
        box = LookupBox(self.config.location, placeholder="City, or City, Region or Country", id="weather-city")
        yield lookup_row("City", box, Horizontal(*buttons, id="weather-units"))
        yield ForecastView()

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
        # Open-Meteo converts: the place on show, asked again in the other units
        if self.location:
            self.load(self.location)
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
            found = await asyncio.to_thread(forecast, location, self.config.units)
        except WeatherError as error:
            view.show(None, str(error))
            self.app.notify(str(error), severity="error", timeout=10)
            return
        self.loaded_at = time()
        self.query_one(LookupBox).show_found(found.place.label)
        view.show(found)


class ForecastView(Widget):
    """The weather now, then a row per day, today first; where it is for shows in the city box.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {
        "weather--temperature",
        "weather--dim",
        "weather--high",
        "weather--low",
        "weather--rain",
    }

    def __init__(self) -> None:
        super().__init__(id="forecast")
        self.forecast: Forecast | None = None
        # Shown, dim, while there is no forecast: that it is coming, or why it did not
        self.message = ""

    def show(self, found: Forecast | None, message: str = "") -> None:
        self.forecast = found
        self.message = message
        self.refresh(layout=True)

    def _style(self, name: str):
        return self.get_component_rich_style(f"weather--{name}")

    def render(self) -> Text:
        if self.forecast is None:
            return Text(self.message, style=self._style("dim"))
        labels = UNIT_LABELS[self.forecast.units]
        now = self.forecast.current
        words, icon = describe(now.code, now.is_day)
        text = Text()
        text.append(f"{icon}   ")
        text.append(f"{round(now.temperature)}{labels['temperature']}", style=self._style("temperature"))
        text.append(f"   {words}")
        details = [
            f"Feels like {round(now.feels_like)}{labels['temperature']}",
            f"Wind {round(now.wind)} {labels['wind']}",
            f"Humidity {now.humidity} %",
            f"Rain {now.precipitation:g} {labels['precipitation']}",
        ]
        text.append("\n    " + "  ·  ".join(details), style=self._style("dim"))
        text.append("\n")
        # The first day is today where the place is; a week never repeats a day name, so the name alone is enough
        for index, day in enumerate(self.forecast.days):
            words, icon = describe(day.code)
            label = f"{day.day:%A}" if index else "Today"
            text.append(f"\n{label:<{DAY_LABEL}}{icon}   {words:<{DESCRIPTION}}")
            text.append(f"{round(day.high):>3}°", style=self._style("high"))
            text.append(" / ", style=self._style("dim"))
            text.append(f"{round(day.low):>3}°", style=self._style("low"))
            chance = "  –" if day.rain_chance is None else f"{day.rain_chance:>3}"
            text.append(f"{GAP}{chance} %", style=self._style("rain"))
            text.append(f"{GAP}{day.precipitation:>4.1f} {labels['precipitation']}", style=self._style("dim"))
        return text
