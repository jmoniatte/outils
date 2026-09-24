import asyncio

from rich.text import Text
from textual import work
from textual.widget import Widget

from ..config import Config
from ..ipinfo import FIELDS, IpInfoError, fetch, rows

# The longest label and two spaces
LABEL = max(len(label) for _, label in FIELDS) + 2


class IpView(Widget):
    """This computer's public address, then where ipinfo.io places it and whose network it is on.

    It asks ipinfo.io when it mounts. The colors come from TCSS through the component classes,
    so a theme change repaints them.
    """

    COMPONENT_CLASSES = {"ip--label", "ip--address", "ip--message"}

    def __init__(self, config: Config) -> None:
        super().__init__(id="ip")
        self.rows: list[tuple[str, str]] = []
        self.message = "Asking ipinfo.io..."

    def on_mount(self) -> None:
        self.load()

    @work(exclusive=True)
    async def load(self) -> None:
        try:
            self.rows = rows(await asyncio.to_thread(fetch))
        except IpInfoError as error:
            self.message = str(error)
            self.app.notify(str(error), severity="error", timeout=10)
        self.refresh(layout=True)

    def render(self) -> Text:
        if not self.rows:
            return Text(self.message, style=self.get_component_rich_style("ip--message"))
        text = Text()
        for index, (label, value) in enumerate(self.rows):
            if index:
                text.append("\n")
            text.append(f"{label:<{LABEL}}", style=self.get_component_rich_style("ip--label"))
            # The address is what the mode is for
            text.append(value, style=self.get_component_rich_style("ip--address") if index == 0 else "")
        return text
