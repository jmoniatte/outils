import asyncio
import os
import subprocess
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from textual.app import App, ComposeResult

from outils.app import load_stylesheet
from outils.config import Config
from outils.dropbox import MISSING, RUNNING, STOPPED, DropboxError, RecentFile, folder, recent, start, state, status, stop
from outils.widgets import DropboxView
from outils.widgets.dropbox_view import RecentFiles
from ouikit.theme import load_palette


class DropboxTest(unittest.TestCase):
    def test_state_reads_what_the_client_says(self):
        self.assertEqual(state(None), MISSING)
        self.assertEqual(state("Dropbox isn't running!"), STOPPED)
        self.assertEqual(state("Up to date"), RUNNING)
        self.assertEqual(state("Syncing 3 files\nUploading 'a.txt'..."), RUNNING)

    def test_status_is_the_command_output_or_none_when_it_is_missing(self):
        done = subprocess.CompletedProcess([], 0, stdout="Up to date\n", stderr="DeprecationWarning")
        with patch("outils.dropbox.subprocess.run", return_value=done) as run:
            self.assertEqual(status(), "Up to date")
        self.assertEqual(run.call_args.args[0], ["dropbox", "status"])
        with patch("outils.dropbox.subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(status())
        with patch("outils.dropbox.subprocess.run", side_effect=subprocess.TimeoutExpired("dropbox", 10)):
            with self.assertRaisesRegex(DropboxError, "did not answer"):
                status()

    def test_start_gives_the_daemon_no_pipe_to_hold(self):
        with patch("outils.dropbox.subprocess.run") as run:
            start()
        self.assertEqual(run.call_args.args[0], ["dropbox", "start"])
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs["start_new_session"])
        with patch("outils.dropbox.subprocess.run", side_effect=subprocess.TimeoutExpired("dropbox", 90)):
            with self.assertRaisesRegex(DropboxError, "did not start"):
                start()

    def test_stop_waits_until_the_daemon_is_gone(self):
        answers = iter(["Up to date", "Up to date", "Dropbox isn't running!"])
        with (
            patch("outils.dropbox._run") as run,
            patch("outils.dropbox.status", side_effect=lambda: next(answers)),
            patch("outils.dropbox.time.sleep") as sleep,
        ):
            stop()
        run.assert_called_once_with("stop")
        self.assertEqual(sleep.call_count, 2)
        with (
            patch("outils.dropbox._run"),
            patch("outils.dropbox.status", return_value="Up to date"),
            patch("outils.dropbox.time.sleep"),
            patch("outils.dropbox.time.monotonic", side_effect=[0, 10, 31]),
            self.assertRaisesRegex(DropboxError, "did not stop"),
        ):
            stop()

    def test_folder_comes_from_the_client_info_or_defaults_to_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / "info.json"
            info.write_text('{"personal": {"path": "/data/Dropbox"}}')
            self.assertEqual(folder(info), Path("/data/Dropbox"))
            info.write_text("{}")
            self.assertEqual(folder(info), Path.home() / "Dropbox")
            self.assertEqual(folder(Path(tmp) / "none.json"), Path.home() / "Dropbox")

    def test_recent_lists_the_latest_files_first_and_skips_the_client_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, name in enumerate(("old.txt", "notes/new.md", "notes/deep/mid.pdf", ".dropbox.cache/tmp", ".dropbox")):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x")
                os.utime(path, (1000 + index, 1000 + index))
            files = recent(root, count=2)
            self.assertEqual([file.name for file in files], ["notes/deep/mid.pdf", "notes/new.md"])
            self.assertEqual(files[0].path, root / "notes/deep/mid.pdf")
            self.assertEqual(files[0].modified, datetime.fromtimestamp(1002, UTC))
            self.assertEqual(len(recent(root)), 3)
            self.assertEqual(recent(root / "missing"), [])


class Host(App):
    CSS = load_stylesheet()
    AUTO_FOCUS = None

    def __init__(self, view: DropboxView) -> None:
        super().__init__()
        self.view = view
        self.messages: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**super().get_css_variables(), **load_palette("onedark")}

    def compose(self) -> ComposeResult:
        yield self.view

    def on_mount(self) -> None:
        self.view.focus()

    def notify(self, message, **kwargs) -> None:
        self.messages.append(message)


def files(now: datetime) -> list[RecentFile]:
    names = ("notes/today.md", "Camera Uploads/photo.jpg", "old.txt")
    ages = (timedelta(minutes=3), timedelta(hours=5), timedelta(days=2))
    return [RecentFile(Path("/box") / name, name, now - age) for name, age in zip(names, ages)]


def many_files(now: datetime) -> list[RecentFile]:
    return [RecentFile(Path(f"/box/file{index}.txt"), f"file{index}.txt", now - timedelta(minutes=index)) for index in range(20)]


class DropboxViewTest(unittest.TestCase):
    def run_view(self, body, said="Up to date", many=False):
        async def main():
            now = datetime.now(UTC)
            with (
                patch("outils.widgets.dropbox_view.status", return_value=said) as self.status,
                patch("outils.widgets.dropbox_view.recent", return_value=many_files(now) if many else files(now)),
                patch("outils.widgets.dropbox_view.open_file") as self.open_file,
                patch("outils.widgets.dropbox_view.start") as self.start,
                patch("outils.widgets.dropbox_view.stop") as self.stop,
            ):
                app = Host(DropboxView(Config(), root=Path("/box")))
                async with app.run_test(size=(80, 20)) as pilot:
                    await self.settle(app, pilot)
                    await body(app, pilot)

        asyncio.run(main())

    async def settle(self, app, pilot):
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

    def test_shows_stop_and_the_latest_files_and_opens_the_one_selected(self):
        async def body(app, pilot):
            self.assertFalse(app.query_one("#dropbox-state").display)
            toggle = app.query_one("#btn-dropbox-toggle")
            self.assertTrue(toggle.visible)
            self.assertEqual(str(toggle.label), "Stop Dropbox")
            self.assertEqual(toggle.styles.color.hex.lower(), app.get_css_variables()["red"].lower())
            self.assertIn("Quits the Dropbox app", toggle.tooltip)
            lines = app.query_one(RecentFiles).render().plain.split("\n")
            self.assertEqual([line.rstrip() for line in lines], [
                "3 minutes ago   notes/today.md",
                "5 hours ago     Camera Uploads/photo.jpg",
                "2 days ago      old.txt",
            ])
            # Down past the last file stays on it; Enter opens it
            await pilot.press("down", "down", "down", "enter")
            self.open_file.assert_called_once_with(Path("/box/old.txt"))
            await pilot.press("up")
            self.assertEqual(app.query_one(RecentFiles).selected.name, "Camera Uploads/photo.jpg")
            # The mouse selects the row under it, which stays selected when it leaves
            rows = app.query_one(RecentFiles)
            await pilot.hover(RecentFiles, offset=(2, 2))
            await pilot.pause()
            self.assertEqual(rows.cursor, 2)
            await pilot.hover("#btn-dropbox-toggle")
            await pilot.pause()
            self.assertEqual(rows.cursor, 2)
            # A click opens the file under the mouse, once even in a double click
            self.open_file.reset_mock()
            await pilot.click(RecentFiles, offset=(2, 0), times=2)
            await pilot.pause()
            self.open_file.assert_called_once_with(Path("/box/notes/today.md"))
            self.assertEqual(rows.cursor, 0)
            self.assertEqual(app.screen.selections, {})

        self.run_view(body)

    def test_stop_then_start_run_the_command_and_the_state_follows(self):
        async def body(app, pilot):
            label = app.query_one("#dropbox-state")
            toggle = app.query_one("#btn-dropbox-toggle")
            # While dropbox stop runs: "Stopping..." in red in place of the button
            release = threading.Event()
            self.stop.side_effect = lambda: release.wait(5)
            self.status.return_value = "Dropbox isn't running!"
            await pilot.click("#btn-dropbox-toggle")
            await pilot.pause()
            self.assertEqual(str(label.render()), "Stopping...")
            self.assertTrue(label.display)
            self.assertEqual(label.styles.color.hex.lower(), app.get_css_variables()["red"].lower())
            self.assertFalse(toggle.display)
            release.set()
            await self.settle(app, pilot)
            self.stop.assert_called_once()
            self.assertFalse(label.display)
            self.assertTrue(toggle.display)
            self.assertEqual(str(toggle.label), "Start Dropbox")
            self.assertEqual(toggle.styles.color.hex.lower(), app.get_css_variables()["green"].lower())
            # And "Starting..." in green
            self.start.side_effect = lambda: release.wait(5)
            release.clear()
            await pilot.click("#btn-dropbox-toggle")
            await pilot.pause()
            self.assertEqual(str(label.render()), "Starting...")
            self.assertEqual(label.styles.color.hex.lower(), app.get_css_variables()["green"].lower())
            release.set()
            await self.settle(app, pilot)
            self.start.side_effect = DropboxError("Dropbox did not start")
            await pilot.click("#btn-dropbox-toggle")
            await self.settle(app, pilot)
            self.assertEqual(self.start.call_count, 2)
            self.assertEqual(app.messages, ["Dropbox did not start"])
            self.assertFalse(label.display)
            self.assertEqual(str(toggle.label), "Start Dropbox")

        self.run_view(body)

    def test_the_list_scrolls_when_the_files_do_not_fit(self):
        async def body(app, pilot):
            scroll = app.query_one("#dropbox-scroll")
            self.assertLess(scroll.size.height, 20)
            self.assertEqual(app.query_one(RecentFiles).size.height, 20)
            self.assertTrue(scroll.show_vertical_scrollbar)
            for _ in range(19):
                await pilot.press("down")
            await pilot.pause()
            self.assertEqual(app.query_one(RecentFiles).selected.name, "file19.txt")
            self.assertEqual(scroll.scroll_y, scroll.max_scroll_y)

        self.run_view(body, many=True)

    def test_a_missing_command_says_so_and_hides_the_button(self):
        async def body(app, pilot):
            self.assertEqual(str(app.query_one("#dropbox-state").render()), "The dropbox command is not installed")
            self.assertFalse(app.query_one("#btn-dropbox-toggle").display)

        self.run_view(body, said=None)


if __name__ == "__main__":
    unittest.main()
