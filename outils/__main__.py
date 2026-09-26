import argparse
import sys
from collections.abc import Sequence

from tui_kit.start import start

from . import __version__, remote
from .app import DEFAULT_MODE, MODES, OutilsApp


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Everyday tools in the terminal: a calendar, clocks, the weather forecast, this computer's public IP, Dropbox's sync, the sound devices, Wi-Fi, the Game of Life or snake.")
    parser.add_argument("--version", action="version", version=f"outils {__version__}")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=list(MODES),
        default=DEFAULT_MODE,
        help=f"the tab to open on (default: {DEFAULT_MODE})",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help=(
            "ask an outils already running to show the tab, and start none: exits 0 when it switched, "
            "2 when it was on show already, 1 when no outils is running"
        ),
    )
    args = parser.parse_args(argv)
    if args.show:
        sys.exit(remote.show(args.mode))
    start("outils", lambda: OutilsApp(args.mode, socket_path=remote.SOCKET))


if __name__ == "__main__":
    main()
