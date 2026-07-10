"""Reflection & Prompt Tuner: conversational prompt auto-optimization.

Implements a Reflexion-style loop via the CodeBuddy runtime (no external API).
Given a Task, its Worker Trace, the current System Prompt and tool description,
a CodeBuddy agent (the "meta-critic", default sub-agent ``reflector``) is asked
to diagnose the root cause and produce an improved System Prompt. The produced
prompt is versioned by the Prompt Registry.

In mock mode a deterministic improved prompt is returned so the closed loop is
verifiable offline.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from .config import SupervisorConfig
from .llms import CodeBuddyRunner
from .models import ReflectionResult, Task, Trace

REFLECT_PROMPT = """You are a meta-critic that improves the System Prompt of a Worker Agent.
You receive the original task, the Worker's execution trace (timing, steps,
tool calls) and the current System Prompt. Output STRICT JSON ONLY, no prose,
in this schema:
{{
  "root_cause": "<why the worker was slow / low-quality>",
  "new_system_prompt": "<improved, more concise prompt with explicit stop rule>",
  "new_tool_desc": null or "<trimmed tool description>",
  "suggestion": "<e.g. lower max_steps to 8 / switch to a lighter model>"
}}

# Original task
{task}

# Worker execution trace
- elapsed_ms: {elapsed_ms}
- step_count: {step_count} / max_steps {max_steps}
- input_tokens: {input_tokens}, output_tokens: {output_tokens}
- tool_call_sequence: {tool_seq}
- final_answer: {answer}
- error: {error}

# Why monitoring flagged this
{reasons}

# Current System Prompt
{current_prompt}

# Current tool description
{tool_desc}

Rewrite the System Prompt so the Worker finishes faster and with higher quality.
Return only the JSON object described above."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text


def _build_prompt(task, trace, current_prompt, tool_desc, reasons, max_steps) -> str:
    return REFLECT_PROMPT.format(
        task=task.description,
        elapsed_ms=trace.elapsed_ms,
        step_count=trace.step_count,
        max_steps=max_steps,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        tool_seq=trace.tool_call_sequence,
        answer=(trace.final_answer or "")[:500],
        error=trace.error or "none",
        reasons="\n".join("- " + r for r in reasons) or "n/a",
        current_prompt=current_prompt,
        tool_desc=tool_desc or "none",
    )


class ReflectionTuner:
    def __init__(self, config: SupervisorConfig, runner: CodeBuddyRunner):
        self.cfg = config
        self.runner = runner

    def reflect(
        self,
        task: Task,
        trace: Trace,
        current_prompt: str,
        tool_desc: Optional[str],
        reasons: List[str],
        new_version: str,
        max_steps: int,
    ) -> ReflectionResult:
        prompt = _build_prompt(task, trace, current_prompt, tool_desc, reasons, max_steps)

        if self.runner.mock:
            improved = (
                current_prompt
                + "\n\n[refined by mock reflection] Be concise, avoid repeated tool "
                "calls, and stop as soon as the answer is found."
            )
            return ReflectionResult(
                version=new_version,
                root_cause="mock: simulated degradation (latency/steps/tokens)",
                new_system_prompt=improved,
                new_tool_desc=tool_desc,
                suggestion=f"lower max_steps to {max(4, max_steps - 2)}",
                triggered_by="; ".join(reasons) or "manual",
            )

        raw = self.runner.run(prompt)
        try:
            data = json.loads(_strip_fences(raw))
        except json.JSONDecodeError:
            return ReflectionResult(
                version=new_version,
                root_cause="(reflection output could not be parsed)",
                new_system_prompt=current_prompt + "\n[reflection note: " + raw[:200] + "]",
                new_tool_desc=tool_desc,
                suggestion="",
                triggered_by="; ".join(reasons) or "manual",
            )

        return ReflectionResult(
            version=new_version,
            root_cause=data.get("root_cause", ""),
            new_system_prompt=data.get("new_system_prompt", current_prompt),
            new_tool_desc=data.get("new_tool_desc"),
            suggestion=data.get("suggestion", ""),
            triggered_by="; ".join(reasons) or "manual",
        )
