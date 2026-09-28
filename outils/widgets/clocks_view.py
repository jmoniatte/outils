from collections.abc import Callable
from datetime import UTC, datetime

from rich.text import Text
from textual.widget import Widget

from ..clocks import Clock, read

# Nerd Font's sun, as on the weather tab: summer time is in force
DST_ICON = "\U000f0599"
# The name column, fixed so the city box in it and the epoch's values line up with the times whatever
# the names; room for "Rio de Janeiro" and longer, a name that does not fit is cut
NAME_WIDTH = 20
# At least this much space between a name and its time
NAME_GAP = 2


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClocksView(Widget):
    """The time now in a few places, a row each: the name, the time, the offset from UTC, and a
    yellow sun while summer time is in force, then the time zone in grey.

    With names False it is the rest of the row a city box starts: the city found, or that it is
    being looked up, or why it was not found, in red.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"clocks--name", "clocks--time", "clocks--offset", "clocks--dst", "clocks--zone", "clocks--message", "clocks--error"}

    def __init__(self, clocks: list[Clock], now: Callable[[], datetime] = utc_now, *, names: bool = True, id: str = "clocks") -> None:
        super().__init__(id=id)
        self.clocks = clocks
        self.names = names
        self.now = now
        self.minute = self.now().replace(second=0, microsecond=0)
        self.city: Clock | None = None
        # In place of the city: that it is being looked up, or why it was not found
        self.message = ""
        self.error = False
        self._show()

    def show_city(self, city: Clock | None, message: str = "", error: bool = False) -> None:
        self.city, self.message, self.error = city, message, error
        self._show()
        self.refresh(layout=True)

    def _show(self) -> None:
        self.display = bool(self.clocks or self.city or self.message)

    def on_mount(self) -> None:
        # Checked every second, redrawn only when the minute turns
        self.set_interval(1, self.tick)

    def tick(self) -> None:
        minute = self.now().replace(second=0, microsecond=0)
        if minute != self.minute:
            self.minute = minute
            self.refresh()

    def _style(self, name: str):
        return self.get_component_rich_style(f"clocks--{name}")

    def render(self) -> Text:
        clocks = [*self.clocks, self.city] if self.city else self.clocks
        text = Text()
        for index, clock in enumerate(clocks):
            reading = read(clock, self.minute)
            if index:
                text.append("\n")
            if self.names:
                text.append(f"{fit_name(reading.name):<{NAME_WIDTH}}", style=self._style("name"))
            text.append(reading.time, style=self._style("time"))
            text.append(f"   {reading.offset}", style=self._style("offset"))
            # Two spaces where the sun is not, so the zones line up
            text.append(f" {DST_ICON}" if reading.dst else "  ", style=self._style("dst"))
            text.append(f"   {reading.zone}", style=self._style("zone"))
        if self.message:
            if clocks:
                text.append("\n")
            text.append(self.message, style=self._style("error" if self.error else "message"))
        return text


def fit_name(name: str) -> str:
    """name, cut with "…" when too long for the name column and its gap."""
    room = NAME_WIDTH - NAME_GAP
    return name if len(name) <= room else name[: room - 1] + "…"
