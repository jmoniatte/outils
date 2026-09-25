"""Conway's Game of Life on a grid whose edges wrap around, so gliders come back on the other side."""

import random

Cell = tuple[int, int]

# The share of cells alive in a new grid
DENSITY = 0.3


def random_cells(width: int, height: int, rng: random.Random | None = None) -> set[Cell]:
    """The live cells, as (x, y), of a new grid filled at random."""
    rng = rng or random.Random()
    return {(x, y) for y in range(height) for x in range(width) if rng.random() < DENSITY}


def step(cells: set[Cell], width: int, height: int) -> set[Cell]:
    """The next generation: a live cell with 2 or 3 live neighbours stays, a dead one with 3 is born."""
    counts: dict[Cell, int] = {}
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    neighbour = ((x + dx) % width, (y + dy) % height)
                    counts[neighbour] = counts.get(neighbour, 0) + 1
    return {cell for cell, count in counts.items() if count == 3 or (count == 2 and cell in cells)}
