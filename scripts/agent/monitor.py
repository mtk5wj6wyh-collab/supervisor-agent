"""Monitor & Evaluator: performance observation and threshold judgement.

Collects latency / step / token / tool-call metrics from each Worker Trace,
compares them against configured thresholds and against a rolling baseline
(p99 of historical token usage), and emits a Verdict:

- OK                -> metrics within bounds
- NEED_REFLECTION   -> at least one metric breached, first occurrence
- DEGRADED          -> ``degrade_consecutive`` breaches in a row
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .config import SupervisorConfig
from .models import Trace, Verdict


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def _max_consecutive(seq: List[str]) -> int:
    if not seq:
        return 0
    best = cur = 1
    for i in range(1, len(seq)):
        if seq[i] == seq[i - 1]:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


class Monitor:
    def __init__(self, config: SupervisorConfig):
        self.cfg = config
        self.latencies: List[int] = []
        self.token_totals: List[int] = []
        self._consecutive_degrade = 0

    def evaluate(self, trace: Trace) -> Tuple[Verdict, Dict]:
        reasons: List[str] = []
        total_tokens = trace.input_tokens + trace.output_tokens

        if trace.error:
            reasons.append(f"worker error: {trace.error}")

        if trace.elapsed_ms > self.cfg.latency_threshold_ms:
            reasons.append(
                f"latency {trace.elapsed_ms}ms > threshold {self.cfg.latency_threshold_ms}ms"
            )

        if trace.step_count >= self.cfg.max_steps:
            reasons.append(
                f"step_count {trace.step_count} >= max_steps {self.cfg.max_steps} (possible loop)"
            )

        if self.token_totals:
            p99 = _percentile(self.token_totals, 99)
            if p99 and total_tokens > p99 * self.cfg.token_p99_multiplier:
                reasons.append(
                    f"token total {total_tokens} > p99 {p99} * {self.cfg.token_p99_multiplier}"
                )

        repeat = _max_consecutive(trace.tool_call_sequence)
        if repeat >= self.cfg.tool_repeat_threshold:
            reasons.append(
                f"tool '{trace.tool_call_sequence[-1]}' called {repeat} times consecutively"
            )

        # Update baselines only for clean runs so p99 stays meaningful.
        if not trace.error and trace.step_count < self.cfg.max_steps:
            self.latencies.append(trace.elapsed_ms)
            self.token_totals.append(total_tokens)

        if reasons:
            self._consecutive_degrade += 1
            if self._consecutive_degrade >= self.cfg.degrade_consecutive:
                verdict = Verdict.DEGRADED
            else:
                verdict = Verdict.NEED_REFLECTION
        else:
            self._consecutive_degrade = 0
            verdict = Verdict.OK

        metrics = {
            "elapsed_ms": trace.elapsed_ms,
            "step_count": trace.step_count,
            "input_tokens": trace.input_tokens,
            "output_tokens": trace.output_tokens,
            "token_total": total_tokens,
            "tool_call_count": trace.tool_call_count,
            "max_tool_repeat": repeat,
            "baseline_token_p99": _percentile(self.token_totals, 99),
        }
        return verdict, {"verdict": verdict.value, "reasons": reasons, "metrics": metrics}
