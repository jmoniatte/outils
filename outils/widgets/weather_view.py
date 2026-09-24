from textual.widgets import Static


class WeatherView(Static):
    """The weather forecast mode; not built yet."""

    def __init__(self) -> None:
        super().__init__("Weather forecast: not built yet", classes="mode-placeholder")
