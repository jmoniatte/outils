"""What the Wi-Fi tab has running in nmcli, and what may start; no Textual."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .reload import Reload


class Operations:
    """The one owner of the Wi-Fi tab's nmcli calls.

    A connection change (connect, disconnect, forget, the radio) runs one at a time, and stays in
    change until its nmcli call ends, even when whatever awaits it is cancelled: the thread carries
    on. Scans go through a Reload, so they never overlap; a timer tick is skipped while a change
    runs, and a rescan asked during a rescan is dropped.
    """

    def __init__(self, load: Callable[[bool], Awaitable[None]]) -> None:
        self._load = load
        # What changes the connection, in words ("connecting to Cafe"), or None
        self.change: str | None = None
        # While nmcli rescans, which takes around 10 seconds
        self.scanning = False
        self._rescan = False
        self._reload = Reload(self._scan)

    def start(self, change: str, call: Callable[[], Any]) -> Awaitable[Any] | None:
        """Run call in a thread as the connection change, or return None when one runs already."""
        if self.change is not None:
            return None
        self.change = change
        task = asyncio.ensure_future(asyncio.to_thread(call))
        task.add_done_callback(self._changed)
        return asyncio.shield(task)

    def _changed(self, task: asyncio.Future) -> None:
        self.change = None

    async def scan(self, rescan: bool = False, tick: bool = False) -> None:
        """Load the networks, or have the scan running load them once more after."""
        if tick and self.change is not None:
            return
        self._rescan = self._rescan or (rescan and not self.scanning)
        await self._reload.run(tick)

    async def _scan(self) -> None:
        rescan, self._rescan = self._rescan, False
        await self._load(rescan)
