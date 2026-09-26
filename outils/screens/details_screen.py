from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static, TabPane

from ..nmcli import Details
from .share_screen import ShareTabsScreen


def detail_rows(details: Details) -> list[tuple[str, str]]:
    """Label and value of each line of the Details tab, leaving out what nmcli did not report."""
    band = f"{details.band}, channel {details.channel}" if details.channel else details.band
    rows = [
        ("Security", details.security or "open"),
        ("Band", band if details.frequency else ""),
        ("Signal", f"{details.signal}%" if details.signal else ""),
        ("Speed", f"{details.rate} Mbit/s" if details.rate else ""),
        ("Access point", details.bssid),
        ("IP address", ", ".join(details.addresses)),
        ("Gateway", details.gateway),
        ("DNS", ", ".join(details.dns)),
        ("IPv6", ", ".join(details.ipv6)),
        ("Device", f"{details.device} ({details.mac})" if details.mac else details.device),
    ]
    return [(label, value) for label, value in rows if value]


class DetailsScreen(ShareTabsScreen):
    """The connection in use, in two tabs, its details and its password, and a QR code to join it from a phone."""

    def __init__(self, details: Details) -> None:
        super().__init__(details.ssid, details.uuid)
        self.details = details

    def panes(self) -> ComposeResult:
        with TabPane("Details", id="details"):
            for label, value in detail_rows(self.details):
                with Horizontal(classes="details-row"):
                    yield Static(label, classes="details-label")
                    yield Static(value, classes="details-value", markup=False)
        yield from super().panes()
