# 架构与状态图

## 分层

```
┌─────────────────────────────────────┐
│          任务输入层                  │
│  任务列表 / 优先级队列 / 持久化      │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│       Supervisor 控制面（Orchestrator）│
│  • 任务分发 Router                   │
│  • 状态机 Scheduler（PENDING/RUNNING/DONE/FAILED）│
│  • 熔断 / 超时 / 最大重试控制         │
│  • 汇聚 Worker 返回结果               │
└──────────────┬──────────────────────┘
               ↓ 派发子任务 + 当前 Worker Config
┌─────────────────────────────────────┐
│         Worker Agent 执行面          │
│  • ReAct / CoT 循环                  │
│  • Tool Calling                      │
│  • 受控 max_steps / timeout          │
│  • 返回 Trace（耗时/步数/Token/输出）  │
└──────────────┬──────────────────────┘
               ↓ Trace + Metrics
┌─────────────────────────────────────┐
│        Monitor & Evaluator（观测层）  │
│  • 指标采集：latency / steps / tokens │
│  • SLOW / DEGRADE 阈值判定           │
│  • 可选：LLM-as-Judge 质量评分        │
└──────────────┬──────────────────────┘
               ↓ 触发条件满足
┌─────────────────────────────────────┐
│      Reflection & Prompt Tuner（调优层）│
│  • 输入：Task + Trace + 当前 Prompt   │
│  • LLM 反思"为何变慢/效果差"          │
│  • 输出：优化后 Prompt / 工具精简 / max_steps 建议 │
│  • 写入 Prompt Registry 版本化        │
└─────────────────────────────────────┘
```

## 单任务状态机

```
        ┌─────────┐
        │ PENDING │──(deps ok & top priority)──→ RUNNING
        └─────────┘                              │
                                                 │ Worker.run
                                                 ↓
                                            Monitor.eval
                                           /          \
                                      OK  /            \ 超阈值
                                         /              \
                                    DONE            Reflection
                                                       │ 新 Prompt
                                                       │ (count<max)
                                                       ↓
                                                  rerun (RUNNING)
                                                       │
                                            still over → FAILED_WITH_TUNING
```

## Supervisor 主循环（伪代码）

```python
while queue.has_pending():
    task = queue.pop_next()          # 优先级 + 依赖
    while True:
        prompt, tool_desc = registry.latest()
        trace = worker.run(task, prompt, tool_desc)
        verdict, detail = monitor.evaluate(trace)
        if verdict == OK:
            task.status = DONE; break
        if not enable_reflection or task.reflection_count >= max_reflect:
            task.status = FAILED_WITH_TUNING; break
        result = reflection.reflect(task, trace, prompt, tool_desc, detail.reasons)
        registry.add(result.new_system_prompt, result.new_tool_desc, result.triggered_by)
        task.reflection_count += 1
        # loop again with the new latest prompt (rerun)
```

## 推荐技术选型（CodeBuddy 原生）

| 层 | 采用 |
|----|------|
| 编排/Supervisor | 本仓库 CodeBuddy Skill + 无头 Python 编排器（调用 `codebuddy -p`） |
| Worker Agent | CodeBuddy 子智能体 `worker`（`.codebuddy/agents/worker.md`） |
| 反思 LLM | CodeBuddy 子智能体 `reflector`（meta-critic） |
| Trace & 日志 | 本仓库 JSONL + 文件 |
| Prompt 版本化 | 本仓库 `prompt_registry.json` |
