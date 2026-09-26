import asyncio

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TabbedContent, TabPane, Tabs

from .. import nmcli
from ..nmcli import Network, NmcliError
from ..qr import wifi_qr
from tui_kit.shortcuts import ACTIONS
from tui_kit.panel import PanelScreen

# A phone camera needs dark modules on light, whatever the theme
QR_STYLE = "#000000 on #ffffff"
SHARE_TABS = ("password", "qr")


class ShareTabsScreen(PanelScreen):
    """A panel with Password and QR code tabs for one saved profile.

    The password is only read from NetworkManager the first time one of those tabs opens.
    """

    BINDINGS = [
        Binding("p", "show_tab('password')", "Show password", group=ACTIONS),
        Binding("c", "show_tab('qr')", "Show QR code", group=ACTIONS),
        # Nothing here needs focus but the Close button, so tab is free to switch tabs
        Binding("tab", "next_tab", "Switch tab", show=False),
    ]

    def __init__(self, uuid: str) -> None:
        super().__init__()
        self.uuid = uuid
        self._loaded = False

    def share_panes(self) -> ComposeResult:
        with TabPane("Password", id="password"):
            with Horizontal(classes="details-row"):
                yield Static("Password", classes="details-label")
                yield Static("Reading...", classes="details-value share-password", markup=False)
        with TabPane("QR code", id="qr"):
            yield Static("Reading...", classes="share-qr", markup=False)

    def on_mount(self) -> None:
        self.query_one(Tabs).can_focus = False

    def action_show_tab(self, pane: str) -> None:
        self.query_one(TabbedContent).active = pane

    def action_next_tab(self) -> None:
        tabs = self.query_one(TabbedContent)
        panes = [pane.id for pane in tabs.query(TabPane)]
        tabs.active = panes[(panes.index(tabs.active) + 1) % len(panes)]

    @on(TabbedContent.TabActivated)
    def _tab_opened(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id in SHARE_TABS:
            self.load_share()

    def load_share(self) -> None:
        """Read the password once; after a failure the next call tries again."""
        if not self._loaded:
            self._loaded = True
            self._read()

    @work(exclusive=True)
    async def _read(self) -> None:
        password = self.query_one(".share-password", Static)
        qr = self.query_one(".share-qr", Static)
        try:
            shared = await asyncio.to_thread(nmcli.share, self.uuid)
        except NmcliError as error:
            self._loaded = False
            password.update(str(error))
            qr.update(str(error))
            return
        if shared.enterprise:
            password.update("none: this network signs in with 802.1X")
            qr.update("No QR code: this network signs in with 802.1X, which a QR code cannot carry")
            return
        password.update(shared.password or "none (open network)")
        qr.update(Text("\n".join(wifi_qr(shared)), style=QR_STYLE, no_wrap=True))
        qr.add_class("-code")


class ShareScreen(ShareTabsScreen):
    """A saved network that is not in use: its password and QR code, without connection details."""

    def __init__(self, network: Network) -> None:
        super().__init__(network.saved_uuid)
        self.network = network

    def compose(self) -> ComposeResult:
        with Vertical(id="share-panel"):
            yield Static(self.network.ssid, id="dialog-title", markup=False)
            yield Static("", id="title-separator")
            with TabbedContent(initial="password", id="share-tabs"):
                yield from self.share_panes()
            yield Static("", id="panel-footer-spacer")
            with Horizontal(id="panel-footer"):
                yield Button("Close", id="btn-close")

    def on_mount(self) -> None:
        super().on_mount()
        self.load_share()
