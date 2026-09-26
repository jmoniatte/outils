from collections.abc import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from ..nmcli import Network


class PasswordScreen(ModalScreen[None]):
    """Ask for a network's password; stays open on a wrong password so it can be typed again.

    submit(network, password, dialog) runs the connect, which Cancel leaves running: nmcli cannot
    be stopped midway. It calls failed() or dismisses the dialog while it is still open.
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, network: Network, submit: Callable[[Network, str, "PasswordScreen"], None]) -> None:
        super().__init__()
        self.network = network
        self.submit = submit

    def compose(self) -> ComposeResult:
        with Vertical():
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
        self.submit(self.network, password, self)

    @on(Button.Pressed, "#cancel-btn")
    def action_cancel(self) -> None:
        self.dismiss()

    def failed(self, message: str) -> None:
        self._set_busy(False)
        self._show_error(message)
        self.query_one("#password", Input).focus()

    def _set_busy(self, busy: bool) -> None:
        self.query_one("#connect-btn", Button).disabled = busy
        self.query_one("#password", Input).disabled = busy
        self.query_one("#password-error", Static).update(f"Connecting to {self.network.ssid}..." if busy else "")

    def _show_error(self, message: str) -> None:
        self.query_one("#password-error", Static).update(message)
