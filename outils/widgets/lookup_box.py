from textual.binding import Binding
from textual.widgets import Input


class LookupBox(Input):
    """A box to type what a tab looks up: the weather's city, the IP's address.

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

    def show_found(self, text: str) -> None:
        self.value = text
        self.cursor_position = 0
        self.add_class("-found")

    def action_leave(self) -> None:
        self.screen.set_focus(None)
