from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Center, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static

from ..nmcli import Share
from ..qr import wifi_qr

# A phone camera needs dark modules on light, whatever the theme
QR_STYLE = "#000000 on #ffffff"


class QrScreen(ModalScreen):
    """The code to join a network from a phone, alone over the whole window so a short window fits it.

    Any key or a click closes it.
    """

    def __init__(self, share: Share) -> None:
        super().__init__()
        self.share = share

    def compose(self) -> ComposeResult:
        # Each centered on its own, so the code sits over the middle of the line under it
        with Center():
            yield Static(Text("\n".join(wifi_qr(self.share)), style=QR_STYLE, no_wrap=True), id="qr-code")
        with Center():
            with Horizontal(id="qr-hint"):
                yield Static("Scan to join ")
                yield Static(Text(self.share.ssid), id="qr-ssid")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self.dismiss()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.dismiss()
