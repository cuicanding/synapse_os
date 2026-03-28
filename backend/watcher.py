"""File watcher for SynapseOS data changes."""
import asyncio
from pathlib import Path
from watchfiles import awatch
from typing import Callable, Awaitable


class DataWatcher:
    """Watch data directory for changes and trigger callbacks."""

    def __init__(self, data_path: str = "data"):
        self.data_path = Path(data_path)
        self.callbacks: list[Callable[[], Awaitable]] = []
        self._running = False
        self._task = None

    def on_change(self, callback: Callable[[], Awaitable]):
        """Register a callback to be called on file changes."""
        self.callbacks.append(callback)

    async def _notify(self):
        """Notify all callbacks of a change."""
        for cb in self.callbacks:
            try:
                await cb()
            except Exception as e:
                print(f"[watcher] callback error: {e}")

    async def _watch(self):
        """Main watch loop."""
        async for changes in awatch(str(self.data_path)):
            if changes:
                print(f"[watcher] detected changes: {changes}", flush=True)
                await self._notify()

    async def start(self):
        """Start watching for file changes."""
        self._running = True
        self._task = asyncio.create_task(self._watch())
        print(f"[watcher] started watching {self.data_path}")

    async def stop(self):
        """Stop watching."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[watcher] stopped")
