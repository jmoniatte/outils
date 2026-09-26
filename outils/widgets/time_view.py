from datetime import UTC, datetime

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Rule

from ..click_only import quick_button
from ..config import Config
from ..epoch import LABELS, EpochError, parse, rows, seconds
from .clocks_view import ClocksView
from .lookup_box import LookupBox, LookupDetails, lookup_row


class TimeView(Vertical):
    """The time now in the config's clocks, a row each, then under a rule a box that turns an epoch
    timestamp into a date, or a date into a timestamp.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(id="time")
        self.clocks = config.clocks
        # Until something is converted, the box and its rows follow now, second by second
        self.following = True
        # What the box was last given, to tell when it was edited
        self.shown = ""
        # What the box names, None when it names nothing
        self.moment: datetime | None = None

    def compose(self) -> ComposeResult:
        yield ClocksView(self.clocks)
        yield Rule(id="time-rule")
        details = LookupDetails(LABELS, id="epoch-details")
        box = LookupBox(placeholder="Timestamp or date", id="epoch-input")
        yield lookup_row("Epoch", box, quick_button("Now", "btn-now"), label_width=details.label_width)
        yield details

    def on_mount(self) -> None:
        # One timer for both, so how far from now is never drawn before now moves on
        self.set_interval(1, self.tick)

    def on_show(self) -> None:
        self.follow_now()

    def tick(self) -> None:
        if not self.follow_now() and self.moment:
            self.measure(datetime.now(UTC))

    def follow_now(self) -> bool:
        """Show now, unless the box is in use; say whether it did."""
        # Held while the box is being typed in, or holds an edit not yet converted
        box = self.query_one(LookupBox)
        live = self.following and self.screen.focused is not box and box.value in ("", self.shown)
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
        self.follow_now()

    def convert(self, text: str) -> None:
        """Show what text names, or why it names nothing; an empty text is now."""
        # Whole seconds: now needs no fraction
        now = datetime.now(UTC).replace(microsecond=0)
        try:
            self.moment = parse(text, now)
        except EpochError as error:
            self.moment = None
            self.query_one(LookupDetails).show([], str(error))
            return
        # Like the IP tab: what was converted, in blue, the seconds for now
        self.shown = text.strip() or seconds(self.moment)
        self.query_one(LookupBox).show_found(self.shown)
        self.measure(now)

    def measure(self, now: datetime) -> None:
        """Show the moment a row each, how far from now measured from now."""
        self.query_one(LookupDetails).show(rows(self.moment, now))
