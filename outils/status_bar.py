"""Tell i3blocks to redraw its volume block, which has signal=10 and otherwise never updates."""

import subprocess

SIGNAL = "-RTMIN+10"


def refresh() -> None:
    try:
        subprocess.run(["pkill", SIGNAL, "i3blocks"], capture_output=True, timeout=2)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
