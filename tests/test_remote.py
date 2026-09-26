import asyncio
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import TabbedContent

from outils import remote
from outils.app import OutilsApp
from outils.config import Config
from outils.weather import WeatherError


class RemoteTest(unittest.TestCase):
    def test_with_nothing_listening_it_says_so_and_removes_a_file_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "outils.sock"
            self.assertEqual(remote.show("weather", path), remote.NOT_RUNNING)
            self.assertTrue(remote.free(path))
            # A socket file whose outils is gone, as after a crash
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
            self.assertTrue(path.exists())
            self.assertEqual(remote.show("weather", path), remote.NOT_RUNNING)
            self.assertFalse(path.exists())

    def test_a_running_outils_switches_tabs_when_asked_and_says_when_it_already_shows_one(self):
        async def main():
            with (
                tempfile.TemporaryDirectory() as tmp,
                patch("outils.app.CONFIG_FILE", Path(tmp) / "config.yaml"),
                patch("outils.widgets.weather_view.forecast", side_effect=WeatherError("offline")),
            ):
                path = Path(tmp) / "outils.sock"
                app = OutilsApp("calendar", Config(theme="onedark"), socket_path=path)
                async with app.run_test(size=(90, 24)) as pilot:
                    await pilot.pause()
                    self.assertTrue(path.exists())
                    # A second outils finds the first one listening, and does without
                    self.assertFalse(remote.free(path))
                    # A panel open is closed on the way
                    await pilot.press("question_mark")
                    await pilot.pause()
                    self.assertEqual(len(app.screen_stack), 2)
                    self.assertEqual(await asyncio.to_thread(remote.show, "weather", path), remote.SWITCHED)
                    await pilot.pause()
                    self.assertEqual((app.mode, len(app.screen_stack)), ("weather", 1))
                    self.assertEqual(app.query_one("#modes", TabbedContent).active, "weather-mode")
                    self.assertEqual(await asyncio.to_thread(remote.show, "weather", path), remote.SAME)
                    self.assertEqual(await asyncio.to_thread(remote.show, "nowhere", path), remote.NOT_RUNNING)
                self.assertFalse(path.exists())

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
