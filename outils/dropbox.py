"""The Dropbox client on this computer, through its dropbox command: its status, start and stop,
and the files that changed last in its folder. No account and no network: the command talks to
the local daemon.

The calls block; the app runs them with asyncio.to_thread.
"""

import heapq
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

COMMAND = "dropbox"
# Where the client says its folder is; ~/Dropbox when it does not say
INFO_FILE = Path.home() / ".dropbox" / "info.json"
DEFAULT_FOLDER = Path.home() / "Dropbox"
# How many of the files changed last the view lists
RECENT = 20
TIMEOUT = 10
# dropbox start waits up to a minute for the daemon
START_TIMEOUT = 90
# How long the daemon may take to quit, and how often to check
STOP_TIMEOUT = 30
STOP_CHECK = 0.5
# What the client keeps in its folder for itself: .dropbox and .dropbox.cache
PRIVATE = ".dropbox"

MISSING = "missing"
STOPPED = "stopped"
RUNNING = "running"


class DropboxError(Exception):
    """The dropbox command failed; the message says how."""


@dataclass
class RecentFile:
    path: Path
    # Relative to the Dropbox folder
    name: str
    modified: datetime


def folder(info_file: Path = INFO_FILE) -> Path:
    """The Dropbox folder, the personal one when the client names more than one."""
    try:
        info = json.loads(info_file.read_text(encoding="utf-8"))
        return Path(info["personal"]["path"])
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_FOLDER


def _run(*args: str, timeout: float = TIMEOUT) -> str:
    try:
        result = subprocess.run(
            [COMMAND, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise DropboxError(f"dropbox {' '.join(args)} did not answer") from None
    return result.stdout.strip()


def status() -> str | None:
    """What the client says it is doing, a line or more; None when the dropbox command is missing."""
    try:
        return _run("status")
    except FileNotFoundError:
        return None


def state(text: str | None) -> str:
    """MISSING, STOPPED or RUNNING, from what status gave."""
    if text is None:
        return MISSING
    if not text or "isn't running" in text:
        return STOPPED
    return RUNNING


def start() -> None:
    """Start the daemon, once it answers."""
    # No pipes: the daemon would inherit them and the call would wait on them; its own session, so it outlives the app
    try:
        subprocess.run(
            [COMMAND, "start"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=START_TIMEOUT,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        raise DropboxError("Dropbox did not start") from None


def stop() -> None:
    """Stop the daemon, once it no longer answers."""
    _run("stop")
    # dropbox stop only asks the daemon to quit, which takes a few seconds; until then it answers
    deadline = time.monotonic() + STOP_TIMEOUT
    while state(status()) != STOPPED:
        if time.monotonic() > deadline:
            raise DropboxError("Dropbox did not stop")
        time.sleep(STOP_CHECK)


def recent(root: Path, count: int = RECENT) -> list[RecentFile]:
    """The count files under root that changed last, the latest first."""
    found: list[tuple[float, str]] = []
    pending = [root]
    while pending:
        try:
            entries = os.scandir(pending.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                if entry.name.startswith(PRIVATE):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        found.append((entry.stat(follow_symlinks=False).st_mtime, entry.path))
                except OSError:
                    continue
    return [
        RecentFile(Path(path), os.path.relpath(path, root), datetime.fromtimestamp(mtime, UTC))
        for mtime, path in heapq.nlargest(count, found)
    ]


def open_file(path: Path) -> None:
    """Open path in its usual application, as a click in a file manager would."""
    subprocess.Popen(
        ["xdg-open", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
