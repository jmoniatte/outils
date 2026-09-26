"""The list's table: one row per network, colors baked into Rich text."""

from dataclasses import dataclass

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable
from tui_kit.shortcuts import ACTIONS, GENERAL

from ..nmcli import Network

# (key, width); the SSID column fits the longest SSID the standard allows
COLUMNS = (
    ("marker", 1),
    ("ssid", 32),
    ("signal", 9),
    ("security", 14),
    ("band", 7),
)
BARS = "▂▄▆█"


@dataclass(frozen=True, slots=True)
class NetworkColors:
    """The palette entries the list bakes into Rich text, where TCSS variables do not reach."""

    current: str
    dim: str
    strong: str
    fair: str
    weak: str


def signal_text(signal: int, colors: NetworkColors) -> Text:
    """Four bars, as many lit as the signal deserves, then the percentage."""
    lit = 4 if signal >= 80 else 3 if signal >= 55 else 2 if signal >= 30 else 1 if signal > 5 else 0
    color = colors.strong if signal >= 55 else colors.fair if signal >= 30 else colors.weak
    text = Text(BARS[:lit], style=color)
    text.append(BARS[lit:], style=colors.dim)
    text.append(f" {signal:>3}%")
    return text


class NetworksTable(DataTable):
    """A list of networks, the one in use drawn in the current color.

    key names the Network field that tells rows apart: ssid on Nearby, saved_uuid on Saved,
    where two profiles can share an SSID.
    """

    BINDINGS = [
        Binding("enter", "select_cursor", "Connect", show=False, group=ACTIONS),
        Binding("j", "cursor_down", "Move down", show=False, group=GENERAL),
        Binding("k", "cursor_up", "Move up", show=False, group=GENERAL),
        # Not tab, which moves between outils' own tabs; the table's rows need no left and right
        Binding("left", "switch_list", "Nearby / Saved", key_display="← →", group=GENERAL),
        Binding("right", "switch_list", show=False),
    ]

    class SwitchList(Message):
        """The user asked for the other list, Nearby or Saved."""

    def __init__(self, colors: NetworkColors, key: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._colors = colors
        self.key = key
        self.networks: list[Network] = []

    def on_mount(self) -> None:
        for key, width in COLUMNS:
            self.add_column(key, key=key, width=width)

    def set_colors(self, colors: NetworkColors) -> None:
        """Re-render the rows against a new palette; their colors are baked into Rich text."""
        self._colors = colors
        self.show(self.networks)

    def show(self, networks: list[Network]) -> None:
        """Replace the rows, keeping the cursor on the network it was on when it is still listed."""
        selected = self.selected_network()
        self.networks = networks
        self.clear()
        keys = [getattr(network, self.key) for network in networks]
        for network, key in zip(networks, keys):
            self.add_row(*self._cells(network), key=key)
        if selected is not None and getattr(selected, self.key) in keys:
            self.move_cursor(row=keys.index(getattr(selected, self.key)), animate=False)
        self._repaint(self.cursor_row)

    def watch_cursor_coordinate(self, old_coordinate: Coordinate, new_coordinate: Coordinate) -> None:
        super().watch_cursor_coordinate(old_coordinate, new_coordinate)
        if old_coordinate.row != new_coordinate.row:
            self._repaint(old_coordinate.row)
            self._repaint(new_coordinate.row)

    def _repaint(self, row: int) -> None:
        """Redraw one row, so the one under the cursor can drop its dim text."""
        # While show() refills the table, the cursor moves over rows not added yet
        if not 0 <= row < min(len(self.networks), self.row_count):
            return
        network = self.networks[row]
        for (key, _), cell in zip(COLUMNS, self._cells(network, highlighted=row == self.cursor_row)):
            self.update_cell(getattr(network, self.key), key, cell)

    def selected_network(self) -> Network | None:
        """The highlighted network, or None while the list is empty."""
        row = self.cursor_row
        return self.networks[row] if 0 <= row < len(self.networks) else None

    def _cells(self, network: Network, highlighted: bool = False) -> tuple[Text, ...]:
        # Text, not str: the table reads strings as markup, and an SSID may hold brackets
        style = f"bold {self._colors.current}" if network.in_use else ""
        # Dim text on the cursor's background is too faint to read
        dim = "" if highlighted else self._colors.dim
        if not network.in_range:
            return (
                Text(""),
                Text(network.ssid, style=dim, no_wrap=True, overflow="ellipsis"),
                Text(""),
                Text("not in range", style=dim),
                Text(""),
            )
        return (
            Text("●" if network.in_use else "", style=self._colors.current),
            Text(network.ssid, style=style, no_wrap=True, overflow="ellipsis"),
            signal_text(network.signal, self._colors),
            Text(network.security or "open", style="" if network.security else dim),
            Text(network.band, style=dim),
        )

    def action_switch_list(self) -> None:
        self.post_message(self.SwitchList())

    def _row_under(self, event: events.MouseEvent) -> int | None:
        """The row under the pointer, or None when it is not over one."""
        row = event.style.meta.get("row")
        return row if isinstance(row, int) and 0 <= row < self.row_count else None

    def on_mouse_move(self, event: events.MouseMove) -> None:
        # The highlight follows the pointer as it does with the arrow keys
        row = self._row_under(event)
        if row is not None and row != self.cursor_row:
            self.move_cursor(row=row)

    async def _on_click(self, event: events.Click) -> None:
        row = self._row_under(event)
        if row is None:
            return
        # Handled here rather than by DataTable, which only selects a row on a second click in the same cell
        event.prevent_default()
        event.stop()
        self.move_cursor(row=row)
        self.action_select_cursor()
