import asyncio
from datetime import date

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static

from ..config import Config
from ..weather import IMPERIAL, METRIC, UNIT_LABELS, Forecast, Place, WeatherError, describe, forecast
from .lookup_box import LookupBox

# The day's label, its icon and words, then its high and low, its chance of rain and how much
# "Wednesday" and two spaces
DAY_LABEL = 11
DESCRIPTION = 20


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
    CREDIT = ("Weather data by", "https://open-meteo.com")

    def __init__(self, config: Config, today: date | None = None) -> None:
        super().__init__(id="weather")
        self.config = config
        self.today = today
        self.asked = False

    def compose(self) -> ComposeResult:
        with Horizontal(classes="lookup-row"):
            yield Static("City", classes="lookup-label")
            yield LookupBox(self.config.location, placeholder="City, or City, Region or Country", id="weather-city")
            with Horizontal(id="weather-units"):
                for units, label in ((METRIC, "°C"), (IMPERIAL, "°F")):
                    button = Button(label, id=f"units-{units}")
                    button.can_focus = False  # A click must not pull focus, as on the calendar's buttons
                    button.active_effect_duration = 0
                    yield button
        yield ForecastView(self.config.units, self.today)

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
        forecast_view = self.query_one(ForecastView)
        forecast_view.units = units
        # Open-Meteo converts: the place on show, asked again in the other units
        if self.asked:
            forecast_view.load(forecast_view.location)
        self.post_message(self.UnitsChanged(units))

    def on_show(self) -> None:
        # Asked the first time its tab shows, so opening another tab costs no request
        if not self.asked:
            self.asked = True
            self.query_one(ForecastView).load(self.config.location)

    def on_forecast_view_found(self, event: "ForecastView.Found") -> None:
        self.query_one(LookupBox).show_found(event.place.label)

    @on(Input.Submitted, "#weather-city")
    def _city_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        city = event.value.strip()
        if city:
            self.query_one(ForecastView).load(city)
        self.screen.set_focus(None)


class ForecastView(Widget):
    """The weather now, then a row per day, today first; where it is for shows in the city box.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    class Found(Message):
        """A forecast came in; the city box shows its place."""

        def __init__(self, place: Place) -> None:
            super().__init__()
            self.place = place

    COMPONENT_CLASSES = {
        "weather--temperature",
        "weather--dim",
        "weather--high",
        "weather--low",
        "weather--rain",
        "weather--message",
    }

    def __init__(self, units: str, today: date | None = None) -> None:
        super().__init__(id="forecast")
        self.units = units
        self.today = today or date.today()
        self.forecast: Forecast | None = None
        self.message = ""
        # What was last asked for, so a change of units asks for it again
        self.location = ""

    @work(exclusive=True)
    async def load(self, location: str) -> None:
        """Ask Open-Meteo for location, keeping what is on show until the answer comes."""
        self.location = location
        if self.forecast is None:
            self.message = f"Asking Open-Meteo for the weather in {location}..."
            self.refresh(layout=True)
        try:
            self.forecast = await asyncio.to_thread(forecast, location, self.units)
            self.post_message(self.Found(self.forecast.place))
        except WeatherError as error:
            self.forecast = None
            self.message = str(error)
            self.app.notify(str(error), severity="error", timeout=10)
        self.refresh(layout=True)

    def _style(self, name: str):
        return self.get_component_rich_style(f"weather--{name}")

    def render(self) -> Text:
        if self.forecast is None:
            return Text(self.message, style=self._style("message"))
        labels = UNIT_LABELS[self.forecast.units]
        now = self.forecast.current
        words, icon = describe(now.code, now.is_day)
        text = Text()
        text.append(f"{icon}  ")
        text.append(f"{round(now.temperature)}{labels['temperature']}", style=self._style("temperature"))
        text.append(f"  {words}")
        details = [
            f"Feels like {round(now.feels_like)}{labels['temperature']}",
            f"Wind {round(now.wind)} {labels['wind']}",
            f"Humidity {now.humidity} %",
            f"Rain {now.precipitation:g} {labels['precipitation']}",
        ]
        text.append("\n   " + " · ".join(details), style=self._style("dim"))
        text.append("\n")
        for day in self.forecast.days:
            words, icon = describe(day.code)
            # A week from today never repeats a day name, so the name alone is enough
            label = "Today" if day.day == self.today else f"{day.day:%A}"
            text.append(f"\n{label:<{DAY_LABEL}}{icon}  {words:<{DESCRIPTION}}")
            text.append(f"{round(day.high):>3}°", style=self._style("high"))
            text.append(" / ", style=self._style("dim"))
            text.append(f"{round(day.low):>3}°", style=self._style("low"))
            chance = "  –" if day.rain_chance is None else f"{day.rain_chance:>3}"
            text.append(f"   {chance} %", style=self._style("rain"))
            text.append(f"   {day.precipitation:>4.1f} {labels['precipitation']}", style=self._style("dim"))
        return text
