"""The game of snake on a walled grid; no Textual.

The snake moves one cell a step. Eating the food makes it one cell longer and scores a point;
running into a wall or into itself ends the game.
"""

import json
import os
import random
from collections import deque
from pathlib import Path

Cell = tuple[int, int]

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)
DIRECTIONS = {"up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}
START_LENGTH = 3
# Turns pressed faster than the snake moves wait their turn, up to this many
QUEUED_TURNS = 2
# Where the best score is kept between games
BEST_FILE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "outils" / "snake.json"


class Game:
    """One game: the snake, head first, the food, and whether it is still going."""

    def __init__(self, width: int, height: int, rng: random.Random | None = None) -> None:
        self.width = width
        self.height = height
        self.rng = rng or random.Random()
        # Across the middle, heading right, its tail to the left
        x, y = width // 2, height // 2
        self.snake: deque[Cell] = deque((x - i, y) for i in range(min(START_LENGTH, x + 1)))
        self.direction = RIGHT
        self.turns: deque[Cell] = deque()
        self.score = 0
        self.alive = True
        # Where the snake ran into a wall or itself, once it has
        self.crash: Cell | None = None
        self.food = self._place_food()

    @property
    def head(self) -> Cell:
        return self.snake[0]

    def turn(self, direction: Cell) -> None:
        """Head that way at the next free step; a turn back onto itself, or no turn at all, is ignored."""
        last = self.turns[-1] if self.turns else self.direction
        reverse = (direction[0] == -last[0] and direction[1] == -last[1])
        if direction == last or reverse or len(self.turns) >= QUEUED_TURNS:
            return
        self.turns.append(direction)

    def step(self) -> None:
        """Move one cell: eat, grow and score, or die against a wall or the snake itself."""
        if not self.alive:
            return
        if self.turns:
            self.direction = self.turns.popleft()
        x, y = self.head
        head = (x + self.direction[0], y + self.direction[1])
        eats = head == self.food
        # The tail moves out of the way unless the snake grows
        body = list(self.snake) if eats else list(self.snake)[:-1]
        if not (0 <= head[0] < self.width and 0 <= head[1] < self.height) or head in body:
            self.alive = False
            self.crash = head
            return
        self.snake.appendleft(head)
        if eats:
            self.score += 1
            self.food = self._place_food()
        else:
            self.snake.pop()

    @property
    def won(self) -> bool:
        return self.food is None

    def _place_food(self) -> Cell | None:
        """A free cell at random; None once the snake fills the grid, which wins the game."""
        taken = set(self.snake)
        free = [(x, y) for y in range(self.height) for x in range(self.width) if (x, y) not in taken]
        if not free:
            self.alive = False
            return None
        return self.rng.choice(free)


def read_best(path: Path | None = None) -> int:
    try:
        best = json.loads((path or BEST_FILE).read_text(encoding="utf-8")).get("best", 0)
    except (OSError, ValueError, AttributeError):
        return 0
    return best if isinstance(best, int) else 0


def save_best(best: int, path: Path | None = None) -> None:
    path = path or BEST_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"best": best}), encoding="utf-8")
    except OSError:
        pass  # A best score that cannot be kept only costs the record
