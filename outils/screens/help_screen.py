from textual.binding import Binding
from tui_kit.help_screen import HelpScreen
from tui_kit.shortcuts import SECTIONS, Shortcut


def documented(*sources) -> tuple[Shortcut, ...]:
    """The bindings Help lists, of either group, in the order they are declared."""
    return tuple(
        Shortcut(binding.key_display or binding.key, binding.description)
        for source in sources
        for binding in source
        if isinstance(binding, Binding) and binding.group in SECTIONS and binding.description
    )


class OutilsHelpScreen(HelpScreen):
    """tui-kit's Help, with the app's keys, which every tab shares, on the left, and the tab's own on
    the right under the tab's name. Both columns keep some width, so a tab with no keys of its own
    still gets a panel of a fair size.
    """

    def __init__(self, tab: str) -> None:
        super().__init__()
        self.tab = tab

    def _sections(self) -> list[tuple[str, tuple[Shortcut, ...]]]:
        return [
            ("General", documented(self.app.BINDINGS)),
            (self.tab, documented(*self.app.HELP_BINDINGS)),
        ]
