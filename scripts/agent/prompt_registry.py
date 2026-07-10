"""Prompt Registry: versioned management of Worker System Prompts.

Every prompt variant (baseline + each reflection-produced improvement) is stored
with metadata so the Supervisor can roll forward to the latest version, or fall
back to the baseline for A/B comparison / rollback.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional


class PromptRegistry:
    def __init__(self, path: str):
        self.path = path
        self.entries: List[Dict] = []
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.entries = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def init_baseline(self, system_prompt: str, tool_desc: Optional[str], eval_score=None):
        if self.entries:
            return
        self.add(system_prompt, tool_desc, trigger_reason="baseline", eval_score=eval_score)

    def add(
        self,
        system_prompt: str,
        tool_desc: Optional[str],
        trigger_reason: str,
        eval_score=None,
    ) -> Dict:
        version = f"v{len(self.entries) + 1}"
        entry = {
            "version": version,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "trigger_reason": trigger_reason,
            "system_prompt": system_prompt,
            "tool_desc": tool_desc,
            "eval_score": eval_score,
        }
        self.entries.append(entry)
        self._save()
        return entry

    def latest(self) -> Optional[Dict]:
        return self.entries[-1] if self.entries else None

    def baseline(self) -> Optional[Dict]:
        return self.entries[0] if self.entries else None

    def get(self, version: str) -> Optional[Dict]:
        for e in self.entries:
            if e["version"] == version:
                return e
        return None
