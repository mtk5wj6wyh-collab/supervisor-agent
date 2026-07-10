# 指标与阈值规范（Monitor & Evaluator）

## 采集指标

| 指标 | 来源 | 说明 |
|------|------|------|
| Latency | `Trace.elapsed_ms` | 端到端耗时 |
| Step Count | `Trace.step_count` | Agent 循环步数 |
| Token | `input_tokens + output_tokens` | 单任务总消耗 |
| Tool Calls | `Trace.tool_call_sequence` | 工具调用序列 |

## 触发阈值

| 指标 | 触发条件 | 示例 |
|------|----------|------|
| Latency | `elapsed_ms > latency_threshold_ms` | > 15000ms |
| Step Count | `step_count >= max_steps` | 疑似死循环 |
| Token | `token_total > p99 * token_p99_multiplier` | p99 基线 2 倍 |
| Tool Calls | 同工具连续调用 `>= tool_repeat_threshold` | 重复调用同工具 |

## 判定逻辑

1. 任一指标超阈值 → 标记 `NEED_REFLECTION`
2. 连续 `degrade_consecutive` 次退化 → 标记 `DEGRADED`（建议降低并发/切换轻量模型）
3. 无超阈值 → `OK`，并把该次 latency/token 纳入基线（p99 滚动）

## 基线维护

- baseline 仅在**干净运行**（无 error 且未耗尽步数）时更新，保证 p99 不被退化样本污染
- p99 用排序取近似值：`sorted[k]`, `k = round(0.99*(n-1))`

## 可观测性存储

- `traces.jsonl`：每任务 `{task_id, worker_config_version, metrics, verdict, reasons, reflection_log, output}`
- 可选 Dashboard：p50/p90/p99 latency、平均步数、Token 趋势、Prompt 版本效果对比

## 防死循环保护

- 单任务最多触发 `max_reflections_per_task` 次反思重跑（建议 ≤2）
- 连续反思仍超标 → `FAILED_WITH_TUNING` 并继续下一任务
- 队列清空才退出
