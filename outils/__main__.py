import argparse
from collections.abc import Sequence

from ouikit.start import start

from . import __version__
from .app import DEFAULT_MODE, MODES, OutilsApp


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Everyday tools in the terminal: a calendar, clocks, the weather forecast, this computer's public IP or the Game of Life.")
    parser.add_argument("--version", action="version", version=f"outils {__version__}")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=list(MODES),
        default=DEFAULT_MODE,
        help=f"the tab to open on (default: {DEFAULT_MODE})",
    )
    args = parser.parse_args(argv)
    start("outils", lambda: OutilsApp(args.mode))


if __name__ == "__main__":
    main()
