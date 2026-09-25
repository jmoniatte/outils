import asyncio

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, Static

from ..config import Config
from ..ipinfo import FIELDS, IpInfoError, fetch, rows
from .lookup_box import LookupBox

# The longest label and two spaces; the IP label is as wide in the TCSS, to line up the box
LABEL = max(len(label) for _, label in FIELDS) + 2


class IpView(Vertical):
    """A box to type an address or a host name in, then what ipinfo.io knows about it.

    It opens on this computer's public address. What was looked up shows in the box, in blue: the
    address, or the host name as typed; an empty box goes back to this computer's.
    """

    # Shown at the bottom right, over the footer's rule: the words, then the link
    CREDIT = ("IP data by", "https://ipinfo.io")

    def __init__(self, config: Config) -> None:
        super().__init__(id="ip")
        self.asked = False

    def compose(self) -> ComposeResult:
        with Horizontal(classes="lookup-row"):
            yield Static("IP", classes="lookup-label")
            yield LookupBox(placeholder="Address or host name, empty for this computer's", id="ip-address")
        yield IpDetails()

    def on_show(self) -> None:
        # Asked the first time its tab shows, so opening another tab costs no request
        if not self.asked:
            self.asked = True
            self.load()

    @on(Input.Submitted, "#ip-address")
    def _address_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.load(event.value.strip())
        self.screen.set_focus(None)

    @work(exclusive=True)
    async def load(self, target: str = "") -> None:
        """Ask ipinfo.io about target, keeping what is on show until the answer comes."""
        details = self.query_one(IpDetails)
        try:
            data = await asyncio.to_thread(fetch, target)
        except IpInfoError as error:
            # In place of the details, not in the header: it answers what was typed
            details.show([], str(error))
            return
        # A host name stays as typed: the IP row gives its address
        self.query_one(LookupBox).show_found(target or data["ip"])
        details.show(rows(data))


class IpDetails(Widget):
    """Where ipinfo.io places the address and whose network it is on, a row per field.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"ip--label", "ip--address", "ip--message", "ip--error"}

    def __init__(self) -> None:
        super().__init__(id="ip-details")
        self.rows: list[tuple[str, str]] = []
        self.message = "Asking ipinfo.io..."
        self.error = ""

    def show(self, rows: list[tuple[str, str]], error: str = "") -> None:
        self.rows = rows
        self.error = error
        self.refresh(layout=True)

    def render(self) -> Text:
        if self.error:
            return Text(self.error, style=self.get_component_rich_style("ip--error"))
        if not self.rows:
            return Text(self.message, style=self.get_component_rich_style("ip--message"))
        text = Text()
        for index, (label, value) in enumerate(self.rows):
            if index:
                text.append("\n")
            text.append(f"{label:<{LABEL}}", style=self.get_component_rich_style("ip--label"))
            # The address is what the tab is for
            text.append(value, style=self.get_component_rich_style("ip--address") if index == 0 else "")
        return text
