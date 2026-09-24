import asyncio
from datetime import date

from rich.text import Text
from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from ..config import Config
from ..weather import UNIT_LABELS, Forecast, Place, WeatherError, describe, forecast

# The day's label, its icon and words, then its high and low, its chance of rain and how much
# "Wednesday" and two spaces
DAY_LABEL = 11
DESCRIPTION = 20


class WeatherView(Vertical):
    """A box to type a city in, then its forecast; it opens on the config's location.

    Once found, the place shows in the box in full and in blue ("Portland, Oregon, United
    States"), so the box says both what to type and where the forecast is for. The box only has
    focus once clicked, so ?, t and q keep working until then, and it lets go after Enter, or
    Escape.
    """

    BINDINGS = [
        # Only reached while the box has focus; otherwise Escape quits, as everywhere
        Binding("escape", "leave_city", show=False),
    ]

    def __init__(self, config: Config, today: date | None = None) -> None:
        super().__init__(id="weather")
        self.config = config
        self.today = today
        self.asked = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="weather-city-row"):
            yield Static("City", id="weather-city-label")
            yield Input(self.config.location, placeholder="City, or City, Region or Country", id="weather-city")
        yield ForecastView(self.config.units, self.today)

    def on_show(self) -> None:
        # Asked the first time its tab shows, so opening another tab costs no request
        if not self.asked:
            self.asked = True
            self.query_one(ForecastView).load(self.config.location)

    @on(events.DescendantFocus)
    def _city_focused(self, event: events.DescendantFocus) -> None:
        # Typing: plain text again, the blue is for a place found
        if event.widget.id == "weather-city":
            event.widget.remove_class("-found")

    def on_forecast_view_found(self, event: "ForecastView.Found") -> None:
        city = self.query_one("#weather-city", Input)
        city.value = event.place.label
        city.cursor_position = 0
        city.add_class("-found")

    def action_leave_city(self) -> None:
        self.screen.set_focus(None)

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

    @work(exclusive=True)
    async def load(self, location: str) -> None:
        """Ask Open-Meteo for location, keeping what is on show until the answer comes."""
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
