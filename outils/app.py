import asyncio
from pathlib import Path

import tui_kit
from tui_kit.header_notification import HeaderNotification
from tui_kit.base_app import COPY_BINDING, HELP_BINDING, THEME_BINDING, BaseApp
from tui_kit.shortcuts import GENERAL
from textual import on
from textual.actions import SkipAction
from textual.app import ComposeResult
from textual.binding import Binding
from textual.notifications import Notification
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Link, Static, TabbedContent, TabPane, Tabs

from . import REPOSITORY_URL, __version__, remote
from .config import CONFIG_FILE, Config, load_config, save_units
from .screens import OutilsHelpScreen
from .widgets import CalendarView, DropboxView, IpView, LifeView, SnakeView, SoundView, TimeView, WeatherView, WifiView

STYLES_DIR = Path(__file__).parent / "styles"
# tui-kit's stylesheets first, so the app's own rules win where they differ
STYLE_FILES = (*tui_kit.STYLE_FILES, STYLES_DIR / "outils.tcss")
# Each mode by the name given on the command line, as its tab; the first one is the default
MODES = {
    "calendar": ("Calendar", CalendarView),
    "time": ("Time", TimeView),
    "weather": ("Weather", WeatherView),
    "ip": ("IP", IpView),
    "sound": ("Sound", SoundView),
    "wifi": ("Wi-Fi", WifiView),
    "dropbox": ("Dropbox", DropboxView),
    "life": ("Life", LifeView),
    "snake": ("Snake", SnakeView),
}
DEFAULT_MODE = next(iter(MODES))


class FooterMessage(HeaderNotification):
    """tui-kit's messages, which find this widget wherever it is: here, in the footer, since outils
    has no title bar. Help hides while one shows, so the message ends where Help ends, on the right.
    """

    def show_notification(self, notification: Notification) -> None:
        self._show_help(False)
        super().show_notification(notification)

    def clear_notification(self) -> None:
        super().clear_notification()
        # Once the message is gone from the screen: Help sits over the end of its line, so both at once
        # would show Help over a message not yet cleared
        self.call_after_refresh(self._show_help, True)

    def _show_help(self, shown: bool) -> None:
        # Unless a new message came in meanwhile
        self.screen.query_one("#btn-help").display = shown and not self.display


def load_stylesheet() -> str:
    return "\n".join(path.read_text() for path in STYLE_FILES)


class OutilsApp(BaseApp):
    """Everyday tools, one tab each: a calendar, clocks, the weather forecast, this computer's public IP, Dropbox's sync, the sound devices, Wi-Fi, the Game of Life and snake."""

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

    def __init__(self, mode: str = DEFAULT_MODE, config: Config | None = None, socket_path: Path | None = None) -> None:
        self.mode = mode
        # Where to hear `outils --show <mode>` from a status-bar block; None, as in tests, to not listen
        self.socket_path = socket_path
        self._server: asyncio.Server | None = None
        self.config = config if config is not None else load_config()
        # The view of the tab on show, told when it hides
        self.shown_view: Widget | None = None
        self.CSS = load_stylesheet()
        super().__init__(self.config.theme, CONFIG_FILE)

    def compose(self) -> ComposeResult:
        # No title bar: the tabs say where you are, and the messages sit by the buttons at the bottom
        # The panes' ids differ from their views' own (#calendar, #time, #weather, #ip, #sound, #wifi, #dropbox, #life, #snake)
        with TabbedContent(initial=f"{self.mode}-mode", id="modes"):
            for name, (label, view) in MODES.items():
                with TabPane(label, id=f"{name}-mode"):
                    yield view(self.config)
        # Under every tab: where the tab's data comes from, if it says, then a rule, Close on the left and
        # Help on the right; a message takes Help's place while it shows
        with Vertical(id="app-footer"):
            with Horizontal(id="mode-credit"):
                yield Static("", classes="spacer")
                yield Static("", id="mode-credit-text")
                link = Link("", id="mode-credit-link")
                link.can_focus = False  # A click must not pull focus off the mode and its keys
                yield link
            with Horizontal(id="app-footer-bar"):
                for label, button_id in (("Close", "btn-close"), ("Help", "btn-help")):
                    button = Button(label, id=button_id)
                    button.can_focus = False  # A click must not pull focus off the mode and its keys
                    yield button
                yield FooterMessage()

    @on(Button.Pressed, "#btn-help")
    def _help(self, event: Button.Pressed) -> None:
        event.stop()
        self.action_help()

    def action_help(self) -> None:
        # The keys every tab shares, then this tab's own under its name
        self.push_screen(OutilsHelpScreen(MODES[self.mode][0]))

    @on(Button.Pressed, "#btn-close")
    def _close(self, event: Button.Pressed) -> None:
        event.stop()
        self.exit()

    async def on_mount(self) -> None:
        # The mode keeps focus for its keys; tabs switch by click or with tab
        self.mode_tabs.can_focus = False
        self._show_mode(self.query_one("#modes", TabbedContent).active_pane)
        for warning in self.config.warnings:
            self.notify(warning, severity="warning", timeout=10)
        if self.socket_path is not None and remote.free(self.socket_path):
            self._server = await asyncio.start_unix_server(self._show_asked, path=str(self.socket_path))

    async def on_unmount(self) -> None:
        if self._server is not None:
            self._server.close()
            self.socket_path.unlink(missing_ok=True)

    async def _show_asked(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Show the tab `outils --show <mode>` names, and answer whether it was on show already."""
        mode = (await reader.readline()).decode().strip()
        if mode in MODES:
            writer.write(f"{self.show_mode(mode)}\n".encode())
            await writer.drain()
        writer.close()

    def show_mode(self, mode: str) -> str:
        """Close any panel or dialog, then show mode's tab; "same" when it was on show already, else "switched"."""
        while len(self.screen_stack) > 1:
            self.pop_screen()
        if mode == self.mode:
            return "same"
        self.query_one("#modes", TabbedContent).active = f"{mode}-mode"
        return "switched"

    @property
    def mode_tabs(self) -> Tabs:
        """The row of outils' own tabs, not the Wi-Fi tab's Nearby and Saved."""
        return self.query_one("#modes > ContentTabs", Tabs)

    def apply_theme(self, theme_name: str) -> None:
        super().apply_theme(theme_name)
        # refresh_css only re-applies TCSS; the Wi-Fi lists bake their colors into Rich text
        for view in self.query(WifiView):
            view.set_colors()

    def on_weather_view_units_changed(self, event: WeatherView.UnitsChanged) -> None:
        save_units(event.units, CONFIG_FILE)

    def action_next_mode(self) -> None:
        if len(self.screen_stack) > 1:
            raise SkipAction()
        self.mode_tabs.action_next_tab()

    @on(TabbedContent.TabActivated, "#modes")
    def _mode_activated(self, event: TabbedContent.TabActivated) -> None:
        self._show_mode(event.pane)

    def _show_mode(self, pane: TabPane) -> None:
        self.mode = pane.id.removesuffix("-mode")
        view = pane.children[0]
        # Help lists the keys of the mode on show (a view may give more than its own), then the app's
        self.HELP_BINDINGS = getattr(view, "HELP_BINDINGS", (view.BINDINGS,))
        # Where the mode's data comes from, with a link, or a line of its own with none
        credit = getattr(view, "CREDIT", None)
        footnote = getattr(view, "footnote", None)
        self.query_one("#mode-credit").display = bool(credit or footnote)
        link = self.query_one("#mode-credit-link", Link)
        link.display = credit is not None
        label = self.query_one("#mode-credit-text", Static)
        label.set_class(not credit and bool(footnote), "-footnote")
        if credit:
            text, url = credit
            label.update(f"{text} ")
            link.text = url.removeprefix("https://")
            link.url = url
        elif footnote:
            label.update(footnote)
        # Once per switch: on mount, TabbedContent then says again that the first tab is active
        if view is self.shown_view:
            return
        # The calendar, Dropbox, Life and Snake take focus for their keys; the city box must never take it by itself
        if view.can_focus:
            view.focus()
        else:
            self.screen.set_focus(None)
        # Told here, not by Show and Hide: Textual's partial relayout does not always send Show to a pane
        # that comes back. Sound and Wi-Fi then give focus to one of their widgets
        if hasattr(self.shown_view, "tab_hidden"):
            self.shown_view.tab_hidden()
        self.shown_view = view
        if hasattr(view, "tab_shown"):
            view.tab_shown()
