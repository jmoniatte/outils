from textual.widgets import Static

from ..config import Config


class WeatherView(Static):
    """The weather forecast mode; not built yet."""

    def __init__(self, config: Config) -> None:
        super().__init__("Weather forecast: not built yet", classes="mode-placeholder")
