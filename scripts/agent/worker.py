"""Worker Agent: delegates task execution to a CodeBuddy sub-agent.

The Worker no longer calls an external LLM API. Instead it builds a
self-contained prompt (active System Prompt + task + available tools + a
<<TRACE>> metrics footer contract) and asks the CodeBuddy runtime to execute
it -- either via the CLI runner (headless) or, in the IDE, the SKILL.md spawns
the ``worker`` sub-agent directly with this prompt.

Latency is measured by the Supervisor (wall clock); step / token / tool-call
metrics are self-reported by the Worker sub-agent in the footer.
"""

from __future__ import annotations

import re
import time
from typing import List, Optional

from .llms import CodeBuddyRunner, Tool
from .models import Trace

TRACE_RE = re.compile(r"<<TRACE>>(.*?)<<END>>", re.DOTALL)


def _parse_trace_footer(raw: str) -> dict:
    data = {
        "step_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_call_count": 0,
        "tool_calls": [],
    }
    m = TRACE_RE.search(raw)
    if not m:
        return data
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if key == "step_count":
            data["step_count"] = int(val) if val.isdigit() else 0
        elif key == "input_tokens":
            data["input_tokens"] = int(val) if val.isdigit() else 0
        elif key == "output_tokens":
            data["output_tokens"] = int(val) if val.isdigit() else 0
        elif key == "tool_call_count":
            data["tool_call_count"] = int(val) if val.isdigit() else 0
        elif key == "tool_calls":
            data["tool_calls"] = [t.strip() for t in val.split(",") if t.strip()]
    return data


def _strip_footer(raw: str) -> str:
    return TRACE_RE.sub("", raw).strip()


class WorkerAgent:
    def __init__(self, config, runner: CodeBuddyRunner, tools: Optional[List[Tool]] = None):
        self.config = config
        self.runner = runner
        self.tools: List[Tool] = tools or []

    def _build_prompt(self, task_description, system_prompt, tool_desc, version, rerun) -> str:
        tool_block = tool_desc or "\n".join(t.describe() for t in self.tools) or (
            "Use the tools available in your environment as needed."
        )
        rerun_note = ""
        if rerun:
            rerun_note = (
                "\nNOTE: This is a RE-RUN after a previous degradation. Apply the "
                "improved System Prompt above and avoid the earlier failure mode."
            )
        return (
            "You are a Worker Agent executing ONE task for a Supervisor.\n\n"
            f"# System Prompt (active version {version})\n{system_prompt}\n\n"
            "# Available tools\n"
            f"{tool_block}\n\n"
            f"# Task\n{task_description}\n\n"
            "# Constraints\n"
            f"- Solve the task step by step (ReAct). You may use tools.\n"
            f"- Do NOT exceed roughly {self.config.max_steps} reasoning steps.\n"
            "- Stop as soon as you have a final answer; do not loop.\n"
            f"{rerun_note}\n\n"
            "# Output\n"
            "First give your final answer to the task. Then, at the very end, emit "
            "EXACTLY this metrics block (with no extra text after it):\n\n"
            "<<TRACE>>\n"
            "elapsed_ms: <best-effort ms you spent>\n"
            "step_count: <number of reasoning/tool steps you took>\n"
            "input_tokens: <best-effort>\n"
            "output_tokens: <best-effort>\n"
            "tool_call_count: <number of tool calls>\n"
            "tool_calls: <comma-separated tool names, or empty>\n"
            "<<END>>"
        )

    def run(
        self,
        task_description: str,
        system_prompt: str,
        tool_desc: Optional[str],
        version: str = "v0",
        rerun: bool = False,
    ) -> Trace:
        t0 = time.time()
        prompt = self._build_prompt(task_description, system_prompt, tool_desc, version, rerun)
        raw = self.runner.run(prompt)
        elapsed_ms = int((time.time() - t0) * 1000)

        footer = _parse_trace_footer(raw)
        final_answer = _strip_footer(raw)

        # Latency is measured by the Supervisor (wall clock); step / token /
        # tool-call metrics come from the Worker's self-reported <<TRACE>> footer.
        return Trace(
            task_id="",
            worker_config_version=version,
            elapsed_ms=elapsed_ms,
            step_count=footer["step_count"],
            input_tokens=footer["input_tokens"],
            output_tokens=footer["output_tokens"],
            tool_call_count=footer["tool_call_count"],
            tool_call_sequence=footer["tool_calls"],
            final_answer=final_answer,
            error=None if final_answer else "empty worker output",
            rerun=rerun,
        )
