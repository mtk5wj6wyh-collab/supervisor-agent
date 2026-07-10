"""Supervisor control plane (Orchestrator).

Drives the closed loop described in the design:

    for each task in queue:
        1. take currently-active System Prompt -> create/reuse Worker
        2. t0 = now(); Worker.run(task) -> Trace
        3. Monitor.evaluate(Trace)
        4. if OK: record -> next task
           else:
             a. Reflection Module -> new Prompt
             b. update Prompt Registry
             c. if allowed: rerun Worker with new Prompt
             d. next task (subsequent tasks use the new Prompt)

Anti-loop guards:
    - a task triggers at most ``max_reflections_per_task`` reflections
    - if still over threshold afterwards -> FAILED_WITH_TUNING, move on
"""

from __future__ import annotations

import os
import time
from typing import List, Optional

from .config import SupervisorConfig
from .llms import LLMClient, Tool
from .models import Task, TaskStatus, Trace, Verdict
from .monitor import Monitor
from .prompt_registry import PromptRegistry
from .reflection import ReflectionTuner
from .task_queue import TaskQueue
from .trace_store import TraceStore
from .worker import WorkerAgent


class Supervisor:
    def __init__(self, config: SupervisorConfig, tasks: List[Task], tools: Optional[List[Tool]] = None):
        self.config = config
        os.makedirs(config.workspace, exist_ok=True)

        self.queue = TaskQueue.load_or_create(os.path.join(config.workspace, "task_queue.json"))
        if tasks:
            self.queue.add_many(tasks)

        self.registry = PromptRegistry(os.path.join(config.workspace, config.prompt_registry_file))
        self.registry.init_baseline(config.system_prompt, config.tool_desc)

        self.trace_store = TraceStore(os.path.join(config.workspace, config.trace_store_file))
        self.monitor = Monitor(config)

        worker_llm = LLMClient(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            timeout=config.api_timeout,
            mock=config.mock,
        )
        self.worker = WorkerAgent(config, worker_llm, tools)

        reflection_llm = LLMClient(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.reflection_model or config.model,
            timeout=config.api_timeout,
            mock=config.mock,
        )
        self.reflection = ReflectionTuner(config, reflection_llm)

    def run(self):
        print(f"[supervisor] queue: {self.queue.summary()}")
        while self.queue.has_pending():
            task = self.queue.pop_next()
            if task is None:
                break
            self._process(task)
            if self.config.verbose:
                print(f"[supervisor] queue: {self.queue.summary()}")
        print("[supervisor] all tasks processed.")
        self._print_summary()

    def _process(self, task: Task):
        while True:
            active = self.registry.latest()
            version = active["version"]
            prompt = active["system_prompt"]
            tool_desc = active.get("tool_desc") or self.config.tool_desc

            rerun = task.reflection_count > 0
            trace = self.worker.run(task.description, prompt, tool_desc, version, rerun=rerun)
            trace.task_id = task.task_id

            verdict, detail = self.monitor.evaluate(trace)
            if self.config.verbose:
                self._print_task(task.task_id, trace, detail)

            reflection_log = None
            if verdict == Verdict.OK:
                task.status = TaskStatus.DONE.value
                self.queue.update(task)
                self.trace_store.record(self._record(task, trace, detail, reflection_log))
                return

            # Over threshold -> consider reflection / rerun.
            if not self.config.enable_reflection or task.reflection_count >= self.config.max_reflections_per_task:
                task.status = TaskStatus.FAILED_WITH_TUNING.value
                self.queue.update(task)
                self.trace_store.record(self._record(task, trace, detail, reflection_log, failed=True))
                print(
                    f"[supervisor] {task.task_id}: FAILED_WITH_TUNING "
                    f"(reflections={task.reflection_count})"
                )
                return

            result = self.reflection.reflect(
                task,
                trace,
                prompt,
                tool_desc,
                detail["reasons"],
                new_version=f"v{len(self.registry.entries) + 1}",
                max_steps=self.config.max_steps,
            )
            self.registry.add(
                result.new_system_prompt,
                result.new_tool_desc,
                trigger_reason=result.triggered_by,
            )
            task.reflection_count += 1
            reflection_log = result.to_dict()
            self.trace_store.record(self._record(task, trace, detail, reflection_log))
            print(
                f"[supervisor] {task.task_id}: reflection -> {result.version} "
                f"(cause: {result.root_cause[:60]}) -> rerun"
            )
            # loop again with the new latest prompt

    def _record(self, task, trace, detail, reflection_log, failed=False) -> dict:
        return {
            "task_id": task.task_id,
            "status": task.status,
            "worker_config_version": trace.worker_config_version,
            "metrics": detail["metrics"],
            "verdict": detail["verdict"],
            "reasons": detail["reasons"],
            "reflection_log": reflection_log,
            "output": trace.final_answer,
            "failed": failed,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _print_task(self, task_id, trace: Trace, detail: dict):
        m = detail["metrics"]
        tag = detail["verdict"]
        print(
            f"[task {task_id}] {tag} | {m['elapsed_ms']}ms | "
            f"steps {m['step_count']} | tok {m['token_total']} | "
            f"tools {m['tool_call_count']} | {trace.worker_config_version}"
        )
        if detail["reasons"]:
            for r in detail["reasons"]:
                print(f"    - {r}")

    def _print_summary(self):
        print("\n==== Supervisor run summary ====")
        print(f"tasks: {self.queue.summary()}")
        print(f"prompt versions: {[e['version'] for e in self.registry.entries]}")
        print(f"traces: {self.config.trace_store_file}")
