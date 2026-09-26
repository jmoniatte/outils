import asyncio

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from .. import nmcli
from ..nmcli import Network, NmcliError


class PasswordScreen(ModalScreen[bool]):
    """Ask for a network's password and connect with it; stays open on a wrong password so it can be typed again.

    Returns True once connected, False when cancelled.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, network: Network) -> None:
        super().__init__()
        self.network = network

    def compose(self) -> ComposeResult:
        with Vertical(id="password-dialog"):
            yield Static(f"Connect to {self.network.ssid}", id="dialog-title", markup=False)
            yield Static(f"{self.network.security}, {self.network.band}", id="password-network")
            with Horizontal(classes="form-row"):
                yield Static("Password", classes="field-label")
                yield Input(password=True, id="password")
            yield Static("", id="password-error", markup=False)
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button("Connect", id="connect-btn")

    def on_mount(self) -> None:
        self.query_one("#password", Input).focus()

    @on(Input.Submitted)
    @on(Button.Pressed, "#connect-btn")
    def _submit(self) -> None:
        password = self.query_one("#password", Input).value
        if not password:
            self._show_error("Enter the password")
            return
        self._set_busy(True)
        self._connect(password)

    @on(Button.Pressed, "#cancel-btn")
    def action_cancel(self) -> None:
        self.workers.cancel_node(self)
        self.dismiss(False)

    @work(exclusive=True)
    async def _connect(self, password: str) -> None:
        try:
            await asyncio.to_thread(nmcli.connect, self.network, password)
        except NmcliError as error:
            self._set_busy(False)
            self._show_error(str(error))
            self.query_one("#password", Input).focus()
            return
        self.dismiss(True)

    def _set_busy(self, busy: bool) -> None:
        self.query_one("#connect-btn", Button).disabled = busy
        self.query_one("#password", Input).disabled = busy
        self.query_one("#password-error", Static).update(f"Connecting to {self.network.ssid}..." if busy else "")

    def _show_error(self, message: str) -> None:
        self.query_one("#password-error", Static).update(message)
