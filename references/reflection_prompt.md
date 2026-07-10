# 反思 Prompt 模板（Reflection & Prompt Tuner）

## 目标

给定「原始任务 + Worker 执行 Trace + 当前 System Prompt + 工具描述」，让反思 LLM（meta-critic）：

1. 做根因分析（Prompt 太模糊 / 工具描述诱导多余调用 / 任务拆解不合理）
2. 产出**修改后的 System Prompt**（更简洁、限制不必要工具调用、明确终止条件）
3. 可选：建议调整 `max_steps` 或切换模型等级

## System Prompt（固定）

```
You are a meta-critic that improves the System Prompt of a Worker Agent.
You receive the original task, the Worker's execution trace (timing, steps,
tool calls) and the current System Prompt. You must output STRICT JSON only,
no prose, in this schema:
{
  "root_cause": "<why the worker was slow / low-quality>",
  "new_system_prompt": "<improved, more concise prompt with explicit stop rule>",
  "new_tool_desc": null or "<trimmed tool description>",
  "suggestion": "<e.g. lower max_steps to 8 / switch to a lighter model>"
}
```

## User Prompt（填充）

```
# Original task
{task}

# Worker execution trace
- elapsed_ms: {elapsed_ms}
- step_count: {step_count} / max_steps {max_steps}
- input_tokens: {input_tokens}, output_tokens: {output_tokens}
- tool_call_sequence: {tool_seq}
- final_answer: {answer}
- error: {error}

# Why monitoring flagged this
{reasons}

# Current System Prompt
{current_prompt}

# Current tool description
{tool_desc}

Rewrite the System Prompt so the Worker finishes faster and with higher quality.
Return only the JSON object described in your instructions.
```

## 输出 schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `root_cause` | string | 退化根因 |
| `new_system_prompt` | string | 优化后的 System Prompt |
| `new_tool_desc` | string \| null | 精简后的工具描述（可选） |
| `suggestion` | string | 对 `max_steps` / 模型的调整建议 |

## 版本管理

- 调优后 Prompt 存入 Prompt Registry，带 `version` / `created_at` / `trigger_reason` / `eval_score`
- Supervisor 下次派发使用最新生效版本
- 保留基线 `v1` 用于 A/B 回滚

## 解析容错

若反思输出无法解析为 JSON，则保留原 Prompt 并附加解析失败的备注，保证闭环不中断。
