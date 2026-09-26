"""The Dropbox client on this computer, through its dropbox command: its status, start and stop,
and the files that changed last in its folder. No account and no network: the command talks to
the local daemon.

The calls block, and the view runs them with asyncio.to_thread, except start and stop: those are
awaited, so quitting while one waits for the daemon does not wait for it too.
"""

import asyncio
import heapq
import json
import os
import subprocess
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tui_kit import processes

COMMAND = "dropbox"
# Where the client says its folder is; ~/Dropbox when it does not say
INFO_FILE = Path.home() / ".dropbox" / "info.json"
DEFAULT_FOLDER = Path.home() / "Dropbox"
# How many of the files changed last the view lists
RECENT = 200
TIMEOUT = 10
# dropbox start waits up to a minute for the daemon
START_TIMEOUT = 90
# How long the daemon may take to quit
STOP_TIMEOUT = 30
# How often start and stop check whether they are done
CHECK = 0.5
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


def _run(*args: str) -> str:
    # Through tui-kit, so quitting kills a call still waiting; a missing command raises FileNotFoundError
    try:
        return processes.run([COMMAND, *args], TIMEOUT).stdout.strip()
    except subprocess.TimeoutExpired:
        raise DropboxError(f"dropbox {' '.join(args)} did not answer") from None


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


async def _wait_until(done: Callable[[], Awaitable[bool]], timeout: float, failure: str) -> None:
    """Check done every CHECK seconds; DropboxError with failure once timeout has passed."""
    deadline = time.monotonic() + timeout
    while not await done():
        if time.monotonic() > deadline:
            raise DropboxError(failure)
        await asyncio.sleep(CHECK)


async def start() -> None:
    """Start the daemon, once it answers."""
    # No pipes, so not through tui-kit: the daemon would inherit them and the call would wait on them;
    # its own session, so it outlives the app
    process = subprocess.Popen(
        [COMMAND, "start"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    async def exited() -> bool:
        return process.poll() is not None

    try:
        await _wait_until(exited, START_TIMEOUT, "Dropbox did not start")
    except DropboxError:
        process.kill()
        raise


async def stop() -> None:
    """Stop the daemon, once it no longer answers."""
    await asyncio.to_thread(_run, "stop")

    # dropbox stop only asks the daemon to quit, which takes a few seconds; until then it answers
    async def stopped() -> bool:
        return state(await asyncio.to_thread(status)) == STOPPED

    await _wait_until(stopped, STOP_TIMEOUT, "Dropbox did not stop")


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
