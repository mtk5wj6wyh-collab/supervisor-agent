---
name: supervisor-agent
description: >
  性能感知 + 对话式提示词自动调优的 Supervisor Agent。当用户希望把一个任务列表交给一个"动态监督者"，
  由它派发给 Worker Agent 执行，并在运行中监控耗时/步数/Token/工具调用，发现性能退化或质量偏差时
  自动触发反思、生成更优的 System Prompt 并动态重跑或影响后续任务时，应使用此 skill。即使用户只说
  "用 supervisor 跑这批任务""做个会自我调优的 agent""带性能监控的多 agent 编排"，也应触发。
---

# Supervisor Agent（性能感知 + 对话式提示词自动调优）

把一批任务交给一个**动态监督者**：它派发给 Worker 执行，实时监控性能，发现退化就**对话式反思**
并自动改进提示词，再重跑或影响后续任务。整个过程直到队列清空才停止。

## 何时使用

- 用户有一组任务（可能带依赖/优先级）想批量交给 Agent 执行
- 用户关心执行效率（耗时、步数、Token、工具调用），希望系统自我优化
- 用户想要"会自己调提示词"的多 Agent 编排

## 核心闭环

```
for each task in queue:
    1. Supervisor 取当前生效 System Prompt → 创建/复用 Worker
    2. t0 = now(); Worker.run(task) → Trace
    3. Monitor.evaluate(Trace)
    4. if 指标正常:
          记录结果 → next task
       else:
         a. Reflection Module → 新 Prompt
         b. 更新 Prompt Registry（版本化）
         c. if 允许重跑: Worker(新Prompt).run(task)
         d. next task（后续任务用新 Prompt）
结束当队列空
```

## 在 CodeBuddy 中执行步骤

### 阶段 0：准备（首次）

1. 确认用户提供的任务列表（JSON，字段：`task_id` / `description` / `priority` / `depends_on`）。
   若无现成文件，参考 `example_tasks.json` 帮用户生成。
2. 确认运行方式：
   - **离线演示**：直接 `python scripts/run.py --tasks <file> --mock`
   - **真实 LLM**：检查环境变量 `SUPERVISOR_LLM_API_KEY` / `SUPERVISOR_LLM_BASE_URL` / `SUPERVISOR_LLM_MODEL`
     （缺失则提示用户配置后再跑）。
3. 可调整阈值：`--latency-ms` / `--max-steps` / `--max-reflect` 等（详见 `SKILL.md` 末尾或 `README.md`）。

### 阶段 1：启动 Supervisor

运行：

```bash
cd supervisor-agent
python scripts/run.py --tasks <任务文件> [--mock] [阈值参数...]
```

Supervisor 会：
- 把任务载入持久化队列（`workspace/task_queue.json`）
- 初始化 Prompt Registry 基线（`workspace/prompt_registry.json`）
- 按优先级+依赖逐个派发 Worker

### 阶段 2：观察与监控

每个任务完成后，Monitor 输出：
- `OK`：指标正常，记录并进入下一任务
- `NEED_REFLECTION`：某指标超阈值（延迟/步数耗尽/Token 膨胀/工具重复调用），触发反思
- `DEGRADED`：连续 N 次退化，建议降低并发或切换轻量模型

阈值与判定逻辑见 `references/metrics_spec.md`。

### 阶段 3：对话式反思与调优

当触发反思：
1. 反思 LLM（meta-critic）拿到 `任务 + Trace + 当前 Prompt`，做根因分析
2. 产出**更简洁、限制冗余工具调用、明确终止条件**的新 System Prompt
3. 写入 Prompt Registry 新版本（基线 v1 + 反思 v2...）
4. 用新 Prompt 重跑当前任务；后续任务自动采用最新版本
5. 若连续反思仍超标，标记 `FAILED_WITH_TUNING` 并继续（防死循环）

反思 Prompt 模板与输出 schema 见 `references/reflection_prompt.md`。

### 阶段 4：收尾与复盘

- 查看 `workspace/traces.jsonl`：每任务的 metrics / verdict / reflection_log / output
- 查看 `workspace/prompt_registry.json`：各版本 Prompt 与触发原因，可 A/B 或回滚
- 向用户汇报：完成任务数、触发反思的任务、Prompt 演化、性能变化趋势

## 防死循环保护

- 单任务最多触发 `max_reflections_per_task` 次反思重跑（默认 ≤2）
- 连续反思仍超标 → `FAILED_WITH_TUNING`，继续下一任务
- 队列清空才退出（不结束不停止）

## 扩展方向（按需实现）

- **多 Worker 并行**：Supervisor Fan-out 并发，各自独立监控
- **质量触发反思**：加 LLM-as-Judge 对输出相关性/完整性评分
- **进化式调优**：维护 Prompt 种群，按成功率+耗时节 Pareto 筛选（参考 GEPA）
- **人机确认**：调优后 Prompt 经人工 Approve 才生效（生产建议）

## 参考文档

- `references/architecture.md` — 架构与状态图
- `references/reflection_prompt.md` — 反思 Prompt 模板
- `references/metrics_spec.md` — 指标与阈值规范
- `README.md` — 安装、运行、参数表
