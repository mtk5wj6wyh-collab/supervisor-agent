"""Trace Store: append-only JSONL log of every task execution.

Each record captures the worker config version, the collected metrics, the
reflection log (if any) and the final output. This is the audit trail that
feeds the optional dashboard / A/B comparison.
"""

from __future__ import annotations

import json
import os
from typing import Dict


class TraceStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def record(self, record: Dict):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def all(self) -> list:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
