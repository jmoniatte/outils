from collections.abc import Callable
from datetime import UTC, datetime

from rich.text import Text
from textual.widget import Widget

from ..clocks import Clock, read

# Nerd Font's sun, as on the weather tab: summer time is in force
DST_ICON = "\U000f0599"
# The name column, fixed so the city box in it and the epoch's values line up with the times whatever
# the names; room for "Rio de Janeiro" and longer, a name that does not fit is cut
NAME_WIDTH = 26
# At least this much space between a name and its time
NAME_GAP = 2


def utc_now() -> datetime:
    return datetime.now(UTC)


class ClockRows(Widget):
    """What ClocksView and CityClock share: redrawn when the minute turns, and a clock drawn from
    its time on: the time, the offset from UTC, a yellow sun while summer time is in force, then the
    time zone in grey.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"clocks--time", "clocks--offset", "clocks--dst", "clocks--zone"}

    def __init__(self, now: Callable[[], datetime] = utc_now, *, id: str) -> None:
        super().__init__(id=id)
        self.now = now
        self.minute = self.now().replace(second=0, microsecond=0)

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

    def _clock(self, clock: Clock) -> Text:
        reading = read(clock, self.minute)
        text = Text(reading.time, style=self._style("time"))
        text.append(f"   {reading.offset}", style=self._style("offset"))
        # Two spaces where the sun is not, so the zones line up
        text.append(f" {DST_ICON}" if reading.dst else "  ", style=self._style("dst"))
        text.append(f"   {reading.zone}", style=self._style("zone"))
        return text


class ClocksView(ClockRows):
    """The time now in a few places, a row each: the name, then the clock."""

    COMPONENT_CLASSES = ClockRows.COMPONENT_CLASSES | {"clocks--name"}

    def __init__(self, clocks: list[Clock], now: Callable[[], datetime] = utc_now) -> None:
        super().__init__(now, id="clocks")
        self.clocks = clocks
        self.display = bool(clocks)

    def render(self) -> Text:
        text = Text()
        for index, clock in enumerate(self.clocks):
            if index:
                text.append("\n")
            text.append(f"{fit_name(clock.name):<{NAME_WIDTH}}", style=self._style("name"))
            text.append_text(self._clock(clock))
        return text


class CityClock(ClockRows):
    """The rest of the row a city box starts: the city found, from its time on, or that it is
    being looked up, or why it was not found, in red. Hidden while there is none."""

    COMPONENT_CLASSES = ClockRows.COMPONENT_CLASSES | {"clocks--message", "clocks--error"}

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        super().__init__(now, id="city-clock")
        self.city: Clock | None = None
        self.message = ""
        self.error = False
        self.display = False

    def show(self, city: Clock | None, message: str = "", error: bool = False) -> None:
        self.city, self.message, self.error = city, message, error
        self.display = bool(city or message)
        self.refresh(layout=True)

    def render(self) -> Text:
        if self.city is not None:
            return self._clock(self.city)
        return Text(self.message, style=self._style("error" if self.error else "message"))


def fit_name(name: str) -> str:
    """name, cut with "…" when too long for the name column and its gap."""
    room = NAME_WIDTH - NAME_GAP
    return name if len(name) <= room else name[: room - 1] + "…"
