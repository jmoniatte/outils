"""Tell an outils already running which tab to show, through a Unix socket; no Textual.

A status-bar block runs `outils --show <mode>`: the exit status says whether an outils took it,
so the block knows to show that window rather than start another.
"""

import os
import socket
import tempfile
from pathlib import Path

# Per user and per login, where the system keeps such files; a private name in /tmp otherwise
SOCKET = (
    Path(os.environ["XDG_RUNTIME_DIR"]) / "outils.sock"
    if os.environ.get("XDG_RUNTIME_DIR")
    else Path(tempfile.gettempdir()) / f"outils-{os.getuid()}.sock"
)
TIMEOUT = 2

# The exit status of `outils --show`, and the answers behind them
SWITCHED = 0
NOT_RUNNING = 1
SAME = 2
ANSWERS = {"switched": SWITCHED, "same": SAME}


def show(mode: str, path: Path = SOCKET) -> int:
    """Ask the outils listening at path to show mode: SWITCHED, SAME when it already did, or NOT_RUNNING."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(TIMEOUT)
            client.connect(str(path))
            client.sendall(f"{mode}\n".encode())
            answer = client.makefile().readline().strip()
    except ConnectionRefusedError:
        # Left by an outils that did not quit cleanly
        path.unlink(missing_ok=True)
        return NOT_RUNNING
    except OSError:
        return NOT_RUNNING
    return ANSWERS.get(answer, NOT_RUNNING)


def free(path: Path = SOCKET) -> bool:
    """Whether an outils may listen at path: nothing answers there, and a file left behind is removed."""
    if not path.exists():
        return True
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(TIMEOUT)
            client.connect(str(path))
    except OSError:
        path.unlink(missing_ok=True)
        return True
    # Another outils is listening: the second one opened by hand does without
    return False
