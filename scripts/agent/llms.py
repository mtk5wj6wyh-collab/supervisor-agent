"""LLM client (OpenAI-compatible) with an offline mock fallback.

The Worker Agent and the Reflection Tuner both talk to an LLM through this
client. When no API key is available (or ``mock=True``) a deterministic mock
responder is used so the full orchestration / monitor / reflection loop can be
exercised without network access.
"""

from __future__ import annotations

import json
import os
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
        # ~4 chars per token is a reasonable approximation.
        return max(1, len(text) // 4)


class _ToolCall:
    def __init__(self, tc_id: str, name: str, arguments: str):
        self.id = tc_id
        self.function = _Function(name, arguments)


class _Function:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _Msg:
    """Minimal stand-in for an openai chat completion message."""

    def __init__(self, content: Optional[str] = None, tool_calls: Optional[list] = None):
        self.content = content
        self.tool_calls = tool_calls or []


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: callable

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
        mock: bool = False,
    ):
        self.base_url = base_url or os.getenv("SUPERVISOR_LLM_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("SUPERVISOR_LLM_API_KEY", "")
        self.model = model or os.getenv("SUPERVISOR_LLM_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self.mock = mock
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError(
                    "The 'openai' package is required for real LLM calls. "
                    "Install it with `pip install openai`, or run with --mock."
                ) from e
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)

    def chat(self, messages: List[dict], tools=None, temperature: float = 0.3):
        if self.mock:
            return self._mock_chat(messages, tools)
        self._ensure()
        params = dict(model=self.model, messages=messages, temperature=temperature)
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        resp = self._client.chat.completions.create(**params)
        return resp.choices[0].message

    def _mock_chat(self, messages: List[dict], tools):
        """Deterministic offline responder.

        - If tools exist and none has been called yet, emit one tool call.
        - Otherwise emit a final answer that echoes the last user message.
        """
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        if tools and not has_tool_result:
            schema = tools[0]
            fn_name = schema["function"]["name"]
            return _Msg(
                content=None,
                tool_calls=[_ToolCall("call_1", fn_name, json.dumps({"query": last_user[:80]}))],
            )

        return _Msg(
            content=(
                f"[mock-final-answer] Task processed. Summary of request: "
                f"{last_user[:120]}"
            )
        )
