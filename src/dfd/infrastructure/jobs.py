"""In-process background execution: a worker pool and a pub/sub broker for live progress."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Event = dict[str, Any]
_STOP = object()


class EventBroker:
    """Fan-out of scan events from worker threads to asyncio subscribers (SSE streams)."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[Event]]]]
        self._subscribers = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, scan_id: str) -> asyncio.Queue[Event]:
        channel: asyncio.Queue[Event] = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers[scan_id].add((asyncio.get_running_loop(), channel))
        return channel

    def unsubscribe(self, scan_id: str, channel: asyncio.Queue[Event]) -> None:
        with self._lock:
            entries = self._subscribers.get(scan_id, set())
            self._subscribers[scan_id] = {e for e in entries if e[1] is not channel}
            if not self._subscribers[scan_id]:
                del self._subscribers[scan_id]

    def publish(self, scan_id: str, event: Event) -> None:
        with self._lock:
            targets = list(self._subscribers.get(scan_id, ()))
        for loop, channel in targets:
            try:
                loop.call_soon_threadsafe(self._offer, channel, event)
            except RuntimeError:  # loop already closed
                continue

    @staticmethod
    def _offer(channel: asyncio.Queue[Event], event: Event) -> None:
        if channel.full():
            channel.get_nowait()  # drop the oldest progress tick, never block a worker
        channel.put_nowait(event)


class WorkerPool:
    """Runs ``handler(scan_id)`` on daemon threads, one job at a time per worker."""

    def __init__(self, handler: Callable[[str], None], workers: int = 1) -> None:
        self._handler = handler
        self._count = workers
        self._queue: queue.Queue[object] = queue.Queue()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        for number in range(self._count):
            thread = threading.Thread(target=self._run, name=f"dfd-worker-{number}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def enqueue(self, scan_id: str) -> None:
        self._queue.put(scan_id)

    def stop(self, timeout: float = 10.0) -> None:
        for _ in self._threads:
            self._queue.put(_STOP)
        for thread in self._threads:
            thread.join(timeout)
        self._threads.clear()

    def join(self) -> None:
        """Block until every queued job has been handled (used by tests)."""
        self._queue.join()

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is _STOP:
                    return
                self._handler(str(job))
            except Exception:
                log.exception("worker failed on job %r", job)
            finally:
                self._queue.task_done()
