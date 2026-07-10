"""CodeBuddy-native runner for the Worker / Reflection sub-agents.

There is NO external LLM HTTP endpoint. The Supervisor is the CodeBuddy agent,
and the Worker / Reflection roles are CodeBuddy sub-agents. This module knows
how to invoke a CodeBuddy agent:

* In the IDE, the SKILL.md drives the sub-agents directly (via the Task tool).
* Headlessly, ``run.py`` shells out to the CodeBuddy CLI (``cli_command``,
  default ``codebuddy -p "<prompt>"``).

A deterministic offline ``mock`` mode is kept so the whole orchestration /
monitor / reflection loop can be exercised without a CLI.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


def count_tokens(text: str) -> int:
    """Heuristic token counter; uses tiktoken when available."""
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


@dataclass
class Tool:
    """A tool descriptor surfaced to the Worker sub-agent as text.

    In the CodeBuddy-native design the Worker uses CodeBuddy's own tools, so a
    Tool here is documentation only (``func`` is unused by the CLI path).
    """

    name: str
    description: str
    parameters: Optional[dict] = None
    func: Optional[callable] = None

    def describe(self) -> str:
        return f"- {self.name}: {self.description}"


class CodeBuddyRunner:
    def __init__(
        self,
        cli_command: str = "codebuddy -p",
        timeout: float = 600.0,
        mock: bool = False,
        mock_degrade: bool = False,
    ):
        self.cli_command = cli_command
        self.timeout = timeout
        self.mock = mock
        self.mock_degrade = mock_degrade

    def run(self, prompt: str) -> str:
        """Invoke a CodeBuddy agent with ``prompt`` and return its text output."""
        if self.mock:
            return self._mock(prompt)
        cmd = self.cli_command.split() + [prompt]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
            )
            return (result.stdout or "") + (result.stderr or "")
        except Exception as e:  # noqa: BLE001
            return f"[runner-error] {type(e).__name__}: {e}"

    def _mock(self, prompt: str) -> str:
        # Emit a worker-like answer plus a <<TRACE>> footer so the Monitor can run.
        if self.mock_degrade:
            return (
                "[mock-final-answer] task processed (degraded run).\n\n"
                "<<TRACE>>\n"
                "elapsed_ms: 0\n"
                "step_count: 99\n"
                "input_tokens: 200\n"
                "output_tokens: 200\n"
                "tool_call_count: 0\n"
                "tool_calls: \n"
                "<<END>>"
            )
        return (
            "[mock-final-answer] task processed.\n\n"
            "<<TRACE>>\n"
            "elapsed_ms: 0\n"
            "step_count: 2\n"
            "input_tokens: 120\n"
            "output_tokens: 80\n"
            "tool_call_count: 1\n"
            "tool_calls: calculator\n"
            "<<END>>"
        )
