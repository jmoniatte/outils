"""The commands the tabs run (pactl, bluetoothctl, nmcli), each failing with its own error; no Textual."""

import subprocess

from tui_kit import processes


def run(args: list[str], error: type[Exception], timeout: float, input: str | None = None) -> subprocess.CompletedProcess:
    """tui-kit's run, with a missing command or a timeout raised as error, with a message fit to show."""
    try:
        return processes.run(args, timeout, input=input)
    except FileNotFoundError as missing:
        raise error(f"{args[0]} is not installed") from missing
    except subprocess.TimeoutExpired as expired:
        raise error(f"{' '.join(args[:2])} timed out") from expired
