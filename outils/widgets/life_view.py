import random

from tui_kit.shortcuts import ACTIONS
from rich.text import Text
from textual.binding import Binding
from textual.events import Resize
from textual.widget import Widget

from ..config import Config
from ..life import Cell, random_cells, step

# Steps per second
SPEED = 5
# Steps a grid may spend still or blinking before a new one replaces it
SETTLED_STEPS = 5 * SPEED
# Each character holds two cells, one over the other, so the cells come out square
BLOCKS = {(False, False): " ", (True, False): "▀", (False, True): "▄", (True, True): "█"}


class LifeView(Widget, can_focus=True):
    """Conway's Game of Life filling the tab, from a random grid.

    It runs only while its tab shows. A grid that settles, or a new size, starts a new one.
    The color comes from TCSS through the component class, so a theme change repaints it.
    """

    COMPONENT_CLASSES = {"life--cell"}

    BINDINGS = [
        Binding("r", "restart", "New grid", group=ACTIONS),
    ]

    def __init__(self, config: Config, rng: random.Random | None = None) -> None:
        super().__init__(id="life")
        self.rng = rng or random.Random()
        self.columns = 0
        self.rows = 0
        self.cells: set[Cell] = set()
        # The last two generations, to tell a still or blinking grid
        self.recent: list[set[Cell]] = []
        self.settled = 0

    def on_mount(self) -> None:
        self.timer = self.set_interval(1 / SPEED, self.advance, pause=True)

    def on_show(self) -> None:
        self.timer.resume()

    def on_hide(self) -> None:
        self.timer.pause()

    def on_resize(self, event: Resize) -> None:
        width, height = event.size.width, event.size.height * 2
        if (width, height) != (self.columns, self.rows):
            self.columns, self.rows = width, height
            self.action_restart()

    def action_restart(self) -> None:
        self.cells = random_cells(self.columns, self.rows, self.rng)
        self.recent = []
        self.settled = 0
        self.refresh()

    def advance(self) -> None:
        if not self.columns or not self.rows:
            return
        cells = step(self.cells, self.columns, self.rows)
        self.settled = self.settled + 1 if cells in self.recent else 0
        self.recent = [self.cells, *self.recent][:2]
        self.cells = cells
        if self.settled >= SETTLED_STEPS:
            self.action_restart()
        else:
            self.refresh()

    def render(self) -> Text:
        style = self.get_component_rich_style("life--cell")
        lines = []
        for top in range(0, self.rows, 2):
            lines.append("".join(BLOCKS[(x, top) in self.cells, (x, top + 1) in self.cells] for x in range(self.columns)))
        return Text("\n".join(lines), style=style, no_wrap=True)
