from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from itertools import count
from pathlib import Path
from queue import Empty, PriorityQueue, Queue
from threading import Event, RLock, Thread
import time
from typing import Callable


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: str
    kind: str
    label: str
    state: TaskState
    completed: int = 0
    total: int | None = None
    destination: str = ""
    detail: str = ""
    error: str = ""
    cancellable: bool = True
    created_at: float = 0.0
    finished_at: float = 0.0


class TaskCancelled(RuntimeError):
    pass


class TaskContext:
    def __init__(self, task_id: str, cancel: Event, progress: Callable[[int, int | None, str], None]) -> None:
        self.task_id = task_id
        self._cancel = cancel
        self._progress = progress

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise TaskCancelled(self.task_id)

    def report(self, completed: int, total: int | None = None, detail: str = "") -> None:
        self.check_cancelled()
        self._progress(max(0, int(completed)), None if total is None else max(0, int(total)), detail)


TaskWork = Callable[[TaskContext], object]


class BackgroundTaskController:
    """One bounded worker for operator-initiated disk work.

    Capture, frame encoding, thumbnails and computer-vision workers deliberately
    remain outside this queue.  Serialising user export work prevents multiple
    large copies from competing for the same event disk.
    """

    def __init__(self, event_queue: Queue[tuple[str, object]]) -> None:
        self.event_queue = event_queue
        self._queue: PriorityQueue[tuple[int, int, str, TaskWork]] = PriorityQueue()
        self._counter = count()
        self._snapshots: dict[str, TaskSnapshot] = {}
        self._cancels: dict[str, Event] = {}
        self._works: dict[str, tuple[str, str, TaskWork, int, str, bool]] = {}
        self._lock = RLock()
        self._stop = Event()
        self._thread = Thread(target=self._loop, name="background-tasks", daemon=True)
        self._thread.start()

    def submit(self, kind: str, label: str, work: TaskWork, *, priority: int = 50,
               destination: Path | str | None = None, cancellable: bool = True) -> str:
        order = next(self._counter)
        task_id = f"task-{order:06d}"
        snapshot = TaskSnapshot(
            task_id, str(kind), str(label), TaskState.QUEUED,
            destination=str(destination or ""), cancellable=bool(cancellable), created_at=time.time(),
        )
        with self._lock:
            self._snapshots[task_id] = snapshot
            self._cancels[task_id] = Event()
            self._works[task_id] = (str(kind), str(label), work, int(priority), str(destination or ""), bool(cancellable))
        self._queue.put((int(priority), order, task_id, work))
        self._emit(snapshot)
        return task_id

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            snapshot = self._snapshots.get(task_id)
            cancel = self._cancels.get(task_id)
            if snapshot is None or cancel is None or not snapshot.cancellable or snapshot.state not in {TaskState.QUEUED, TaskState.RUNNING}:
                return False
            cancel.set()
            return True

    def snapshots(self) -> list[TaskSnapshot]:
        with self._lock:
            return sorted((replace(item) for item in self._snapshots.values()), key=lambda item: item.created_at, reverse=True)

    def retry(self, task_id: str) -> str | None:
        with self._lock:
            snapshot = self._snapshots.get(task_id)
            stored = self._works.get(task_id)
        if snapshot is None or stored is None or snapshot.state not in {TaskState.FAILED, TaskState.CANCELLED}:
            return None
        kind, label, work, priority, destination, cancellable = stored
        return self.submit(kind, label, work, priority=priority, destination=destination, cancellable=cancellable)

    def stop(self, timeout: float = 2.0) -> list[str]:
        self._stop.set()
        with self._lock:
            for cancel in self._cancels.values():
                cancel.set()
        self._thread.join(max(0.0, timeout))
        return [self._thread.name] if self._thread.is_alive() else []

    def _update(self, task_id: str, **changes: object) -> TaskSnapshot:
        with self._lock:
            current = self._snapshots[task_id]
            updated = replace(current, **changes)
            self._snapshots[task_id] = updated
        self._emit(updated)
        return updated

    def _emit(self, snapshot: TaskSnapshot) -> None:
        self.event_queue.put(("background_task", snapshot))

    def _loop(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                _priority, _order, task_id, work = self._queue.get(timeout=.1)
            except Empty:
                continue
            try:
                with self._lock:
                    cancel = self._cancels[task_id]
                if cancel.is_set():
                    raise TaskCancelled(task_id)
                self._update(task_id, state=TaskState.RUNNING)
                context = TaskContext(
                    task_id, cancel,
                    lambda completed, total, detail: self._update(
                        task_id, completed=completed, total=total, detail=detail,
                    ),
                )
                work(context)
                context.check_cancelled()
                self._update(task_id, state=TaskState.COMPLETED, finished_at=time.time())
            except TaskCancelled:
                self._update(task_id, state=TaskState.CANCELLED, finished_at=time.time())
            except Exception as exc:
                self._update(task_id, state=TaskState.FAILED, error=str(exc), finished_at=time.time())
            finally:
                self._queue.task_done()
