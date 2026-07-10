# Supervisor Agent — 性能感知 + 对话式提示词自动调优

一个动态监督者（Dynamic Supervisor）Agent：按顺序/优先级把任务派发给 Worker Agent，运行中实时监控
**耗时 / 步数 / Token / 工具调用次数**，并在检测到性能退化或质量偏差时触发**对话式反思（Reflection）**，
由反思模块产出更优的 System Prompt / 工具描述 / 策略参数，动态注入 Worker 后重跑或影响后续任务。

> 本仓库已适配为 **CodeBuddy Skill** 格式。安装后可在 CodeBuddy 中直接调用，也可作为独立 Python 程序运行。

## 架构分层

```
任务输入层 → Supervisor 控制面(Orchestrator) → Worker 执行面 → Monitor 观测层 → Reflection 调优层
```

- **任务输入层**：批量任务列表（task_id / description / priority / depends_on），持久化队列。
- **Supervisor 控制面**：Router + 状态机（PENDING→RUNNING→DONE/FAILED）+ 熔断/超时/重试。
- **Worker 执行面**：受约束 ReAct 循环，返回结构化 Trace。
- **Monitor 观测层**：latency / step / token / tool-call 阈值判定，输出 OK / NEED_REFLECTION / DEGRADED。
- **Reflection 调优层**：Reflexion 模式 + LLM-as-Meta-Critic，产出版本化 System Prompt 存入 Prompt Registry。

## 快速开始

### 方式一：作为独立 Python 程序运行

```bash
cd supervisor-agent
pip install -r requirements.txt

# 离线演示（无需 API key）
python scripts/run.py --tasks example_tasks.json --mock

# 使用真实 LLM
export SUPERVISOR_LLM_API_KEY=sk-xxx
export SUPERVISOR_LLM_BASE_URL=https://api.openai.com/v1
export SUPERVISOR_LLM_MODEL=gpt-4o-mini
python scripts/run.py --tasks example_tasks.json
```

### 方式二：在 CodeBuddy 中使用

安装本 Skill 后，在 CodeBuddy 对话中说：

```
用 supervisor-agent 跑 example_tasks.json，开启性能监控与自动调优
```

Skill 会按 `SKILL.md` 的流程启动 Supervisor，自动驱动 Worker、Monitor 与 Reflection 闭环。

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
| `SUPERVISOR_LLM_MODEL` | Worker 模型 | gpt-4o-mini |
| `SUPERVISOR_REFLECTION_MODEL` | 反思模型（可更强） | 同 Worker |
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
├── SKILL.md                  # CodeBuddy Skill 主文件（执行流程）
├── README.md
├── requirements.txt
├── example_tasks.json        # 示例任务
├── scripts/
│   ├── run.py                # 入口
│   └── agent/                # 实现包
│       ├── models.py         # Task / Trace / ReflectionResult / Verdict
│       ├── config.py         # 阈值与端点配置
│       ├── llms.py           # LLM 客户端（含 Mock）
│       ├── task_queue.py     # 优先级 + 依赖队列
│       ├── worker.py         # 受约束 ReAct Worker
│       ├── monitor.py        # 性能观测与阈值判定
│       ├── reflection.py     # 对话式反思 + 提示词调优
│       ├── prompt_registry.py# 版本化 Prompt 管理
│       ├── trace_store.py    # JSONL 执行日志
│       ├── supervisor.py     # 编排闭环
│       └── cli.py            # 命令行
└── references/
    ├── architecture.md       # 架构与状态图
    ├── reflection_prompt.md  # 反思 Prompt 模板
    └── metrics_spec.md       # 指标与阈值规范
```
