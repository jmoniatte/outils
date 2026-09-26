import random

from tui_kit.shortcuts import ACTIONS
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from ..config import Config
from ..snake import DIRECTIONS, Game, read_best, save_best

READY, PLAYING, PAUSED, OVER = "ready", "playing", "paused", "over"
# Characters a cell is wide: two side by side, one row tall, make a square
CELL = 2
# The board is at most this much wider than tall, in cells, as snake boards usually are
SHAPE = 4 / 3
# Columns the score and the best score take right of the board, their margin included
SIDE = 14
# Seconds a step takes: quicker with each point, down to the fastest
START_DELAY = 0.13
FASTEST_DELAY = 0.07
SPEEDUP = 0.002

TITLE = "S N A K E"
# The splash screen, in board cells: a snake shaped like an S, from its tail to its head, then
# the title right of it and the food under the title; the tail reaches back to the left wall
SPLASH_SNAKE = [
    *[(x, 4) for x in range(6)],
    (5, 3),
    *[(x, 2) for x in range(5, 0, -1)],
    (1, 1),
    *[(x, 0) for x in range(1, 9)],
    (8, 1),
]
SPLASH_TITLE = (7, 2)
SPLASH_FOOD = (9, 4)
SPLASH_SIZE = (12, 5)
# What the column right of the board says in each state; the class gives its color
STATES = {READY: "Ready", PLAYING: "", PAUSED: "Paused", OVER: "Game over"}
# How close the score is to the best, as its class, from the highest share of the best reached
SCORE_LEVELS = ((1, "-record"), (0.75, "-close"), (0.5, "-half"), (0, "-low"))


def score_level(score: int, best: int) -> str:
    """Red under half the best, orange to three quarters, yellow to the best, blue from there on;
    blue too with no best yet, as every point is then a record."""
    if best == 0:
        return "-record"
    return next(name for share, name in SCORE_LEVELS if score >= share * best)


class SnakeView(Horizontal, can_focus=True):
    """The game of snake: a walled board, 4:3 at most, then right of it the state and "Press Space"
    when the game waits for it at the top, the best score over the score at the bottom. Nothing is written on the board once
    a game has started, so a screenshot shows it whole. The best score is kept between games.

    It starts paused, on the keys to play; it pauses when its tab is left.
    """

    BINDINGS = [
        Binding("up,k,w", "turn('up')", "Up", key_display="↑ k w", group=ACTIONS),
        Binding("down,j,s", "turn('down')", "Down", key_display="↓ j s", group=ACTIONS),
        Binding("left,h,a", "turn('left')", "Left", key_display="← h a", group=ACTIONS),
        Binding("right,l,d", "turn('right')", "Right", key_display="→ l d", group=ACTIONS),
        Binding("p,space", "toggle", "Play or pause", key_display="p space", group=ACTIONS),
        Binding("r", "restart", "Restart", group=ACTIONS),
    ]

    def __init__(self, config: Config, rng: random.Random | None = None) -> None:
        super().__init__(id="snake")
        self.rng = rng or random.Random()
        self.state = READY
        self.game = Game(0, 0, self.rng)
        self.best = read_best()
        self.timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield SnakeBoard()
        with Vertical(id="snake-side"):
            yield Static("", id="snake-state")
            yield Static("Press Space", id="snake-prompt")
            yield Static("", classes="spacer")
            yield Static("New best!", id="snake-new-best")
            yield Static("", id="snake-best")
            yield Static("", id="snake-score")

    def on_mount(self) -> None:
        self._show_score()

    def on_resize(self, event: Resize) -> None:
        # As tall as there is room for, and as wide as SHAPE allows, the room left permitting
        rows = self.content_size.height - 2
        widest = (self.content_size.width - SIDE - 2) // CELL
        columns = max(1, min(round(rows * SHAPE), widest))
        # A character of wall either side
        self.query_one(SnakeBoard).styles.width = CELL * columns + 2

    def on_hide(self) -> None:
        if self.state == PLAYING:
            self._pause()

    def on_snake_board_resized(self, event: "SnakeBoard.Resized") -> None:
        # A new size is a new board: back to the start
        self.game = Game(event.columns, event.rows, self.rng)
        self._stop()
        self.state = READY
        self._redraw()

    def action_turn(self, name: str) -> None:
        if self.state == OVER:
            return
        self.game.turn(DIRECTIONS[name])
        if self.state != PLAYING:
            self._play()

    def action_toggle(self) -> None:
        if self.state == PLAYING:
            self._pause()
        elif self.state == OVER:
            # Back to the splash screen, with a new board; space again starts it
            self.game = Game(self.game.width, self.game.height, self.rng)
            self.state = READY
            self._redraw()
        else:
            self._play()

    def action_restart(self) -> None:
        self.game = Game(self.game.width, self.game.height, self.rng)
        self._stop()
        self._play()

    def _play(self) -> None:
        self.state = PLAYING
        self._redraw()
        self._schedule()

    def _pause(self) -> None:
        self._stop()
        self.state = PAUSED
        self._redraw()

    def _stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def _schedule(self) -> None:
        delay = max(FASTEST_DELAY, START_DELAY - SPEEDUP * self.game.score)
        self.timer = self.set_timer(delay, self._step)

    def _step(self) -> None:
        self.timer = None
        if self.state != PLAYING:
            return
        self.game.step()
        if not self.game.alive:
            self.state = OVER
            if self.game.score > self.best:
                self.best = self.game.score
                save_best(self.best)
        else:
            self._schedule()
        self._redraw()

    def _show_score(self) -> None:
        state = self.query_one("#snake-state", Static)
        won = self.state == OVER and self.game.won
        state.update("You win!" if won else STATES[self.state])
        for name in (*STATES, "won"):
            state.set_class(name == ("won" if won else self.state), f"-{name}")
        score = self.query_one("#snake-score", Static)
        score.update(f"Score {self.game.score}")
        level = score_level(self.game.score, self.best)
        for _, name in SCORE_LEVELS:
            score.set_class(name == level, name)
        self.query_one("#snake-best", Static).update(f"Best {self.best}")
        # Hidden, not removed, so the lines under them keep their places
        new_best = self.state == OVER and self.game.score > 0 and self.game.score == self.best
        self.query_one("#snake-new-best").visible = new_best
        self.query_one("#snake-prompt").visible = self.state != PLAYING

    def _redraw(self) -> None:
        self._show_score()
        self.query_one(SnakeBoard).refresh()


class SnakeBoard(Widget):
    """The board: a cell is two characters wide and one tall, so it comes out square; the words for
    the state on top, in the middle.

    The wall is a character thick at the sides and half of one on top and under, the half on the
    board's side, not a border: a border's line runs through the middle of its characters, so a
    snake touching it seemed not to. Where the snake crashed,
    into the wall or itself, is red.

    The colors come from TCSS through the component classes, so a theme change repaints them.
    """

    COMPONENT_CLASSES = {
        "snake--wall",
        "snake--crash",
        "snake--body",
        "snake--head",
        "snake--food",
        "snake--title",
    }

    class Resized(Message):
        """The board took a new size, in cells."""

        def __init__(self, columns: int, rows: int) -> None:
            super().__init__()
            self.columns = columns
            self.rows = rows

    def __init__(self) -> None:
        super().__init__(id="snake-board")
        self.cells = (0, 0)

    def on_resize(self, event: Resize) -> None:
        # Inside the wall, a character thick all round; a cell is two characters wide
        cells = ((self.content_size.width - 2) // CELL, self.content_size.height - 2)
        if cells != self.cells:
            self.cells = cells
            self.post_message(self.Resized(*cells))

    def _style(self, name: str) -> Style:
        return self.get_component_rich_style(f"snake--{name}")

    def _splash(self, game: Game, put, fill, right: int, bottom: int) -> None:
        """The S-shaped snake, the title and the food, or the title alone on a board too small."""
        columns, rows = SPLASH_SIZE
        if game.width < columns or game.height < rows:
            row, start = bottom // 2, max(1, (1 + right - len(TITLE)) // 2)
            for index, char in enumerate(TITLE[: right - start]):
                put(start + index, row, char, "title")
            return
        # In the middle, its tail stretched back to the left wall, like a snake coming in
        left, top = (game.width - columns) // 2, (game.height - rows) // 2
        tail = SPLASH_SNAKE[0]
        for x in range(-left, tail[0]):
            fill((left + x, top + tail[1]), "body")
        for x, y in SPLASH_SNAKE[:-1]:
            fill((left + x, top + y), "body")
        head = SPLASH_SNAKE[-1]
        fill((left + head[0], top + head[1]), "head")
        fill((left + SPLASH_FOOD[0], top + SPLASH_FOOD[1]), "food")
        x, y = SPLASH_TITLE
        for index, char in enumerate(TITLE):
            put(CELL * (left + x) + 1 + index, top + y + 1, char, "title")

    def render(self) -> Text:
        view = self.parent
        if not isinstance(view, SnakeView):
            return Text()
        game = view.game
        width, height = self.content_size.width, self.content_size.height
        # A character per column and row, as (character, style)
        grid: list[list[tuple[str, Style]]] = [[(" ", Style())] * width for _ in range(height)]

        def put(x: int, y: int, char: str, name: str) -> None:
            if 0 <= y < height and 0 <= x < width:
                grid[y][x] = (char, self._style(name))

        right, bottom = CELL * game.width + 1, game.height + 1

        def fill(cell: tuple[int, int], name: str) -> None:
            # The board starts a character in, after the wall; a cell in a side wall is its one
            # character, and in the top or bottom wall its half block
            x, y = cell
            columns = [0] if x < 0 else [right] if x >= game.width else [CELL * x + 1 + i for i in range(CELL)]
            char = "▄" if y < 0 else "▀" if y >= game.height else "█"
            for column in columns:
                put(column, y + 1, char, name)

        for x in range(right + 1):
            put(x, 0, "▄", "wall")
            put(x, bottom, "▀", "wall")
        for y in range(game.height):
            fill((-1, y), "wall")
            fill((game.width, y), "wall")
        if view.state != READY:
            for cell in game.snake:
                fill(cell, "body")
            if game.snake:
                fill(game.head, "head")
            if game.food is not None:
                fill(game.food, "food")
        if game.crash is not None:
            fill(game.crash, "crash")
        # The splash screen on the empty board before the first game; nothing once one has started
        if view.state == READY:
            self._splash(game, put, fill, right, bottom)
        text = Text(no_wrap=True, overflow="crop")
        for row, chars in enumerate(grid):
            if row:
                text.append("\n")
            for char, style in chars:
                text.append(char, style)
        return text
