"""Worker Agent: a constrained ReAct / Plan-Execute loop with tool calling.

The Worker receives a task plus the currently-active System Prompt and tool
description, then runs a bounded reasoning loop. It returns a structured Trace
that the Monitor layer consumes. The loop is capped by ``max_steps`` and a
wall-clock ``timeout_sec`` to guarantee termination.
"""

from __future__ import annotations

import json
import time
from typing import List, Optional

from .llms import LLMClient, Tool, count_tokens
from .models import Trace


class WorkerAgent:
    def __init__(self, config, llm: LLMClient, tools: Optional[List[Tool]] = None):
        self.config = config
        self.llm = llm
        self.tools: List[Tool] = tools or []
        self._tool_map = {t.name: t for t in self.tools}

    def _execute_tool(self, name: str, arguments: str) -> str:
        tool = self._tool_map.get(name)
        if tool is None:
            return f"[error] unknown tool: {name}"
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        try:
            result = tool.func(**args)
            return str(result)
        except Exception as e:  # noqa: BLE001 - surface tool errors back to the model
            return f"[tool-error] {type(e).__name__}: {e}"

    def run(
        self,
        task_description: str,
        system_prompt: str,
        tool_desc: Optional[str],
        version: str = "v0",
        rerun: bool = False,
    ) -> Trace:
        t0 = time.time()
        system = system_prompt or "You are a helpful assistant."
        if tool_desc:
            system += "\n\nAvailable tools:\n" + tool_desc

        messages: List[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_description},
        ]

        step = 0
        tool_seq: List[str] = []
        in_tok = 0
        out_tok = 0
        final_answer = ""
        error: Optional[str] = None

        tool_schemas = [t.to_openai_schema() for t in self.tools] or None

        try:
            while step < self.config.max_steps:
                if time.time() - t0 > self.config.timeout_sec:
                    error = f"timeout after {self.config.timeout_sec}s"
                    break

                in_tok += count_tokens(json.dumps(messages, ensure_ascii=False))
                resp = self.llm.chat(messages, tools=tool_schemas, temperature=0.3)
                step += 1

                if getattr(resp, "tool_calls", None):
                    for tc in resp.tool_calls:
                        name = tc.function.name
                        tool_seq.append(name)
                        result = self._execute_tool(name, tc.function.arguments)
                        messages.append(
                            {
                                "role": "assistant",
                                "content": resp.content or "",
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": tc.function.arguments,
                                        },
                                    }
                                ],
                            }
                        )
                        messages.append(
                            {"role": "tool", "tool_call_id": tc.id, "content": result}
                        )
                        out_tok += count_tokens(result)
                else:
                    final_answer = resp.content or ""
                    out_tok += count_tokens(final_answer)
                    messages.append({"role": "assistant", "content": final_answer})
                    break
            else:
                # Loop exhausted max_steps without a final answer.
                final_answer = final_answer or "(max steps reached without final answer)"
                error = error or "step budget exhausted"
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"

        elapsed_ms = int((time.time() - t0) * 1000)
        return Trace(
            task_id="",
            worker_config_version=version,
            elapsed_ms=elapsed_ms,
            step_count=step,
            input_tokens=in_tok,
            output_tokens=out_tok,
            tool_call_count=len(tool_seq),
            tool_call_sequence=tool_seq,
            final_answer=final_answer,
            error=error,
            rerun=rerun,
        )
