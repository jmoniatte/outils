from datetime import UTC, datetime

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Rule, Static

from ..config import Config
from ..epoch import EpochError, parse, rows, seconds
from .clocks_view import ClocksView
from .lookup_box import LookupBox

# The longest label and two spaces; the Epoch label is as wide in the TCSS, to line up the box
LABEL = len("Relative") + 2


class TimeView(Vertical):
    """A box that turns an epoch timestamp into a date, or a date into a timestamp, then under a
    rule the time now in the config's clocks, a row each.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(id="time")
        self.clocks = config.clocks
        # Until something is converted, the box and its rows follow now, second by second
        self.following = True
        # What the box was last given, to tell when it was edited
        self.shown = ""

    def compose(self) -> ComposeResult:
        with Horizontal(classes="lookup-row", id="epoch-row"):
            yield Static("Epoch", classes="lookup-label")
            yield LookupBox(placeholder="Timestamp or date", id="epoch-input")
            now = Button("Now", id="btn-now")
            now.can_focus = False  # A click must not pull focus, as on the calendar's buttons
            now.active_effect_duration = 0
            yield now
        yield EpochDetails()
        yield Rule(id="time-rule")
        yield ClocksView(self.clocks)

    def on_mount(self) -> None:
        # One timer for both, so how far from now is never drawn before now moves on
        self.set_interval(1, self.tick)

    def on_show(self) -> None:
        self.follow_now()

    def tick(self) -> None:
        if not self.follow_now():
            self.query_one(EpochDetails).move_to(datetime.now(UTC))

    def follow_now(self) -> bool:
        """Show now, unless the box is in use; say whether it did."""
        # Held while the box is being typed in, or holds an edit not yet converted
        box = self.query_one(LookupBox)
        live = self.following and not box.has_focus and box.value in ("", self.shown)
        if live:
            self.convert("")
        # Nothing to go back to while it follows now; hidden, not removed, so it keeps its place
        self.query_one("#btn-now", Button).visible = not live
        return live

    @on(Button.Pressed, "#btn-now")
    def _now(self, event: Button.Pressed) -> None:
        event.stop()
        self.following = True
        self.screen.set_focus(None)
        self.convert("")
        self.follow_now()

    @on(Input.Submitted, "#epoch-input")
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        # An empty box goes back to following now
        self.following = not event.value.strip()
        self.convert(event.value)
        self.screen.set_focus(None)
        self.follow_now()

    def convert(self, text: str) -> None:
        """Show what text names, or why it names nothing; an empty text is now."""
        details = self.query_one(EpochDetails)
        # Whole seconds: now needs no fraction
        now = datetime.now(UTC).replace(microsecond=0)
        try:
            moment = parse(text, now)
        except EpochError as error:
            details.show(None, now, str(error))
            return
        # Like the IP tab: what was converted, in blue, the seconds for now
        self.shown = text.strip() or seconds(moment)
        self.query_one(LookupBox).show_found(self.shown)
        details.show(moment, now)


class EpochDetails(Widget):
    """What the box names, a row each: the timestamp, the date in UTC and here, and how far from now.

    How far from now is measured from the time TimeView gives it every second, not the clock at
    each redraw, so it cannot say "1 second ago" for now until now moves on.
    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"epoch--label", "epoch--error"}

    def __init__(self) -> None:
        super().__init__(id="epoch-details")
        self.moment: datetime | None = None
        self.at = datetime.now(UTC)
        self.error = ""

    def show(self, moment: datetime | None, at: datetime, error: str = "") -> None:
        self.moment = moment
        self.at = at
        self.error = error
        self.refresh(layout=True)

    def move_to(self, at: datetime) -> None:
        """Measure how far from now from at."""
        self.at = at
        self.refresh()

    def render(self) -> Text:
        if self.error:
            return Text(self.error, style=self.get_component_rich_style("epoch--error"))
        if self.moment is None:
            return Text()
        text = Text()
        for index, (label, value) in enumerate(rows(self.moment, self.at)):
            if index:
                text.append("\n")
            text.append(f"{label:<{LABEL}}", style=self.get_component_rich_style("epoch--label"))
            text.append(value)
        return text
