# Supervisor Agent — 性能感知 + 对话式提示词自动调优（CodeBuddy 原生）

一个动态监督者（Dynamic Supervisor）Agent：按顺序/优先级把任务派发给 **Worker 子智能体**执行，
运行中实时监控 **耗时 / 步数 / Token / 工具调用次数**，并在检测到性能退化或质量偏差时触发**对话式反思**，
由 Reflector 子智能体产出更优的 System Prompt / 工具描述 / 策略参数，动态注入 Worker 后重跑或影响后续任务。

> **完全运行在 CodeBuddy 自身运行时上，不调用任何外部 LLM API。** Supervisor 是 CodeBuddy 主智能体，
> Worker / Reflection 是 CodeBuddy **子智能体**（`.codebuddy/agents/`），符合 CodeBuddy 原生格式。

## 架构分层

```
任务输入层 → Supervisor 主智能体(Orchestrator) → Worker 子智能体 → Monitor 观测层 → Reflector 子智能体
```

- **任务输入层**：批量任务列表（task_id / description / priority / depends_on），持久化队列。
- **Supervisor 主智能体**：Router + 状态机（PENDING→RUNNING→DONE/FAILED）+ 熔断/超时/重试。
- **Worker 子智能体**：执行单任务，返回 `<<TRACE>>` 指标块。
- **Monitor 观测层**：latency / step / token / tool-call 阈值判定，输出 OK / NEED_REFLECTION / DEGRADED。
- **Reflector 子智能体**：Reflexion 模式 + meta-critic，产出版本化 System Prompt。

## 快速开始

本仓库已适配为 **CodeBuddy Skill**。安装后可在 CodeBuddy 中直接调用；也提供无头脚本批量运行。

### 1. 作为 CodeBuddy Skill 使用（推荐）

将本目录作为 Skill 安装（或放到项目的 `.codebuddy/skills/supervisor-agent/`），并确保
`.codebuddy/agents/worker.md` 与 `reflector.md` 就位。然后在 CodeBuddy 对话中说：

```
用 supervisor-agent 跑 example_tasks.json，开启性能监控与自动调优
```

CodeBuddy 会按 `SKILL.md` 的流程启动 Supervisor，自动派发 `worker` / `reflector` 子智能体形成闭环。

### 2. 无头批量运行（脚本驱动 CodeBuddy CLI）

```bash
cd supervisor-agent
pip install -r requirements.txt          # tiktoken 可选

# 离线演示（无需 CodeBuddy CLI）
python .codebuddy/skills/supervisor-agent/scripts/run.py --tasks example_tasks.json --mock

# 真实运行：脚本通过 `codebuddy -p` 调用子智能体（无外部 API）
python .codebuddy/skills/supervisor-agent/scripts/run.py --tasks example_tasks.json
```

## 输出与可观测性

运行后 `workspace/` 下生成：

```
workspace/
├── task_queue.json        # 任务状态（可断点续跑）
├── prompt_registry.json   # 版本化 System Prompt（含基线 v1 + 反思产出）
└── traces.jsonl           # 每任务 Trace：metrics / verdict / reflection_log / output
```

## 关键参数（环境变量或 --flag）

| 参数 | 说明 | 默认 |
|------|------|------|
| `SUPERVISOR_CLI_COMMAND` | 无头模式调用的 CodeBuddy CLI 前缀 | `codebuddy -p` |
| `SUPERVISOR_WORKER_AGENT` | Worker 子智能体名 | `worker` |
| `SUPERVISOR_REFLECTOR_AGENT` | Reflector 子智能体名 | `reflector` |
| `SUPERVISOR_MAX_STEPS` | Worker 最大步数 | 12 |
| `SUPERVISOR_LATENCY_MS` | 延迟阈值(ms) | 15000 |
| `SUPERVISOR_TOKEN_MULT` | Token p99 超倍触发 | 2.0 |
| `SUPERVISOR_TOOL_REPEAT` | 同工具连续调用阈值 | 5 |
| `SUPERVISOR_MAX_REFLECT` | 单任务最大反思次数 | 2 |
| `SUPERVISOR_MOCK` | 离线 Mock 模式 | 0 |

## 防死循环保护

- 单任务最多触发 `max_reflections_per_task` 次反思重跑（默认 ≤2）。
- 若连续反思后仍超标，标记 `FAILED_WITH_TUNING` 并继续下一任务。
- 队列清空才退出（符合"不结束不停止"要求）。

## 目录结构

```
supervisor-agent/
├── README.md / requirements.txt / LICENSE
├── example_tasks.json            # 示例任务
└── .codebuddy/
    ├── skills/
    │   └── supervisor-agent/      # CodeBuddy Skill（IDE 自动加载）
    │       ├── SKILL.md           # Skill 主文件（执行流程 / 触发条件）
    │       ├── scripts/
    │       │   ├── run.py         # 入口（无头编排，调用 CodeBuddy CLI）
    │       │   └── agent/         # 实现包
    │       │       ├── models.py             # Task / Trace / ReflectionResult / Verdict
    │       │       ├── config.py             # 配置（CodeBuddy CLI / 阈值，无外部 API）
    │       │       ├── llms.py               # CodeBuddyRunner（调用 codebuddy CLI + mock）
    │       │       ├── task_queue.py         # 优先级 + 依赖队列
    │       │       ├── worker.py             # Worker：派发子智能体 + 解析 <<TRACE>>
    │       │       ├── monitor.py            # 性能观测与阈值判定
    │       │       ├── reflection.py         # 对话式反思 + 提示词调优
    │       │       ├── prompt_registry.py    # 版本化 Prompt 管理
    │       │       ├── trace_store.py        # JSONL 执行日志
    │       │       ├── supervisor.py         # 编排闭环
    │       │       └── cli.py                # 命令行
    │       └── references/
    │           ├── architecture.md           # 架构与状态图
    │           ├── reflection_prompt.md      # 反思 Prompt 模板
    │           └── metrics_spec.md           # 指标与阈值规范
    └── agents/
        ├── worker.md             # Worker 子智能体（CodeBuddy 原生格式）
        └── reflector.md          # Reflector 子智能体（meta-critic）
```

## 推荐技术选型（CodeBuddy 原生）

| 层 | 采用 |
|----|------|
| 编排/Supervisor | 本仓库 CodeBuddy Skill + 无头 Python 编排器（调用 `codebuddy -p`） |
| Worker Agent | CodeBuddy 子智能体 `worker`（`.codebuddy/agents/worker.md`） |
| 反思 LLM | CodeBuddy 子智能体 `reflector`（meta-critic） |
| Trace & 日志 | 本仓库 JSONL + 文件 |
| Prompt 版本化 | 本仓库 `prompt_registry.json` |
