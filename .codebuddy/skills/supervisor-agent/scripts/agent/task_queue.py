"""Task queue with priority ordering and dependency resolution.

Tasks are stored as a list; the Supervisor pops the next runnable task based on
priority and dependency status. The queue is persisted to JSON so a run can be
resumed after interruption.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List

from .models import Task, TaskStatus


@dataclass
class TaskQueue:
    tasks: List[Task] = field(default_factory=list)
    path: str = ""

    # --- persistence ---
    def save(self):
        if self.path:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self.tasks], f, ensure_ascii=False, indent=2)

    @classmethod
    def load_or_create(cls, path: str) -> "TaskQueue":
        q = cls(path=path)
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            q.tasks = [Task.from_dict(d) for d in data]
        return q

    def add(self, task: Task):
        self.tasks.append(task)
        self.save()

    def add_many(self, task_list: List[Task]):
        self.tasks.extend(task_list)
        self.save()

    def _is_runnable(self, task: Task) -> bool:
        if task.status not in (TaskStatus.PENDING.value, TaskStatus.RETRY.value):
            return False
        for dep in task.depends_on:
            dep_task = self.get(dep)
            if dep_task is None or dep_task.status != TaskStatus.DONE.value:
                return False
        return True

    def pop_next(self) -> Task | None:
        """Return the highest-priority runnable task, or None if none ready."""
        candidates = [t for t in self.tasks if self._is_runnable(t)]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (t.priority, t.task_id))
        chosen = candidates[0]
        chosen.status = TaskStatus.RUNNING.value
        self.save()
        return chosen

    def update(self, task: Task):
        for i, t in enumerate(self.tasks):
            if t.task_id == task.task_id:
                self.tasks[i] = task
                break
        self.save()

    def get(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def has_pending(self) -> bool:
        return any(
            t.status in (TaskStatus.PENDING.value, TaskStatus.RETRY.value) for t in self.tasks
        )

    def summary(self) -> dict:
        by_status = {}
        for t in self.tasks:
            by_status[t.status] = by_status.get(t.status, 0) + 1
        return {"total": len(self.tasks), "by_status": by_status}
