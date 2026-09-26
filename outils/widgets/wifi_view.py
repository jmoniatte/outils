import asyncio
from datetime import datetime

from tui_kit.dialog import ConfirmDialog
from tui_kit.shortcuts import ACTIONS
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static, TabbedContent, TabPane, Tabs

from .. import nmcli
from ..config import Config
from ..nmcli import Network, NmcliError, Scan
from ..screens import DetailsScreen, PasswordScreen, ShareScreen
from .networks_table import NetworkColors, NetworksTable

TABS = (("nearby", "Nearby"), ("saved", "Saved"))
# NetworkManager rescans on its own; this only picks up what it found
REFRESH_SECONDS = 10
# A login page intercepts any plain http address; this one exists for that and never redirects to https
LOGIN_PAGE_URL = "http://neverssl.com"
# The card needs a few seconds after the radio comes on before it lists networks
WIFI_ON_DELAY = 3


class WifiView(Vertical):
    """Wi-Fi networks through nmcli, in two lists, the networks in range and the saved profiles,
    then a footer with the status and the Rescan, Disconnect and Wi-Fi buttons.

    It asks nmcli only while its tab shows.
    """

    BINDINGS = [
        Binding("r", "rescan", "Rescan", group=ACTIONS),
        Binding("d", "disconnect", "Disconnect", group=ACTIONS),
        Binding("f", "forget", "Forget network", group=ACTIONS),
        Binding("i", "details", "Connection details", group=ACTIONS),
        Binding("w", "toggle_wifi", "Wi-Fi on / off", group=ACTIONS),
        Binding("o", "login_page", "Open login page", group=ACTIONS),
    ]
    # The view's keys, the list's, then the details panel's
    HELP_BINDINGS = (BINDINGS, NetworksTable.BINDINGS, DetailsScreen.BINDINGS)

    def __init__(self, config: Config) -> None:
        super().__init__(id="wifi")
        # The SSID being joined, so a second connect or a refresh does not run over it
        self.connecting: str | None = None
        # What the footer status is made of; see _show_status
        self.wifi_on = True
        self.connectivity = "unknown"
        self.scanning = False
        # The list takes focus only while the tab shows: TabbedContent would switch to a hidden one
        self.showing = False
        self.asked = False

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="nearby", id="networks-tabs"):
            for tab_id, label in TABS:
                with TabPane(label, id=tab_id):
                    # "renderable" keeps each cell's own color on the highlighted row too
                    yield NetworksTable(
                        self.colors(),
                        id=f"{tab_id}-table",
                        cursor_type="row",
                        zebra_stripes=False,
                        show_header=False,
                        cursor_foreground_priority="renderable",
                    )
        with Horizontal(id="networks-footer"):
            yield self._button("Rescan", "btn-rescan")
            # The status takes the time's place whenever there is something to say
            yield Static("", id="networks-scanned")
            yield Static("", id="networks-status")
            # The buttons that cut the connection stand apart on the right
            yield Static("", id="networks-footer-spacer")
            yield self._button("Disconnect", "btn-disconnect")
            yield self._button("Wi-Fi off", "btn-wifi")

    @staticmethod
    def _button(label: str, button_id: str) -> Button:
        button = Button(label, id=button_id)
        button.can_focus = False  # A click must not pull focus off the list
        return button

    def on_mount(self) -> None:
        # The tables keep focus; the lists switch by click or with the arrows
        self.query_one(Tabs).can_focus = False
        self.timer = self.set_interval(REFRESH_SECONDS, self._refresh, pause=True)

    def tab_shown(self) -> None:
        """The tab shows: focus on the list, and ask nmcli until it hides."""
        self.showing = True
        self.table.focus()
        # The first time, a fresh scan; later, what NetworkManager found meanwhile
        self.load_networks(rescan=not self.asked)
        self.asked = True
        self.timer.resume()

    def tab_hidden(self) -> None:
        self.showing = False
        self.timer.pause()

    # -- the lists

    def colors(self) -> NetworkColors:
        palette = self.app.palette
        return NetworkColors(
            current=palette["green"],
            dim=palette["comment"],
            strong=palette["green"],
            fair=palette["yellow"],
            weak=palette["red"],
        )

    def set_colors(self) -> None:
        """Repaint the lists after a theme change: they bake their colors into Rich text."""
        for table in self.query(NetworksTable):
            table.set_colors(self.colors())

    @property
    def table(self) -> NetworksTable:
        """The table of the list on show."""
        return self.query_one(f"#{self.query_one(TabbedContent).active}-table", NetworksTable)

    def show(self, scan: Scan) -> None:
        tabs = self.query_one(TabbedContent)
        for tab_id, label in TABS:
            networks = getattr(scan, tab_id)
            self.query_one(f"#{tab_id}-table", NetworksTable).show(networks)
            tabs.get_tab(tab_id).label = f"{label} ({len(networks)})"

    def set_wifi(self, on: bool) -> None:
        """Red to turn the radio off, green to turn it on; rescanning and disconnecting need it on."""
        button = self.query_one("#btn-wifi", Button)
        button.label = "Wi-Fi off" if on else "Wi-Fi on"
        button.set_class(on, "-off")
        button.set_class(not on, "-on")
        self.query_one("#btn-rescan").display = on
        self.query_one("#btn-disconnect").display = on
        self.query_one("#networks-status").set_class(not on, "-first")

    def set_status(self, text: str, warning: bool = False) -> None:
        status = self.query_one("#networks-status", Static)
        status.update(text)
        status.display = bool(text)
        status.set_class(warning, "-warning")
        self.query_one("#networks-scanned").display = not text

    def set_scanned(self, text: str) -> None:
        self.query_one("#networks-scanned", Static).update(text)

    def selected_network(self) -> Network | None:
        return self.table.selected_network()

    @on(NetworksTable.SwitchList)
    def _switch_list(self, event: NetworksTable.SwitchList) -> None:
        event.stop()
        tabs = self.query_one(TabbedContent)
        tabs.active = "saved" if tabs.active == "nearby" else "nearby"

    @on(TabbedContent.TabActivated, "#networks-tabs")
    def _focus_table(self, event: TabbedContent.TabActivated) -> None:
        # Not outils' own tabs: those are the app's
        event.stop()
        if self.showing:
            self.table.focus()

    @on(DataTable.RowSelected)
    def _connect_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        network = self.selected_network()
        if network is None:
            return
        # The Saved list is for sharing; connecting is done from Nearby
        if self.query_one(TabbedContent).active == "saved" and not network.in_use:
            self.app.push_screen(ShareScreen(network))
        else:
            self._connect_requested(network)

    @on(Button.Pressed, "#btn-rescan")
    def action_rescan(self) -> None:
        self.load_networks(rescan=True)

    @on(Button.Pressed, "#btn-wifi")
    def action_toggle_wifi(self) -> None:
        if not self._still_connecting():
            self._toggle_wifi()

    @on(Button.Pressed, "#btn-disconnect")
    def action_disconnect(self) -> None:
        if not self._still_connecting():
            self._disconnect()

    def action_login_page(self) -> None:
        if self.connectivity == "portal":
            self.app.open_url(LOGIN_PAGE_URL)
        else:
            self.app.notify("This network does not ask for a login page")

    def action_details(self) -> None:
        self._show_details()

    def action_forget(self) -> None:
        network = self.selected_network()
        if network is None or self._still_connecting():
            return
        if not network.saved:
            self.app.notify(f"{network.ssid} is not saved")
            return
        dialog = ConfirmDialog(
            f"Forget {network.ssid}? Its password is deleted, so connecting again asks for it.",
            title="Forget network",
            confirm_label="Forget",
            cancel_label="Cancel",
        )
        self.app.push_screen(dialog, callback=lambda confirmed: self._forget(network) if confirmed else None)

    # -- nmcli

    def _refresh(self) -> None:
        # A slow rescan must not be cancelled by the quick refresh
        scanning = any(worker.group == "wifi-scan" and worker.is_running for worker in self.app.workers)
        if self.connecting is None and not scanning:
            self.load_networks()

    @work(exclusive=True, group="wifi-scan")
    async def load_networks(self, rescan: bool = False) -> None:
        """Show what NetworkManager last saw; with rescan, then wait the few seconds a fresh scan takes and show that."""
        try:
            self.wifi_on = await asyncio.to_thread(nmcli.wifi_enabled)
            if not self.wifi_on:
                self.show(Scan([], []))
                self._show_status()
                return
            self.connectivity = await asyncio.to_thread(nmcli.connectivity)
            self._show_scan(await asyncio.to_thread(nmcli.scan))
            if rescan:
                self.scanning = True
                self._show_status()
                try:
                    scan = await asyncio.to_thread(nmcli.scan, True)
                finally:
                    # Not redrawn here: cancelled as the app quits, the view may be gone
                    self.scanning = False
                self._show_scan(scan)
        except NmcliError as error:
            self.set_status("Scan failed")
            self.app.notify(str(error), severity="error")

    def _show_scan(self, scan: Scan) -> None:
        self.show(scan)
        self._show_status()
        self.set_scanned(f"{datetime.now():%H:%M:%S}")

    def _show_status(self) -> None:
        """The one thing worth saying in the footer, most urgent first; the list labels hold the counts."""
        self.set_wifi(self.wifi_on)
        if self.connecting is not None:
            self.set_status(f"Connecting to {self.connecting}...")
        elif not self.wifi_on:
            self.set_status("Wi-Fi is off", warning=True)
        elif self.connectivity == "portal":
            self.set_status("Login page required: press o", warning=True)
        elif self.connectivity == "limited":
            self.set_status("No internet access", warning=True)
        else:
            self.set_status("Scanning..." if self.scanning else "")

    def _connect_requested(self, network: Network) -> None:
        if self._still_connecting():
            return
        if network.in_use:
            self._show_details()
        elif network.saved or network.open:
            self._connect(network)
        elif network.enterprise:
            self.app.notify(
                f"{network.ssid} needs 802.1X, which outils cannot set up; use nm-connection-editor",
                severity="warning",
            )
        else:
            self.app.push_screen(PasswordScreen(network), callback=lambda joined: self._password_done(network, joined))

    @work(exclusive=True, group="wifi-connect")
    async def _toggle_wifi(self) -> None:
        on = not self.wifi_on
        try:
            await asyncio.to_thread(nmcli.set_wifi, on)
        except NmcliError as error:
            self.app.notify(str(error), severity="error")
            return
        self.app.notify("Wi-Fi turned on" if on else "Wi-Fi turned off")
        self.load_networks()
        if on:
            self.set_timer(WIFI_ON_DELAY, self.load_networks)

    @work(exclusive=True, group="wifi-details")
    async def _show_details(self) -> None:
        try:
            details = await asyncio.to_thread(nmcli.details)
        except NmcliError as error:
            self.app.notify(str(error), severity="error")
            return
        if details is None:
            self.app.notify("Not connected to Wi-Fi")
        else:
            self.app.push_screen(DetailsScreen(details))

    def _still_connecting(self) -> bool:
        """Warn and say so when a connect is running; nothing else may change the connection meanwhile."""
        if self.connecting is not None:
            self.app.notify(f"Still connecting to {self.connecting}", severity="warning")
        return self.connecting is not None

    def _password_done(self, network: Network, joined: bool) -> None:
        if joined:
            self.app.notify(f"Connected to {network.ssid}")
        self.load_networks()

    @work(exclusive=True, group="wifi-connect")
    async def _connect(self, network: Network) -> None:
        self.connecting = network.ssid
        self._show_status()
        try:
            await asyncio.to_thread(nmcli.connect, network)
        except NmcliError as error:
            hint = ". Press f to forget it and enter the password again" if network.saved else ""
            self.app.notify(f"Could not connect to {network.ssid}: {error}{hint}", severity="error", timeout=10)
        else:
            self.app.notify(f"Connected to {network.ssid}")
        finally:
            self.connecting = None
        self.load_networks()

    @work(exclusive=True, group="wifi-connect")
    async def _disconnect(self) -> None:
        try:
            name = await asyncio.to_thread(nmcli.disconnect)
        except NmcliError as error:
            self.app.notify(str(error), severity="error")
            return
        self.app.notify(f"Disconnected from {name}" if name else "Not connected to Wi-Fi")
        self.load_networks()

    @work(exclusive=True, group="wifi-connect")
    async def _forget(self, network: Network) -> None:
        try:
            await asyncio.to_thread(nmcli.forget, network)
        except NmcliError as error:
            self.app.notify(str(error), severity="error")
            return
        self.app.notify(f"Forgot {network.ssid}")
        self.load_networks()
