"""Supervisor Agent package: performance-aware, self-tuning multi-agent orchestrator."""

from .config import SupervisorConfig
from .models import Task, Trace, ReflectionResult, Verdict, TaskStatus
from .supervisor import Supervisor

__all__ = [
    "SupervisorConfig",
    "Task",
    "Trace",
    "ReflectionResult",
    "Verdict",
    "TaskStatus",
    "Supervisor",
]
