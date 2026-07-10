"""Shared data models for the Supervisor Agent.

Defines the Task, Trace, ReflectionResult and Verdict types that flow between
the Supervisor control plane, the Worker execution plane, the Monitor and the
Reflection/Prompt-Tuner layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    RETRY = "RETRY"
    FAILED_WITH_TUNING = "FAILED_WITH_TUNING"


class Verdict(str, Enum):
    OK = "OK"
    NEED_REFLECTION = "NEED_REFLECTION"
    DEGRADED = "DEGRADED"


@dataclass
class Task:
    """A single unit of work submitted to the Supervisor queue."""

    task_id: str
    description: str
    priority: int = 5  # lower number = higher priority
    depends_on: list = field(default_factory=list)
    status: str = "PENDING"
    retries: int = 0
    reflection_count: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(
            task_id=d["task_id"],
            description=d["description"],
            priority=d.get("priority", 5),
            depends_on=d.get("depends_on", []),
            status=d.get("status", "PENDING"),
            retries=d.get("retries", 0),
            reflection_count=d.get("reflection_count", 0),
            extra=d.get("extra", {}),
        )


@dataclass
class Trace:
    """Structured execution record returned by a Worker Agent run."""

    task_id: str
    worker_config_version: str
    elapsed_ms: int
    step_count: int
    input_tokens: int
    output_tokens: int
    tool_call_count: int
    tool_call_sequence: list = field(default_factory=list)
    final_answer: str = ""
    error: Optional[str] = None
    rerun: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReflectionResult:
    """Output of the Reflection & Prompt-Tuner module."""

    version: str
    root_cause: str
    new_system_prompt: str
    new_tool_desc: Optional[str]
    suggestion: str
    triggered_by: str

    def to_dict(self) -> dict:
        return asdict(self)
