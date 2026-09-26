import contextlib
import io
import unittest
from unittest.mock import patch

from outils import remote
from outils.__main__ import main


class MainTest(unittest.TestCase):
    def test_version_prints_and_exits(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertTrue(output.getvalue().startswith("outils "))

    def test_the_mode_comes_from_the_command_line_and_defaults_to_the_calendar(self) -> None:
        with (
            patch("outils.__main__.start", side_effect=lambda name, make_app: make_app()) as start,
            patch("outils.__main__.OutilsApp") as app,
        ):
            main([])
            main(["time"])
            main(["weather"])
            main(["ip"])
            main(["dropbox"])
            main(["sound"])
            main(["wifi"])
            main(["life"])
            main(["snake"])
        self.assertEqual([call.args for call in app.call_args_list], [("calendar",), ("time",), ("weather",), ("ip",), ("dropbox",), ("sound",), ("wifi",), ("life",), ("snake",)])
        self.assertEqual(start.call_args.args[0], "outils")
        # The one started listens for `outils --show`
        self.assertEqual(app.call_args.kwargs, {"socket_path": remote.SOCKET})

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["sun"])
        self.assertEqual(raised.exception.code, 2)

    def test_show_asks_the_outils_running_and_starts_none(self) -> None:
        with (
            patch("outils.__main__.start") as start,
            patch("outils.__main__.remote.show", return_value=2) as show,
            self.assertRaises(SystemExit) as raised,
        ):
            main(["weather", "--show"])
        show.assert_called_once_with("weather")
        start.assert_not_called()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
