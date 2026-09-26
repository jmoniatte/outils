import asyncio

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TabbedContent, TabPane, Tabs
from tui_kit.panel import PanelScreen
from tui_kit.shortcuts import ACTIONS

from .. import nmcli
from ..click_only import click_only
from ..nmcli import Network, NmcliError, Share
from .qr_screen import QrScreen


class ShareTabsScreen(PanelScreen):
    """A panel titled with a network's name, with a Password tab, and a QR code button in it, for one saved profile.

    The password is only read from NetworkManager the first time either is asked for. The code
    opens alone over the whole window (QrScreen): in the panel, it needed a tall window.
    """

    BINDINGS = [
        Binding("p", "show_tab('password')", "Show password", group=ACTIONS),
        Binding("c", "show_qr", "Show QR code", group=ACTIONS),
        # Nothing here needs focus but the Close button, so tab is free to switch tabs
        Binding("tab", "next_tab", "Switch tab", show=False),
    ]

    def __init__(self, ssid: str, uuid: str) -> None:
        super().__init__()
        self.ssid = ssid
        self.uuid = uuid
        self._loaded = False
        # What NetworkManager gave, once read
        self.shared: Share | None = None
        # The QR code was asked for before the password was read: it opens once it is
        self._qr_asked = False

    def compose(self) -> ComposeResult:
        with Vertical(id="network-panel"):
            yield Static(self.ssid, id="dialog-title", markup=False)
            yield Static("", id="title-separator")
            with TabbedContent(id="network-tabs"):
                yield from self.panes()
            yield Static("", id="panel-footer-spacer")
            with Horizontal(id="panel-footer"):
                yield Button("Close", id="btn-close")

    def panes(self) -> ComposeResult:
        """The tabs, the first one open; a subclass adds its own before the Password tab."""
        with TabPane("Password", id="password"):
            with Horizontal(classes="details-row"):
                yield Static("Password", classes="details-label")
                yield Static("Reading...", classes="details-value share-password", markup=False)
            # Focus would draw its label reversed, a second background, once the code closes; c is its key
            yield click_only(Button("QR code", id="btn-qr"))

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
        if event.pane.id == "password":
            self._load_share()

    @on(Button.Pressed, "#btn-qr")
    def action_show_qr(self) -> None:
        if self.shared is None:
            self._qr_asked = True
            self._load_share()
        else:
            self._open_qr()

    def _open_qr(self) -> None:
        if self.shared.enterprise:
            self.app.notify("No QR code: this network signs in with 802.1X, which a QR code cannot carry")
        else:
            self.app.push_screen(QrScreen(self.shared))

    def _load_share(self) -> None:
        """Read the password once; after a failure the next call tries again."""
        if not self._loaded:
            self._loaded = True
            self._read()

    @work(exclusive=True)
    async def _read(self) -> None:
        password = self.query_one(".share-password", Static)
        try:
            shared = await asyncio.to_thread(nmcli.share, self.uuid)
        except NmcliError as error:
            self._loaded = False
            self._qr_asked = False
            password.update(str(error))
            self.app.notify(str(error), severity="error")
            return
        self.shared = shared
        if shared.enterprise:
            password.update("none: this network signs in with 802.1X")
        else:
            password.update(shared.password or "none (open network)")
        if self._qr_asked:
            self._qr_asked = False
            self._open_qr()


class ShareScreen(ShareTabsScreen):
    """A saved network that is not in use: its password, read as the panel opens, and QR code, without connection details."""

    def __init__(self, network: Network) -> None:
        super().__init__(network.ssid, network.saved_uuid)
