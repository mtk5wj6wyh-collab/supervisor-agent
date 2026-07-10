"""Configuration for the Supervisor Agent.

All thresholds, model endpoints, worker constraints and storage paths live
here. A config can be built from environment variables or a JSON file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SupervisorConfig:
    # --- LLM endpoints (OpenAI-compatible) ---
    model: str = "gpt-4o-mini"
    reflection_model: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    api_timeout: float = 120.0

    # --- Worker constraints ---
    system_prompt: str = (
        "You are a diligent Worker Agent. Solve the user task step by step. "
        "Use the provided tools when helpful. When the task is complete, reply "
        "with a concise final answer and stop."
    )
    tool_desc: Optional[str] = None
    max_steps: int = 12
    timeout_sec: float = 60.0

    # --- Monitor thresholds ---
    latency_threshold_ms: int = 15000
    token_p99_multiplier: float = 2.0
    tool_repeat_threshold: int = 5  # >= N consecutive calls to the same tool
    degrade_consecutive: int = 3  # N consecutive degradations -> DEGRADED

    # --- Reflection control ---
    enable_reflection: bool = True
    max_reflections_per_task: int = 2

    # --- Storage ---
    workspace: str = "./supervisor_workspace"
    prompt_registry_file: str = "prompt_registry.json"
    trace_store_file: str = "traces.jsonl"

    # --- Misc ---
    mock: bool = False
    verbose: bool = True

    @classmethod
    def from_env(cls) -> "SupervisorConfig":
        def get(name: str, default):
            v = os.getenv(name)
            if v is None:
                return default
            return v

        return cls(
            model=get("SUPERVISOR_LLM_MODEL", cls.model),
            reflection_model=get("SUPERVISOR_REFLECTION_MODEL", None) or None,
            base_url=get("SUPERVISOR_LLM_BASE_URL", cls.base_url),
            api_key=get("SUPERVISOR_LLM_API_KEY", "") or "",
            max_steps=int(get("SUPERVISOR_MAX_STEPS", cls.max_steps)),
            latency_threshold_ms=int(get("SUPERVISOR_LATENCY_MS", cls.latency_threshold_ms)),
            token_p99_multiplier=float(get("SUPERVISOR_TOKEN_MULT", cls.token_p99_multiplier)),
            tool_repeat_threshold=int(get("SUPERVISOR_TOOL_REPEAT", cls.tool_repeat_threshold)),
            max_reflections_per_task=int(get("SUPERVISOR_MAX_REFLECT", cls.max_reflections_per_task)),
            enable_reflection=get("SUPERVISOR_REFLECTION", "1") != "0",
            workspace=get("SUPERVISOR_WORKSPACE", cls.workspace),
            mock=get("SUPERVISOR_MOCK", "0") == "1",
            verbose=get("SUPERVISOR_VERBOSE", "1") != "0",
        )

    @classmethod
    def from_file(cls, path: str) -> "SupervisorConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls.from_env()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
