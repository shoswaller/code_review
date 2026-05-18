# 实现说明

本文档说明项目中主要实现模块的职责、关键函数和扩展方式。

## CLI 入口

`main.py` 负责命令行生命周期：

1. `parse_args()` 解析命令行参数。
2. `load_config()` 读取 `config.json`。
3. `_resolve_llm_kwargs()` 合并配置、环境变量和命令行参数。
4. `ChatOpenAI(**llm_kwargs)` 初始化 OpenAI 兼容模型。
5. 根据输入路径和 `--project` 选择单文件或项目模式。
6. 编译 LangGraph 并执行 `stream()` 或 `invoke()`。

单文件执行逻辑集中在 `_run()`，项目模式集中在 `run_project_review()`。

## 图构建

`setup.py` 中的 `build_workflow()` 构建单文件审查图：

- 为每个启用的分析师创建 Agent 节点、ToolNode 和 Clear 节点。
- 将分析师串联成流水线。
- 接入 Approve/Revise 辩论。
- 接入 Action Reviewer。
- 接入三方风险辩论。
- 最后由 Lead Reviewer 指向 `END`。

`build_project_workflow()` 只负责项目级架构分析节点；逐文件审查仍复用 `build_workflow()`。

`create_initial_state()` 负责初始化图运行状态，包含消息、报告字段、辩论状态、风险状态和历史上下文。

## 条件路由

`conditional_logic.py` 包含三类路由：

- 分析师工具循环：如果最后一条 AI 消息包含 `tool_calls`，进入对应 ToolNode，否则进入 Clear 节点。
- Approve/Revise 辩论：根据 `debate_state.count` 和当前发言方决定继续辩论或进入 Review Manager。
- 风险辩论：根据 `risk_debate_state.count` 和 `latest_speaker` 在三种风险角色之间轮转，达到轮数后进入 Lead Reviewer。

## 工具系统

`tools.py` 中所有工具使用 `@tool` 装饰，可被 LangGraph `ToolNode` 执行。

| 工具 | 作用 |
| --- | --- |
| `read_file` | 读取源码文件 |
| `count_lines` | 统计行数、函数数、类数和 import 数 |
| `find_pattern` | 按正则搜索代码模式 |
| `check_sql_injection` | 检测常见 SQL 拼接风险 |
| `list_project_files` | 列出项目文件 |
| `get_directory_structure` | 输出目录树 |
| `analyze_imports` | 分析 Python import 依赖 |
| `detect_project_type` | 根据配置文件识别技术栈 |

`ANALYST_TOOLS` 按角色分配工具，避免每个 Agent 拿到过宽权限。

## Agent 实现

`agents/analysts.py` 使用 `_create_analyst()` 创建四类分析师。每个分析师都绑定工具，并在没有工具调用时把最终内容写入对应报告字段。

`agents/researchers.py` 实现：

- `create_approve_researcher()`
- `create_revise_researcher()`
- `create_review_manager()`

Review Manager 优先使用 `llm.with_structured_output(ReviewPlan)`，失败时降级为普通文本。

`agents/reviewer.py` 实现 Action Reviewer，优先输出 `ActionPlan`。

`agents/risk_mgmt.py` 使用 `_create_risk_analyst()` 复用三种风险视角的发言逻辑。

`agents/lead_reviewer.py` 实现最终裁定，优先输出 `FinalDecision`。

## 结构化模型

`schemas.py` 定义核心数据结构：

- `ReviewFinding`
- `ReviewPlan`
- `ActionPlan`
- `FinalDecision`
- `ProjectOverview`
- `FileReviewSummary`
- `ProjectReviewReport`

同时提供 Markdown 渲染函数：

- `render_review_plan()`
- `render_action_plan()`
- `render_final_decision()`
- `render_project_report()`

结构化输出让后续 Agent 更容易消费上游结果，也方便最终报告生成。

## 记忆与断点

`ReviewMemory` 默认将历史记录保存到 `./data/review_history.json`。写入时使用临时文件和 `os.replace()`，降低写入中断导致 JSON 损坏的风险。

`checkpointer.py` 封装 LangGraph 的 `SqliteSaver`。启用 `--checkpoint` 后，同一个 `--thread-id` 可复用 SQLite 中的执行状态。

## 项目扫描与报告

`project_scanner.py` 负责：

- 按扩展名发现源码文件。
- 排除依赖、缓存、构建产物等目录。
- 统计文件数、行数、函数数、类数和语言分布。
- 生成目录树。

`project_reporter.py` 负责：

- 从单文件审查文本中解析问题数量和严重级别。
- 生成每个文件的摘要。
- 计算项目健康度。
- 汇总 Top 问题和建议。
- 渲染项目级 Markdown 报告。

## 扩展方式

### 新增分析师

1. 在 `agents/analysts.py` 中新增创建函数。
2. 在 `tools.py` 的 `ANALYST_TOOLS` 中配置工具。
3. 在 `setup.py` 的 `analyst_config` 中注册。
4. 在 `conditional_logic.py` 中增加对应路由函数，或复用 `_make_analyst_router()`。
5. 在 CLI `--analysts` choices 中加入新名称。

### 新增工具

1. 在 `tools.py` 中用 `@tool` 定义函数。
2. 将工具加入对应的 `ANALYST_TOOLS` 列表。
3. 调整 Agent prompt，让模型知道何时使用该工具。

### 调整辩论策略

- 修改 `--debate-rounds` 和 `--risk-rounds` 的默认值。
- 修改 `should_continue_debate()` 或 `should_continue_risk()` 的路由策略。
- 修改对应 Agent prompt 的立场和输出要求。
