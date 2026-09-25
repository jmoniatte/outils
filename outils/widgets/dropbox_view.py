import asyncio
from datetime import UTC, datetime
from pathlib import Path

from ouikit.shortcuts import ACTIONS
from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Click, MouseMove
from textual.geometry import Region
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from ..config import Config
from ..dropbox import MISSING, RUNNING, STOPPED, DropboxError, RecentFile, folder, open_file, recent, start, state, status, stop
from ..epoch import relative

# Seconds between two looks at the client and the folder, while the tab shows
POLL = 2
# "59 minutes ago" and two spaces
AGE = 16
# What the client's state reads as, left of the button
STOP_TIP = "Quits the Dropbox app. Nothing syncs until you start it again."
START_TIP = "Starts the Dropbox app, which syncs what changed while it was stopped."


class DropboxView(Vertical, can_focus=True):
    """A button to stop or start the Dropbox client on this computer, then the files that changed
    last in its folder, the latest first.

    It asks the client only while its tab shows.
    """

    BINDINGS = [
        Binding("up", "move(-1)", "Previous file", key_display="↑", group=ACTIONS),
        Binding("down", "move(1)", "Next file", key_display="↓", group=ACTIONS),
        Binding("enter", "open", "Open the file", group=ACTIONS),
    ]

    def __init__(self, config: Config, root: Path | None = None) -> None:
        super().__init__(id="dropbox")
        self.root = root or folder()
        # While dropbox start or stop runs
        self.busy = False

    def compose(self) -> ComposeResult:
        # Over the list, on the right
        with Horizontal(id="dropbox-row"):
            # In place of the button while it is hidden: Starting..., Stopping..., or no dropbox command
            state_label = Static("", id="dropbox-state")
            state_label.display = False
            yield state_label
            toggle = Button("Stop Dropbox", id="btn-dropbox-toggle")
            toggle.can_focus = False  # A click must not pull focus off the list and its keys
            toggle.active_effect_duration = 0
            # Until the client has answered; hidden, not removed, so it keeps its place
            toggle.visible = False
            yield toggle
        # Scrolls when the files do not all fit
        with VerticalScroll(id="dropbox-scroll") as scroll:
            scroll.can_focus = False  # The view keeps focus for its keys
            yield RecentFiles()

    def on_mount(self) -> None:
        self.timer = self.set_interval(POLL, self.poll, pause=True)

    def on_show(self) -> None:
        self.poll()
        self.timer.resume()

    def on_hide(self) -> None:
        self.timer.pause()

    @work(exclusive=True, group="poll")
    async def poll(self) -> None:
        try:
            current = state(await asyncio.to_thread(status))
        except DropboxError:
            # Too busy to answer, so running
            current = RUNNING
        files = await asyncio.to_thread(recent, self.root)
        self.show_state(current)
        self.query_one(RecentFiles).show(files, f"No files in {self.root}")

    def show_state(self, current: str) -> None:
        if self.busy:
            return
        toggle = self.query_one("#btn-dropbox-toggle", Button)
        toggle.visible = True
        toggle.display = current != MISSING
        toggle.label = "Start Dropbox" if current == STOPPED else "Stop Dropbox"
        toggle.tooltip = START_TIP if current == STOPPED else STOP_TIP
        toggle.set_class(current == STOPPED, "-start")
        self._show_label("missing", "The dropbox command is not installed" if current == MISSING else "")

    def _show_label(self, name: str, text: str) -> None:
        """Say text in place of the button, or nothing when text is empty."""
        label = self.query_one("#dropbox-state", Static)
        label.update(text)
        label.display = bool(text)
        for other in ("missing", "starting", "stopping"):
            label.set_class(other == name, f"-{other}")

    @on(Button.Pressed, "#btn-dropbox-toggle")
    def _toggle(self, event: Button.Pressed) -> None:
        event.stop()
        if not self.busy:
            self.switch(event.button.has_class("-start"))

    @work(group="switch")
    async def switch(self, starting: bool) -> None:
        self.busy = True
        # The client says little while it starts or stops, and there is nothing to press meanwhile
        self.query_one("#btn-dropbox-toggle", Button).display = False
        self._show_label("starting" if starting else "stopping", "Starting..." if starting else "Stopping...")
        try:
            await asyncio.to_thread(start if starting else stop)
        except (DropboxError, OSError) as error:
            self.app.notify(str(error), severity="error")
        finally:
            self.busy = False
            self.poll()

    def action_move(self, delta: int) -> None:
        self.query_one(RecentFiles).move(delta)

    def action_open(self) -> None:
        selected = self.query_one(RecentFiles).selected
        if selected:
            open_file(selected.path)

    def on_recent_files_opened(self, event: "RecentFiles.Opened") -> None:
        event.stop()
        open_file(event.file.path)


class RecentFiles(Widget):
    """The files that changed last, a row each: how long ago, then the path, its folder dimmer than the name, in bold.

    One row is selected, by the arrows or the mouse over it; Enter or a click opens it. The colors
    come from TCSS through the component classes, so a theme change repaints them.
    """

    # Textual's own double click would select the text of every row
    ALLOW_SELECT = False

    COMPONENT_CLASSES = {"dropbox--age", "dropbox--folder", "dropbox--name", "dropbox--cursor", "dropbox--message"}

    class Opened(Message):
        """A file was clicked."""

        def __init__(self, file: RecentFile) -> None:
            super().__init__()
            self.file = file

    def __init__(self) -> None:
        super().__init__(id="dropbox-files")
        self.files: list[RecentFile] = []
        self.cursor = 0
        self.message = "Reading the folder..."

    def show(self, files: list[RecentFile], empty: str) -> None:
        # The same file stays selected as others come in above it
        chosen = self.selected
        self.files = files
        self.message = empty
        paths = [file.path for file in files]
        self.cursor = paths.index(chosen.path) if chosen and chosen.path in paths else min(self.cursor, len(files) - 1)
        self.cursor = max(self.cursor, 0)
        # A row per file, so the height changes with their number
        self.refresh(layout=True)

    @property
    def selected(self) -> RecentFile | None:
        return self.files[self.cursor] if self.cursor < len(self.files) else None

    def move(self, delta: int) -> None:
        if self.files:
            self.cursor = max(0, min(len(self.files) - 1, self.cursor + delta))
            self.refresh()
            # The list scrolls to keep the selected row in sight
            self.parent.scroll_to_region(Region(0, self.cursor, self.size.width, 1), animate=False)

    def on_mouse_move(self, event: MouseMove) -> None:
        # As in flotte: the selection follows the mouse, and stays when it leaves
        if event.y < len(self.files) and event.y != self.cursor:
            self.cursor = event.y
            self.refresh()

    def on_click(self, event: Click) -> None:
        # A single click opens, as in flotte; the second click of a double one does nothing more
        if event.y < len(self.files) and event.chain == 1:
            self.cursor = event.y
            self.refresh()
            self.post_message(self.Opened(self.files[event.y]))

    def render(self) -> Text:
        if not self.files:
            return Text(self.message, style=self.get_component_rich_style("dropbox--message"))
        now = datetime.now(UTC)
        age = self.get_component_rich_style("dropbox--age")
        grey = self.get_component_rich_style("dropbox--folder")
        bold = self.get_component_rich_style("dropbox--name")
        # The background alone: the selected row keeps its colors
        cursor = Style(bgcolor=self.get_component_rich_style("dropbox--cursor").bgcolor)
        lines = []
        for index, file in enumerate(self.files):
            line = Text(end="")
            line.append(f"{relative(file.modified, now):<{AGE}}", style=age)
            # Too long for a row: its start goes, so the file's own name stays
            room = max(self.size.width - AGE, 2)
            path = file.name if len(file.name) <= room else "…" + file.name[-(room - 1):]
            head, _, name = path.rpartition("/")
            if head:
                line.append(f"{head}/", style=grey)
            line.append(name, style=bold)
            if index == self.cursor:
                line.pad_right(max(0, self.size.width - line.cell_len))
                line.stylize(cursor)
            lines.append(line)
        return Text("\n", no_wrap=True).join(lines)
