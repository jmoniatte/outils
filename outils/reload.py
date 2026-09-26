"""A view's reload run one at a time, for the views that poll; no Textual."""

from collections.abc import Awaitable, Callable


class Reload:
    """Runs load one at a time. A reload is never cancelled, since its thread would carry on
    anyway and its result be lost: a timer tick while one runs is skipped, and any other request
    runs it once more after, so what just changed shows."""

    def __init__(self, load: Callable[[], Awaitable[None]]) -> None:
        self._load = load
        self._running = False
        self._again = False

    @property
    def overtaken(self) -> bool:
        """Whether a request came in during this reload: what it read may be older than the change."""
        return self._again

    async def run(self, tick: bool = False) -> None:
        if self._running:
            self._again = self._again or not tick
            return
        self._running = True
        try:
            self._again = True
            while self._again:
                self._again = False
                await self._load()
        finally:
            self._running = False
