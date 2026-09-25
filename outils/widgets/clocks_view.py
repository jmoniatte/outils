from collections.abc import Callable
from datetime import UTC, datetime

from rich.text import Text
from textual.widget import Widget

from ..clocks import Clock, read

# Nerd Font's sun, as on the weather tab: summer time is in force
DST_ICON = "\U000f0599"


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClocksView(Widget):
    """The time now in a few places, a row each: the name, the time, the offset from UTC, and a
    yellow sun while summer time is in force.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"clocks--name", "clocks--time", "clocks--offset", "clocks--dst"}

    def __init__(self, clocks: list[Clock], now: Callable[[], datetime] = utc_now) -> None:
        super().__init__(id="clocks")
        self.clocks = clocks
        self.now = now
        self.minute = self.now().replace(second=0, microsecond=0)
        self.display = bool(clocks)

    def on_mount(self) -> None:
        # Checked every second, redrawn only when the minute turns
        self.set_interval(1, self.tick)

    def tick(self) -> None:
        minute = self.now().replace(second=0, microsecond=0)
        if minute != self.minute:
            self.minute = minute
            self.refresh()

    def render(self) -> Text:
        name_width = max((len(clock.name) for clock in self.clocks), default=0) + 3
        text = Text()
        for index, clock in enumerate(self.clocks):
            reading = read(clock, self.minute)
            if index:
                text.append("\n")
            text.append(f"{reading.name:<{name_width}}", style=self.get_component_rich_style("clocks--name"))
            text.append(reading.time, style=self.get_component_rich_style("clocks--time"))
            text.append(f"   {reading.offset}", style=self.get_component_rich_style("clocks--offset"))
            if reading.dst:
                text.append(f" {DST_ICON}", style=self.get_component_rich_style("clocks--dst"))
        return text
