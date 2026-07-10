"""Command line interface for the Supervisor Agent (CodeBuddy-native).

The orchestrator drives CodeBuddy's own runtime -- no external LLM API. In the
IDE the SKILL.md spawns the Worker/Reflection sub-agents directly; headlessly
this script shells out to the CodeBuddy CLI (default ``codebuddy -p``).

Examples
--------
# Offline demo (no CLI needed)
python agent/cli.py --tasks example_tasks.json --mock

# Headless run via the CodeBuddy CLI
python agent/cli.py --tasks example_tasks.json

# Custom CLI command / thresholds
python agent/cli.py --tasks tasks.json --cli-command "codebuddy -p" --latency-ms 8000
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .config import SupervisorConfig
from .llms import Tool
from .models import Task
from .supervisor import Supervisor


def _default_tools() -> List[Tool]:
    """A small built-in tool set so the Worker has something to call."""

    def calculator(expression: str) -> str:
        try:
            return str(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 (demo only)
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"

    def echo(text: str) -> str:
        return text

    return [
        Tool(
            name="calculator",
            description="Evaluate a basic arithmetic expression, e.g. '2*(3+4)'.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            func=calculator,
        ),
        Tool(
            name="echo",
            description="Echo back the provided text (useful for reminders).",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            func=echo,
        ),
    ]


def _load_tasks(path: str) -> List[Task]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    tasks = []
    for i, item in enumerate(data):
        if "task_id" not in item:
            item["task_id"] = f"task_{i+1}"
        tasks.append(Task.from_dict(item))
    return tasks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Performance-aware Supervisor Agent with prompt auto-tuning.")
    p.add_argument("--tasks", required=True, help="Path to a JSON task list.")
    p.add_argument("--config", help="Path to a JSON config file (overrides env/defaults).")
    p.add_argument("--mock", action="store_true", help="Use the offline mock runner (no CodeBuddy CLI needed).")
    p.add_argument("--mock-degrade", action="store_true", help="Force the mock worker to report a degraded trace (demo of the reflection loop).")
    p.add_argument("--cli-command", help="CodeBuddy CLI command prefix, e.g. 'codebuddy -p'.")
    p.add_argument("--workspace", help="Workspace directory for state files.")
    p.add_argument("--latency-ms", type=int, help="Latency threshold in ms.")
    p.add_argument("--max-steps", type=int, help="Worker max_steps.")
    p.add_argument("--max-reflect", type=int, help="Max reflections per task.")
    p.add_argument("--quiet", action="store_true", help="Reduce output.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.config:
        cfg = SupervisorConfig.from_file(args.config)
    else:
        cfg = SupervisorConfig.from_env()

    # CLI overrides
    if args.mock:
        cfg.mock = True
    if args.mock_degrade:
        cfg.mock_degrade = True
    if args.cli_command:
        cfg.cli_command = args.cli_command
    if args.workspace:
        cfg.workspace = args.workspace
    if args.latency_ms:
        cfg.latency_threshold_ms = args.latency_ms
    if args.max_steps:
        cfg.max_steps = args.max_steps
    if args.max_reflect is not None:
        cfg.max_reflections_per_task = args.max_reflect
    if args.quiet:
        cfg.verbose = False

    tasks = _load_tasks(args.tasks)
    tools = _default_tools()

    supervisor = Supervisor(cfg, tasks, tools)
    supervisor.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
