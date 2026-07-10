---
name: supervisor-agent
description: >
  性能感知 + 对话式提示词自动调优的 Supervisor Agent（CodeBuddy 原生）。当用户希望把一个任务列表交给
  一个"动态监督者"，由它派发给 Worker 子智能体执行，并在运行中监控耗时/步数/Token/工具调用，发现性能
  退化或质量偏差时自动触发反思、生成更优的 System Prompt 并动态重跑或影响后续任务时，应使用此 skill。
  即使用户只说"用 supervisor 跑这批任务""做个会自我调优的 agent""带性能监控的多 agent 编排"，也应触发。
---

# Supervisor Agent（性能感知 + 对话式提示词自动调优 · CodeBuddy 原生）

把一批任务交给一个**动态监督者**：它把任务派发给 CodeBuddy **Worker 子智能体**（`worker`）执行，
实时监控性能，发现退化就触发**对话式反思**——交给 **Reflector 子智能体**（`reflector`）产出更优的
System Prompt 并动态注入重跑或影响后续任务。**全程运行在 CodeBuddy 自身运行时上，不调用任何外部 LLM API。**

## 何时使用

- 用户有一组任务（可能带依赖/优先级）想批量交给 Agent 执行
- 用户关心执行效率（耗时、步数、Token、工具调用），希望系统自我优化
- 用户想要"会自己调提示词"的多 Agent 编排（CodeBuddy 子智能体格式）

## 核心组件（均为 CodeBuddy 原生）

- **Supervisor（你 / 本 skill）**：主智能体，负责编排闭环、状态机、监控阈值。
- **`worker` 子智能体**（`.codebuddy/agents/worker.md`）：执行单个任务，返回 `<<TRACE>>` 指标块。
- **`reflector` 子智能体**（`.codebuddy/agents/reflector.md`）：meta-critic，产出优化后的 Prompt。
- **`scripts/` 编排器**：可选，无头批量运行时通过 CodeBuddy CLI（`codebuddy -p`）驱动上述子智能体。

## 核心闭环

```
for each task in queue:
    1. Supervisor 取当前生效 System Prompt → 派发 worker 子智能体
    2. t0 = now(); worker.run(task) → Trace(<<TRACE>> 指标)
    3. Monitor 评估 Trace（latency / step / token / tool-call）
    4. if 指标正常:
          记录结果 → next task
       else:
         a. 派发 reflector 子智能体 → 新 Prompt
         b. 更新 prompt_registry.json（版本化）
         c. if 允许重跑: worker(新Prompt).run(task)
         d. next task（后续任务用新 Prompt）
结束当队列空
```

## 在 CodeBuddy 中执行步骤

### 阶段 0：准备（首次）

1. 确认任务列表（JSON：`task_id` / `description` / `priority` / `depends_on`）。无现成文件可参考
   `example_tasks.json` 帮用户生成。
2. 确认 `.codebuddy/agents/worker.md` 与 `reflector.md` 已就位（本 skill 自带）。
3. 可选：调整阈值（见末尾参数表）。

### 阶段 1：启动 Supervisor（两种方式，任选）

**方式 A — 无头脚本（推荐批量）**：直接用 Python 编排器，它内部通过 CodeBuddy CLI 调用子智能体，
无需外部 API：

```bash
cd supervisor-agent
python scripts/run.py --tasks example_tasks.json          # 经 codebuddy -p 调用子智能体
python scripts/run.py --tasks example_tasks.json --mock   # 离线自测（无需 CLI）
```

**方式 B — 交互式（本 skill 直接驱动）**：按下面的循环，对每个任务用 Task 工具派发 `worker` 子智能体，
反思时派发 `reflector` 子智能体。

### 阶段 2：观察与监控

每个任务完成后，Monitor 输出：
- `OK`：指标正常，记录并进入下一任务
- `NEED_REFLECTION`：某指标超阈值（延迟/步数耗尽/Token 膨胀/工具重复调用），触发反思
- `DEGRADED`：连续 N 次退化，建议降低并发或切换轻量模型

阈值与判定见 `references/metrics_spec.md`。

### 阶段 3：对话式反思与调优

触发反思时：
1. 派发 `reflector` 子智能体，输入「任务 + Trace + 当前 Prompt + 触发原因」
2. 它做根因分析并产出**更简洁、限制冗余工具调用、明确终止条件**的新 System Prompt（JSON）
3. 将新 Prompt 写入 `prompt_registry.json` 新版本（基线 v1 + 反思 v2...）
4. 用新 Prompt 重跑当前任务；后续任务自动采用最新版本
5. 若连续反思仍超标，标记 `FAILED_WITH_TUNING` 并继续（防死循环）

反思 Prompt 模板与输出 schema 见 `references/reflection_prompt.md`。

### 阶段 4：收尾与复盘

- `workspace/traces.jsonl`：每任务 metrics / verdict / reflection_log / output
- `workspace/prompt_registry.json`：各版本 Prompt 与触发原因，可 A/B 或回滚
- 向用户汇报：完成任务数、触发反思的任务、Prompt 演化、性能变化趋势

## 防死循环保护

- 单任务最多触发 `max_reflections_per_task` 次反思重跑（默认 ≤2）
- 连续反思仍超标 → `FAILED_WITH_TUNING`，继续下一任务
- 队列清空才退出（不结束不停止）

## 扩展方向

- **多 Worker 并行**：Supervisor Fan-out 并发，各自独立监控
- **质量触发反思**：加 LLM-as-Judge 对输出相关性/完整性评分
- **进化式调优**：维护 Prompt 种群，按成功率+耗时节 Pareto 筛选（参考 GEPA）
- **人机确认**：调优后 Prompt 经人工 Approve 才生效（生产建议）

## 参数（环境变量或 --flag）

| 参数 | 说明 | 默认 |
|------|------|------|
| `SUPERVISOR_CLI_COMMAND` / `--cli-command` | 无头模式调用的 CodeBuddy CLI 前缀 | `codebuddy -p` |
| `SUPERVISOR_WORKER_AGENT` | Worker 子智能体名 | `worker` |
| `SUPERVISOR_REFLECTOR_AGENT` | Reflector 子智能体名 | `reflector` |
| `SUPERVISOR_MAX_STEPS` / `--max-steps` | Worker 最大步数（指令+监控） | 12 |
| `SUPERVISOR_LATENCY_MS` / `--latency-ms` | 延迟阈值(ms) | 15000 |
| `SUPERVISOR_TOKEN_MULT` | Token p99 超倍触发 | 2.0 |
| `SUPERVISOR_TOOL_REPEAT` | 同工具连续调用阈值 | 5 |
| `SUPERVISOR_MAX_REFLECT` / `--max-reflect` | 单任务最大反思次数 | 2 |
| `SUPERVISOR_MOCK` / `--mock` | 离线 Mock（无需 CLI） | 0 |

## 参考文档

- `references/architecture.md` — 架构与状态图
- `references/reflection_prompt.md` — 反思 Prompt 模板
- `references/metrics_spec.md` — 指标与阈值规范
- `README.md` — 安装、运行、参数表
