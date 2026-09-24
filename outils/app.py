from pathlib import Path

import ouikit
from ouikit.app_header import AppHeader
from ouikit.base_app import COPY_BINDING, HELP_BINDING, THEME_BINDING, BaseApp
from ouikit.shortcuts import GENERAL
from textual import on
from textual.actions import SkipAction
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, TabbedContent, TabPane, Tabs

from . import REPOSITORY_URL, __version__
from .config import CONFIG_FILE, Config, load_config
from .widgets import CalendarView, IpView, WeatherView

STYLES_DIR = Path(__file__).parent / "styles"
# ouikit's stylesheets first, so the app's own rules win where they differ
STYLE_FILES = (*ouikit.STYLE_FILES, STYLES_DIR / "outils.tcss")
# Each mode by the name given on the command line, as its tab; the first one is the default
MODES = {
    "calendar": ("Calendar", CalendarView),
    "weather": ("Weather", WeatherView),
    "ip": ("IP", IpView),
}
DEFAULT_MODE = next(iter(MODES))


def load_stylesheet() -> str:
    return "\n".join(path.read_text() for path in STYLE_FILES)


class OutilsApp(BaseApp):
    """Everyday tools, one tab each: a calendar, the weather forecast and this computer's public IP."""

    TITLE = "outils"
    VERSION = __version__
    REPOSITORY_URL = REPOSITORY_URL
    # Nothing takes focus on its own: the weather's city box would swallow ?, t and q; the
    # calendar gets it when its tab shows, for its arrow keys
    AUTO_FOCUS = None

    BINDINGS = [
        HELP_BINDING,
        THEME_BINDING,
        COPY_BINDING,
        # Before the screen's own tab, which would move focus; skipped under a panel or dialog
        Binding("tab", "next_mode", "Next tab", group=GENERAL, priority=True),
        Binding("q", "quit", "Quit", group=GENERAL),
        # Panels and dialogs bind escape themselves, so it only quits from the mode
        Binding("escape", "quit", show=False),
    ]

    def __init__(self, mode: str = DEFAULT_MODE, config: Config | None = None) -> None:
        self.mode = mode
        self.config = config if config is not None else load_config()
        self.CSS = load_stylesheet()
        super().__init__(self.config.theme, CONFIG_FILE)

    def compose(self) -> ComposeResult:
        yield AppHeader()
        # The panes' ids differ from their views' own (#calendar, #weather, #ip)
        with TabbedContent(initial=f"{self.mode}-mode", id="modes"):
            for name, (label, view) in MODES.items():
                with TabPane(label, id=f"{name}-mode"):
                    yield view(self.config)
        # Under every tab: a rule, then Close on the left
        with Horizontal(id="app-footer"):
            close = Button("Close", id="btn-close")
            close.can_focus = False  # A click must not pull focus off the mode and its keys
            yield close

    @on(Button.Pressed, "#btn-close")
    def _close(self, event: Button.Pressed) -> None:
        event.stop()
        self.exit()

    def on_mount(self) -> None:
        # The mode keeps focus for its keys; tabs switch by click or with tab
        self.query_one(Tabs).can_focus = False
        self._show_mode(self.query_one("#modes", TabbedContent).active_pane)
        for warning in self.config.warnings:
            self.notify(warning, severity="warning", timeout=10)

    def action_next_mode(self) -> None:
        if len(self.screen_stack) > 1:
            raise SkipAction()
        self.query_one(Tabs).action_next_tab()

    @on(TabbedContent.TabActivated, "#modes")
    def _mode_activated(self, event: TabbedContent.TabActivated) -> None:
        self._show_mode(event.pane)

    def _show_mode(self, pane: TabPane) -> None:
        self.mode = pane.id.removesuffix("-mode")
        view = pane.children[0]
        # Help lists the keys of the mode on show, then the app's own
        self.HELP_BINDINGS = (view.BINDINGS,)
        # The calendar takes focus for its arrow keys; the city box must never take it by itself
        if view.can_focus:
            view.focus()
        else:
            self.screen.set_focus(None)
