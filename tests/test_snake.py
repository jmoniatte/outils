import asyncio
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from outils.app import OutilsApp
from outils.config import Config
from outils.snake import DOWN, LEFT, RIGHT, UP, Game, read_best, save_best
from outils.widgets import SnakeView
from outils.widgets.snake_view import OVER, PAUSED, PLAYING, READY, SnakeBoard, score_level
from tests.host import Host
from tui_kit.theme import load_palette

COLORS = {name: value.lower() for name, value in load_palette("onedark").items()}


def game(width=10, height=6, snake=((5, 3), (4, 3), (3, 3)), food=(9, 0)):
    """A game with the snake and the food where the test wants them."""
    played = Game(width, height, random.Random(1))
    played.snake.clear()
    played.snake.extend(snake)
    played.food = food
    return played


class GameTest(unittest.TestCase):
    def test_starts_across_the_middle_heading_right_with_food_off_the_snake(self):
        played = Game(10, 6, random.Random(1))
        self.assertEqual(list(played.snake), [(5, 3), (4, 3), (3, 3)])
        self.assertEqual(played.direction, RIGHT)
        self.assertNotIn(played.food, played.snake)
        self.assertTrue(played.alive)

    def test_moves_eats_grows_and_scores(self):
        played = game(food=(6, 3))
        played.step()
        self.assertEqual(list(played.snake), [(6, 3), (5, 3), (4, 3), (3, 3)])
        self.assertEqual(played.score, 1)
        self.assertNotIn(played.food, played.snake)
        played.food = (0, 0)
        played.step()
        self.assertEqual(list(played.snake), [(7, 3), (6, 3), (5, 3), (4, 3)])
        self.assertEqual(played.score, 1)

    def test_turns_wait_their_step_and_a_turn_back_is_ignored(self):
        played = game()
        played.turn(LEFT)
        self.assertEqual(list(played.turns), [])
        # Up then left in one step: both are kept, one a step
        played.turn(UP)
        played.turn(LEFT)
        played.turn(DOWN)
        self.assertEqual(list(played.turns), [UP, LEFT])
        played.step()
        played.step()
        self.assertEqual(played.head, (4, 2))

    def test_a_wall_or_the_snake_itself_ends_the_game_but_the_tail_moving_away_does_not(self):
        played = game(snake=((9, 3), (8, 3), (7, 3)))
        played.step()
        self.assertFalse(played.alive)
        self.assertEqual(played.head, (9, 3))
        # A square: the head moves where the tail just left
        square = game(snake=((4, 3), (4, 2), (5, 2), (5, 3)))
        square.direction = RIGHT
        square.step()
        self.assertTrue(square.alive)
        biting = game(snake=((4, 3), (4, 2), (5, 2), (5, 3), (5, 4)))
        biting.direction = RIGHT
        biting.step()
        self.assertFalse(biting.alive)
        # Where it crashed, to show in red
        self.assertEqual((played.crash, biting.crash, square.crash), ((10, 3), (5, 3), None))

    def test_filling_the_board_wins(self):
        played = game(width=3, height=1, snake=((1, 0), (0, 0)), food=(2, 0))
        played.step()
        self.assertEqual((played.won, played.alive, played.score), (True, False, 1))

    def test_the_best_score_is_kept_in_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outils" / "snake.json"
            self.assertEqual(read_best(path), 0)
            save_best(12, path)
            self.assertEqual(read_best(path), 12)
            path.write_text("oops")
            self.assertEqual(read_best(path), 0)

    def test_the_score_level_by_its_share_of_the_best(self):
        levels = [score_level(score, 10) for score in (0, 4, 5, 7, 8, 9, 10, 12)]
        self.assertEqual(levels, ["-low", "-low", "-half", "-half", "-close", "-close", "-record", "-record"])
        self.assertEqual([score_level(0, 0), score_level(3, 0)], ["-record", "-record"])


def board(app) -> list[str]:
    return app.query_one(SnakeBoard).render().plain.split("\n")


def color(app, x: int, row: int) -> str:
    """The color of the character at x on the board's row."""
    text = app.query_one(SnakeBoard).render()
    width = len(text.plain.split("\n")[0]) + 1
    return next(span.style for span in text.spans if span.start <= row * width + x < span.end).color.triplet.hex.lower()


def side(app) -> list[str]:
    """What the column right of the board shows."""
    return [line.render().plain for line in app.query("#snake-side Static") if line.visible and not line.has_class("spacer")]


class SnakeViewTest(unittest.TestCase):
    def run_view(self, body):
        async def main():
            with tempfile.TemporaryDirectory() as tmp, patch("outils.snake.BEST_FILE", Path(tmp) / "snake.json"):
                self.best_file = Path(tmp) / "snake.json"
                app = Host(SnakeView(Config(), random.Random(1)))
                async with app.run_test(size=(60, 16)) as pilot:
                    await pilot.pause()
                    await body(app, pilot, app.view)

        asyncio.run(main())

    def test_starts_paused_on_the_keys_then_space_plays_and_p_pauses(self):
        async def body(app, pilot, view):
            self.assertEqual(view.state, READY)
            # The title alone on the board; the state and the prompt right of it
            lines = [line.strip("█▄▀ ") for line in board(app)]
            self.assertEqual([line for line in lines if line], ["S N A K E"])
            self.assertTrue(all(line.startswith("█") and line.endswith("█") for line in board(app)[1:-1]))
            self.assertEqual(side(app), ["Ready", "Press Space", "Best 0", "Score 0"])
            # 15 rows inside the padding, less the wall: 13 cells tall, and 4:3 of that wide
            self.assertEqual((view.game.width, view.game.height), (17, 13))
            # Right of the board: the state level with its first row inside, the score with its last
            board_region = app.query_one(SnakeBoard).region
            state = app.query_one("#snake-state").region
            self.assertEqual((state.x, state.y), (board_region.right + 3, board_region.y + 1))
            self.assertEqual(app.query_one("#snake-prompt").region.y, board_region.y + 3)
            self.assertEqual(app.query_one("#snake-score").region.y, board_region.bottom - 2)
            self.assertEqual(app.query_one("#snake-best").region.y, board_region.bottom - 3)
            head = view.game.head
            await pilot.pause(0.3)
            self.assertEqual(view.game.head, head)
            await pilot.press("space")
            self.assertEqual(view.state, PLAYING)
            await pilot.pause(0.3)
            self.assertGreater(view.game.head[0], head[0])
            # Nothing on the board once a game has started, and no prompt while it runs
            self.assertNotIn("S N A K E", "".join(board(app)))
            self.assertEqual(side(app), ["", "Best 0", "Score 0"])
            await pilot.press("p")
            self.assertEqual(view.state, PAUSED)
            paused_at = view.game.head
            await pilot.pause(0.3)
            self.assertEqual(view.game.head, paused_at)
            self.assertEqual(side(app), ["Paused", "Press Space", "Best 0", "Score 0"])
            # Each state in its color
            state = app.query_one("#snake-state")
            self.assertEqual(state.styles.color.hex.lower(), COLORS["yellow"])
            # A turn resumes it; hjkl and wasd steer like the arrows
            await pilot.press("k")
            self.assertEqual(view.state, PLAYING)
            await pilot.pause(0.2)
            self.assertLess(view.game.head[1], paused_at[1])

        self.run_view(body)

    def test_the_splash_screen_is_a_snake_shaped_like_an_s_with_the_title_and_the_food(self):
        async def body(app, pilot, view):
            lines = board(app)
            # 17 by 13 cells: the 12 by 5 picture sits 2 cells in and 4 down, its tail back to the wall
            self.assertEqual(lines[9], "█" * 17 + " " * 6 + "██" + " " * 10 + "█")
            self.assertEqual(lines[7].rstrip(" █"), "█      ██████████  S N A K E")
            # The tail green; the head, yellow, ends the S top right; the food, red, is under the title
            self.assertEqual([color(app, x, row) for x, row in ((1, 9), (21, 6), (23, 9), (19, 7))], [COLORS["green"], COLORS["yellow"], COLORS["red"], COLORS["yellow"]])

        self.run_view(body)

    def test_the_game_ends_at_a_wall_keeps_the_best_and_r_restarts(self):
        async def body(app, pilot, view):
            view.game.snake.clear()
            view.game.snake.extend([(16, 5), (15, 5), (14, 5)])
            view.game.score = 7
            await pilot.press("space")
            await pilot.pause(0.3)
            self.assertEqual(view.state, OVER)
            self.assertEqual(view.game.crash, (17, 5))
            self.assertEqual(side(app), ["Game over", "Press Space", "New best!", "Best 7", "Score 7"])
            self.assertEqual(app.query_one("#snake-state").styles.color.hex.lower(), COLORS["red"])
            # The board is left whole, for a screenshot
            self.assertEqual({line.strip("█▄▀ ") for line in board(app)}, {""})
            self.assertEqual(read_best(self.best_file), 7)
            # The score in blue: it set the record
            score = app.query_one("#snake-score")
            self.assertEqual(score.styles.color.hex.lower(), COLORS["blue"])
            # Space goes back to the splash screen with a new board, and space again starts it
            await pilot.press("space")
            self.assertEqual((view.state, view.game.score, view.game.crash), (READY, 0, None))
            self.assertIn("S N A K E", "".join(board(app)))
            self.assertEqual(side(app), ["Ready", "Press Space", "Best 7", "Score 0"])
            # A new game starts at nothing of the best: red
            self.assertEqual(score.styles.color.hex.lower(), COLORS["red"])
            await pilot.press("space")
            self.assertEqual(view.state, PLAYING)
            # r starts a new game at once, from any state
            view.game.score = 3
            await pilot.press("r")
            self.assertEqual((view.state, view.game.score), (PLAYING, 0))
            self.assertEqual(view.best, 7)

        self.run_view(body)

    def test_the_wall_the_snake_its_food_and_a_crash_in_their_colors(self):
        async def body(app, pilot, view):
            await pilot.press("space", "p")
            view.game.snake.clear()
            view.game.snake.extend([(2, 0), (1, 0), (0, 1)])
            view.game.food = (5, 1)

            def at(x, row):
                return (board(app)[row][x], color(app, x, row))

            # The wall is a character thick at the sides, half of one on top and under, hugging the board
            self.assertEqual({at(x, 0) for x in range(36)}, {("▄", COLORS["comment"])})
            self.assertEqual({at(x, 14) for x in range(36)}, {("▀", COLORS["comment"])})
            self.assertEqual([at(x, 1) for x in (0, 35)], [("█", COLORS["comment"])] * 2)
            # A cell is two characters, a character in: the body, then the head; the food under them
            self.assertEqual([at(x, 1) for x in (3, 4)], [("█", COLORS["green"])] * 2)
            self.assertEqual([at(x, 1) for x in (5, 6)], [("█", COLORS["yellow"])] * 2)
            self.assertEqual(at(1, 2), ("█", COLORS["green"]))
            self.assertEqual([at(x, 2) for x in (11, 12)], [("█", COLORS["red"])] * 2)
            # A crash into a wall shows red in it: over that cell on top, its one character at a side
            view.game.crash = (4, -1)
            self.assertEqual([at(x, 0) for x in (9, 10)], [("▄", COLORS["red"])] * 2)
            view.game.crash = (17, 3)
            self.assertEqual(at(35, 4), ("█", COLORS["red"]))

        self.run_view(body)


class SnakeModeTest(unittest.TestCase):
    def test_help_lists_its_keys_and_leaving_the_tab_pauses_the_game(self):
        async def main():
            with tempfile.TemporaryDirectory() as tmp, patch("outils.snake.BEST_FILE", Path(tmp) / "snake.json"):
                app = OutilsApp("snake", Config(theme="onedark"))
                async with app.run_test(size=(80, 24)) as pilot:
                    await pilot.pause()
                    view = app.query_one(SnakeView)
                    self.assertIs(app.focused, view)
                    await pilot.press("question_mark")
                    await pilot.pause()
                    keys = [key.render().plain for key in app.screen.query("#shortcuts-snake .shortcut-key")]
                    self.assertEqual(keys[:6], ["↑ k w", "↓ j s", "← h a", "→ l d", "p space", "r"])
                    await pilot.press("escape", "space")
                    self.assertEqual(view.state, PLAYING)
                    await pilot.press("tab")
                    await pilot.pause()
                    self.assertEqual((app.mode, view.state), ("calendar", PAUSED))

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
