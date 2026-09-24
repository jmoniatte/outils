from pathlib import Path

import ouikit
from ouikit.app_header import AppHeader
from ouikit.base_app import HELP_BINDING, THEME_BINDING, BaseApp
from ouikit.shortcuts import GENERAL
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from . import REPOSITORY_URL, __version__
from .config import CONFIG_FILE, Config, load_config
from .widgets import CalendarView, WeatherView

STYLES_DIR = Path(__file__).parent / "styles"
# ouikit's stylesheets first, so the app's own rules win where they differ
STYLE_FILES = (*ouikit.STYLE_FILES, STYLES_DIR / "outils.tcss")
# Each mode by the name given on the command line; the first one is the default
MODES = {
    "calendar": ("Calendar", CalendarView),
    "weather": ("Weather", WeatherView),
}
DEFAULT_MODE = next(iter(MODES))


def load_stylesheet() -> str:
    return "\n".join(path.read_text() for path in STYLE_FILES)


class OutilsApp(BaseApp):
    """Everyday tools, one mode per run: a calendar or the weather forecast."""

    TITLE = "outils"
    VERSION = __version__
    REPOSITORY_URL = REPOSITORY_URL
    # Nothing takes focus on its own: the weather's city box would swallow ?, t and q; the
    # calendar focuses itself for its arrow keys
    AUTO_FOCUS = None

    BINDINGS = [
        HELP_BINDING,
        THEME_BINDING,
        Binding("q", "quit", "Quit", group=GENERAL),
        # Panels and dialogs bind escape themselves, so it only quits from the mode
        Binding("escape", "quit", show=False),
    ]

    def __init__(self, mode: str = DEFAULT_MODE, config: Config | None = None) -> None:
        self.mode = mode
        self.config = config if config is not None else load_config()
        # Help lists the keys of the mode on show, then the app's own
        self.HELP_BINDINGS = (MODES[mode][1].BINDINGS,)
        self.CSS = load_stylesheet()
        super().__init__(self.config.theme, CONFIG_FILE)

    def compose(self) -> ComposeResult:
        label, view = MODES[self.mode]
        yield AppHeader(Static(label, id="mode-name"))
        yield view(self.config)

    def on_mount(self) -> None:
        for warning in self.config.warnings:
            self.notify(warning, severity="warning", timeout=10)
