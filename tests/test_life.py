import asyncio
import random
import unittest

from outils.config import Config
from outils.life import random_cells, step
from outils.widgets import LifeView
from tests.host import Host

GLIDER = {(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)}


class LifeTest(unittest.TestCase):
    def test_the_rules_and_the_edges_wrapping_around(self):
        # A blinker turns a quarter and back; a block stays
        blinker = {(1, 0), (1, 1), (1, 2)}
        self.assertEqual(step(blinker, 5, 5), {(0, 1), (1, 1), (2, 1)})
        self.assertEqual(step(step(blinker, 5, 5), 5, 5), blinker)
        block = {(0, 0), (1, 0), (0, 1), (1, 1)}
        self.assertEqual(step(block, 5, 5), block)
        # A glider moves one cell down and right every four steps, and comes back past the edge
        cells = GLIDER
        for _ in range(4 * 6):
            cells = step(cells, 6, 6)
        self.assertEqual(cells, GLIDER)
        self.assertEqual(step(set(), 6, 6), set())

    def test_a_random_grid_stays_inside_its_size(self):
        cells = random_cells(10, 4, random.Random(1))
        self.assertTrue(cells)
        self.assertTrue(all(0 <= x < 10 and 0 <= y < 4 for x, y in cells))



class LifeViewTest(unittest.TestCase):
    def run_view(self, body):
        async def main():
            app = Host(LifeView(Config(), random.Random(1)))
            async with app.run_test(size=(40, 11)) as pilot:
                await pilot.pause()
                await body(app, pilot)

        asyncio.run(main())

    def test_fills_its_space_two_cells_per_character_and_restarts(self):
        async def body(app, pilot):
            view = app.view
            # Its tab's padding takes 8 columns and a row; each row holds two cells
            self.assertEqual((view.columns, view.rows), (32, 20))
            lines = view.render().plain.split("\n")
            self.assertEqual((len(lines), {len(line) for line in lines}), (10, {32}))
            view.cells = {(0, 0), (1, 1), (2, 0), (2, 1)}
            self.assertEqual(view.render().plain.split("\n")[0][:3], "▀▄█")
            # A still grid is replaced once it has settled
            view.cells = {(0, 0), (1, 0), (0, 1), (1, 1)}
            for _ in range(30):
                view.advance()
            self.assertNotEqual(view.cells, {(0, 0), (1, 0), (0, 1), (1, 1)})
            before = view.cells
            await pilot.press("r")
            self.assertNotEqual(view.cells, before)

        self.run_view(body)


if __name__ == "__main__":
    unittest.main()
