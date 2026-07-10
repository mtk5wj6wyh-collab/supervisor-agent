"""Configuration for the Supervisor Agent (CodeBuddy-native).

This agent runs entirely on CodeBuddy's own runtime -- the Supervisor is the
CodeBuddy agent and the Worker / Reflection roles are CodeBuddy sub-agents
(defined under ``.codebuddy/agents/``). No external LLM HTTP endpoint is used.

For headless batch runs, the Python orchestrator drives the CodeBuddy CLI
(``cli_command``, default ``codebuddy -p``); in the IDE the SKILL.md instructs
the CodeBuddy agent to spawn the sub-agents directly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SupervisorConfig:
    # --- CodeBuddy agent runtime (native, no external API) ---
    cli_command: str = "codebuddy -p"  # command prefix to invoke a CodeBuddy agent headlessly
    worker_subagent: str = "worker"
    reflector_subagent: str = "reflector"
    model: str = "default"  # label only; CodeBuddy selects the actual model

    # --- Worker constraints (instructed to the sub-agent + used by Monitor) ---
    system_prompt: str = (
        "You are a diligent Worker Agent. Solve the user task step by step. "
        "Use the available tools when helpful. When the task is complete, reply "
        "with a concise final answer and stop -- do not loop."
    )
    tool_desc: Optional[str] = None
    max_steps: int = 12
    timeout_sec: float = 600.0

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
    mock_degrade: bool = False  # force the mock worker to report a degraded trace
    verbose: bool = True

    @classmethod
    def from_env(cls) -> "SupervisorConfig":
        def get(name: str, default):
            v = os.getenv(name)
            return v if v is not None else default

        return cls(
            cli_command=get("SUPERVISOR_CLI_COMMAND", cls.cli_command),
            worker_subagent=get("SUPERVISOR_WORKER_AGENT", cls.worker_subagent),
            reflector_subagent=get("SUPERVISOR_REFLECTOR_AGENT", cls.reflector_subagent),
            model=get("SUPERVISOR_MODEL", cls.model),
            max_steps=int(get("SUPERVISOR_MAX_STEPS", cls.max_steps)),
            latency_threshold_ms=int(get("SUPERVISOR_LATENCY_MS", cls.latency_threshold_ms)),
            token_p99_multiplier=float(get("SUPERVISOR_TOKEN_MULT", cls.token_p99_multiplier)),
            tool_repeat_threshold=int(get("SUPERVISOR_TOOL_REPEAT", cls.tool_repeat_threshold)),
            max_reflections_per_task=int(get("SUPERVISOR_MAX_REFLECT", cls.max_reflections_per_task)),
            enable_reflection=get("SUPERVISOR_REFLECTION", "1") != "0",
            workspace=get("SUPERVISOR_WORKSPACE", cls.workspace),
            mock=get("SUPERVISOR_MOCK", "0") == "1",
            mock_degrade=get("SUPERVISOR_MOCK_DEGRADE", "0") == "1",
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
