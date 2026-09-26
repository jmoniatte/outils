from collections.abc import Iterable

from rich.style import Style
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Input, Static

# Between a label and its value
GAP = 2


class LookupBox(Input):
    """A box to type what a tab looks up: the time's epoch, the weather's city, the IP's address.

    What was found replaces the text, in full and in blue (the -found class), until the box is
    clicked. It lets go of focus after Enter, which the tab handles, or Escape.
    """

    BINDINGS = [
        # Only reached while the box has focus; otherwise Escape quits, as everywhere
        Binding("escape", "leave", show=False),
    ]

    def on_focus(self) -> None:
        # Typing: plain text again, the blue is for what was found
        self.remove_class("-found")

    def on_input_submitted(self) -> None:
        # Before the tab sees it, so ?, t and q work again whatever the tab does with it
        self.screen.set_focus(None)

    def show_found(self, text: str) -> None:
        self.value = text
        self.cursor_position = 0
        self.add_class("-found")

    def action_leave(self) -> None:
        self.screen.set_focus(None)


def lookup_row(label: str, box: LookupBox, *beside: Widget, label_width: int | None = None) -> Horizontal:
    """The label, the box, then what goes beside it; label_width lines the box up with LookupDetails' values."""
    name = Static(label, classes="lookup-label")
    name.styles.width = label_width or len(label) + GAP
    return Horizontal(name, box, *beside, classes="lookup-row")


class LookupDetails(Widget):
    """What the box found, a row per label and value, the values lined up; or why it found nothing, in red.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"lookup--label", "lookup--message", "lookup--error"}

    def __init__(self, labels: Iterable[str], message: str = "", *, id: str) -> None:
        super().__init__(id=id)
        self.label_width = max(len(label) for label in labels) + GAP
        # Shown, dim, until there are rows
        self.message = message
        self.rows: list[tuple[str, str]] = []
        self.error = ""

    def show(self, rows: list[tuple[str, str]], error: str = "") -> None:
        self.rows = rows
        self.error = error
        self.refresh(layout=True)

    def value_style(self, index: int) -> Style | str:
        return ""

    def render(self) -> Text:
        if self.error:
            return Text(self.error, style=self.get_component_rich_style("lookup--error"))
        if not self.rows:
            return Text(self.message, style=self.get_component_rich_style("lookup--message"))
        text = Text()
        for index, (label, value) in enumerate(self.rows):
            if index:
                text.append("\n")
            text.append(f"{label:<{self.label_width}}", style=self.get_component_rich_style("lookup--label"))
            text.append(value, style=self.value_style(index))
        return text
