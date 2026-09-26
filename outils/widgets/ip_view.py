import asyncio

from rich.style import Style
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input

from ..config import Config
from ..ipinfo import FIELDS, IpInfoError, fetch, rows
from .lookup_box import LookupBox, LookupDetails, lookup_row


class IpView(Vertical):
    """A box to type an address or a host name in, then what ipinfo.io knows about it.

    It opens on this computer's public address. What was looked up shows in the box, in blue: the
    address, or the host name as typed; an empty box goes back to this computer's.
    """

    # Shown at the bottom right, over the footer's rule: the words, then the link
    CREDIT = ("Data by", "https://ipinfo.io")

    def __init__(self, config: Config) -> None:
        super().__init__(id="ip")
        self.asked = False

    def compose(self) -> ComposeResult:
        details = IpDetails()
        box = LookupBox(placeholder="Address or host name, empty for this computer's", id="ip-address")
        yield lookup_row("IP", box, label_width=details.label_width)
        yield details

    def on_show(self) -> None:
        # Asked the first time its tab shows, so opening another tab costs no request
        if not self.asked:
            self.asked = True
            self.load()

    @on(Input.Submitted, "#ip-address")
    def _address_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.load(event.value.strip())

    @work(exclusive=True)
    async def load(self, target: str = "") -> None:
        """Ask ipinfo.io about target, keeping what is on show until the answer comes."""
        details = self.query_one(IpDetails)
        try:
            data = await asyncio.to_thread(fetch, target)
        except IpInfoError as error:
            # In place of the details, not in the footer: it answers what was typed
            details.show([], str(error))
            return
        # A host name stays as typed: the IP row gives its address
        self.query_one(LookupBox).show_found(target or data["ip"])
        details.show(rows(data))


class IpDetails(LookupDetails):
    """Where ipinfo.io places the address and whose network it is on, a row per field, the address first."""

    COMPONENT_CLASSES = {"ip--address"}

    def __init__(self) -> None:
        super().__init__((label for _, label in FIELDS), "Asking ipinfo.io...", id="ip-details")

    def value_style(self, index: int) -> Style | str:
        # The address is what the tab is for
        return self.get_component_rich_style("ip--address") if index == 0 else ""
