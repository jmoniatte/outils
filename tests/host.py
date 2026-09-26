"""An app that shows one view alone, for the tests of a view."""

from textual.app import App, ComposeResult
from textual.widget import Widget
from tui_kit.header_notification import HeaderNotification
from tui_kit.theme import load_palette

from outils.app import MODES, load_stylesheet

MODE_VIEWS = {view for _, view in MODES.values()}


class Host(App):
    """view in outils's styles and onedark's colors, as when its tab shows: padded if it is a tab's
    view, focused if it can take focus. The messages it would show are kept in messages."""

    CSS = load_stylesheet()
    AUTO_FOCUS = None

    def __init__(self, view: Widget) -> None:
        super().__init__()
        self.view = view.add_class("mode") if type(view) in MODE_VIEWS else view
        self.messages: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield self.view

    def on_mount(self) -> None:
        if self.view.can_focus:
            self.view.focus()

    def notify(self, message, **kwargs) -> None:
        self.messages.append(message)


async def settle(app: App, pilot) -> None:
    """Wait for the workers the view started, those they started in turn, and for what they show."""
    while True:
        await pilot.pause()
        if not any(worker.is_running for worker in app.workers):
            break
        await app.workers.wait_for_complete()
    await pilot.pause()


def footer_message(app: App) -> str:
    """The message the footer shows, empty when none does."""
    notification = app.screen.query_one(HeaderNotification)
    return notification.render().plain if notification.display else ""
