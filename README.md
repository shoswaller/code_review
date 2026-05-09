<<<<<<< HEAD
# code_review_agents
## 注意：该项目大量使用vibe coding
## 该项目参照了TradingAgents多智能体设计思路 https://github.com/TauricResearch/TradingAgents
=======
# Code Review 多智能体系统

基于 LangGraph 的五层多智能体代码审查系统。输入一个代码文件，四个专业分析师分别从风格、安全、性能、逻辑角度进行审查，经过两轮三方辩论后输出结构化裁定。

## 项目架构

```
输入: 代码文件路径
  │
  ▼
┌─ 第一层: 分析师团队 ─────────────────────────────────────┐
│  Style Analyst       Security Analyst                    │
│  Performance Analyst Logic Analyst                       │
│  每个分析师 ↔ 独立工具节点 (ReAct 循环)                    │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ 第二层: 研究辩论 ───────────────────────────────────────┐
│  Approve Researcher ↔ Revise Researcher (N 轮辩论)       │
│  → Review Manager (结构化输出: ReviewPlan)                │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ 第三层: 行动方案 ───────────────────────────────────────┐
│  Action Reviewer (结构化输出: ActionPlan)                 │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ 第四层: 风险评估 ───────────────────────────────────────┐
│  FastMerge ↔ QualityFirst ↔ Balanced (N 轮三方辩论)       │
└──────────────────────────────────────────────────────────┘
  │
  ▼
┌─ 第五层: 最终裁定 ───────────────────────────────────────┐
│  Lead Reviewer (结构化输出: FinalDecision)                │
│  输出: Approve / Request Changes / Reject                │
└──────────────────────────────────────────────────────────┘
  │
  ▼
输出: 完整审查报告 + 持久化记忆
```

## 项目结构

```
code_review/
├── main.py                 # CLI 入口，参数解析，流程调度
├── setup.py                # StateGraph 构建，状态初始化
├── state.py                # 全局状态类型定义
├── schemas.py              # Pydantic 结构化输出模型
├── tools.py                # 代码分析工具（@tool 装饰器）
├── conditional_logic.py    # 图的条件路由判定函数
├── memory.py               # 审查记忆持久化
├── checkpointer.py         # SQLite 断点续传
├── test_target.py          # 用于测试的示例文件（含故意植入问题）
└── agents/
    ├── __init__.py          # Agent 工厂函数统一导出
    ├── analysts.py          # 第一层: 风格/安全/性能/逻辑分析师
    ├── researchers.py       # 第二层: Approve/Revise研究员 + Review Manager
    ├── reviewer.py          # 第三层: Action Reviewer
    ├── risk_mgmt.py         # 第四层: FastMerge/QualityFirst/Balanced
    ├── lead_reviewer.py     # 第五层: Lead Reviewer
    └── utils.py             # 消息清除等辅助函数
```

---

## 文件详解

### state.py —— 全局状态定义

定义三种 `TypedDict`，是整张图所有节点共享的"全局变量"：

| 类型 | 说明 |
|------|------|
| `AgentState` | 继承 `MessagesState`，包含所有中间报告、辩论状态、最终裁定 |
| `DebateState` | Approve/Revise 辩论的跟踪状态（历史、当前发言者、轮次计数） |
| `RiskDebateState` | 三方风险评估的跟踪状态（各方历史、最新发言者、轮次计数） |

**关键字段**：`style_report` / `security_report` / `performance_report` / `logic_report`（四个分析师输出）、`debate_state`（辩论控制）、`action_plan`（修改方案）、`risk_debate_state`（风险讨论）、`final_decision`（最终裁定）、`past_context`（历史记忆注入）。

**对比 TradingAgents**: `tradingagents/agents/utils/agent_states.py` 中的 `AgentState` + `InvestDebateState` + `RiskDebateState`。

---

### tools.py —— 代码分析工具

定义 4 个 LangChain `@tool` 工具，供 ToolNode 自动调度：

| 工具 | 功能 | 使用场景 |
|------|------|---------|
| `read_file` | 读取文件完整内容 | 所有分析师的入口工具 |
| `count_lines` | 统计行数、函数、类、导入模块 | 风格、性能分析师了解代码规模 |
| `find_pattern` | 正则搜索，返回匹配行与行号 | 搜索 `eval`、`except:`、硬编码密钥等 |
| `check_sql_injection` | 检测 f-string/+ 拼接 SQL、`.format()` 拼接 | 安全分析师专用 |

工具按职责分组的字典 `ANALYST_TOOLS` 用于图构建时为每个分析师绑定专属工具集，类比 TradingAgents 的 `_create_tool_nodes`。

**对比 TradingAgents**: `tradingagents/agents/utils/core_stock_tools.py` 等工具定义文件 + `trading_graph.py` 中的 `_create_tool_nodes()`。

---

### schemas.py —— 结构化输出模型

定义 3 个 Pydantic `BaseModel`，用于 LLM 的 `with_structured_output` 调用：

| Model | 字段 | 使用者 |
|-------|------|--------|
| `ReviewPlan` | `recommendation`、`summary`、`findings[]`、`must_fix[]`、`nice_to_have[]` | Review Manager（第二层裁决） |
| `ActionPlan` | `action`、`reasoning`、`changes[]`、`estimated_effort` | Action Reviewer（第三层） |
| `FinalDecision` | `verdict`、`executive_summary`、`review_thesis`、`risk_assessment`、`time_estimate` | Lead Reviewer（第五层） |

附带 3 个 `render_*()` 函数，将 Pydantic 对象渲染为 Markdown 字符串，供下游 LLM 消费。

**对比 TradingAgents**: `tradingagents/agents/schemas.py` 中的 `ResearchPlan` + `TraderProposal` + `PortfolioDecision`。

---

### conditional_logic.py —— 条件路由逻辑

图不是静态顺序执行的——每个分析师需要在"分析"和"调工具"之间循环，辩论需要交替发言并在达到上限时终止。这些动态决策由条件函数处理：

| 函数 | 用途 | 返回节点名 |
|------|------|-----------|
| `should_continue_style()` | Style 分析师的路由 | `"tools_style"` 或 `"Clear Style"` |
| `should_continue_security()` | Security 分析师的路由 | `"tools_security"` 或 `"Clear Security"` |
| `should_continue_performance()` | Performance 分析师的路由 | `"tools_performance"` 或 `"Clear Performance"` |
| `should_continue_logic()` | Logic 分析师的路由 | `"tools_logic"` 或 `"Clear Logic"` |
| `should_continue_debate()` | Approve/Revise 辩论路由 | `"Revise Researcher"` / `"Approve Researcher"` / `"Review Manager"` |
| `should_continue_risk()` | 风险三方辩论路由 | `"Quality First"` / `"Balanced"` / `"Fast Merge"` / `"Lead Reviewer"` |

**核心规则**：
- 分析师路由：消息末尾有 `tool_calls` → 工具节点；纯文本 → 清除节点（报告完成）
- 辩论路由：`count >= 2 * max_rounds` → 裁判节点；否则交替发言者

前四个函数由 `_make_analyst_router` 工厂统一生成，避免重复代码。

**对比 TradingAgents**: `tradingagents/graph/conditional_logic.py` 中的 `ConditionalLogic` 类的 6 个 `should_continue_*` 方法。

---

### setup.py —— 图构建

这是整个项目的**核心文件**，负责用 LangGraph 的 `StateGraph` API 搭建完整的五层审查图。

**`build_workflow(llm, selected_analysts, max_debate_rounds, max_risk_rounds)`**：

1. **第一层——分析师管道**：遍历 `selected_analysts` 列表，为每个分析师：
   - 添加分析师 LLM 节点
   - 添加消息清除节点
   - 添加专属工具节点
   - 设置 `add_conditional_edges`（分析师-工具循环）和 `add_edge`（工具→分析师回环）
   - 串联到下一个分析师或进入辩论

2. **第二层——研究辩论**：添加 Approve/Revise 研究员和 Review Manager。双向条件边形成交替辩论，`lambda` 注入 `max_rounds` 参数控制终止。

3. **第三层——行动方案**：单向边连接 Review Manager → Action Reviewer。

4. **第四层——风险评估**：添加 FastMerge/QualityFirst/Balanced 和 Lead Reviewer。三向条件边形成循环辩论。

5. **第五层——最终裁定**：Lead Reviewer → END。

**`create_initial_state(file_path, past_context)`**：创建图的初始状态字典，所有报告字段为空，辩论计数器归零。

**对比 TradingAgents**: `tradingagents/graph/setup.py` 的 `GraphSetup.setup_graph()` + `tradingagents/graph/propagation.py` 的 `Propagator.create_initial_state()`。

---

### agents/analysts.py —— 第一层：分析师

四个专业分析师，每个都是一个**LLM + 工具**的 ReAct Agent：

| 分析师 | 关注维度 | 绑定工具 |
|--------|---------|---------|
| Style Analyst | 命名规范、代码格式、注释质量、代码组织 | read_file、count_lines、find_pattern |
| Security Analyst | 注入风险、危险函数、硬编码密钥、路径遍历、不安全反序列化 | read_file、find_pattern、check_sql_injection |
| Performance Analyst | 算法复杂度、不必要I/O、内存使用、字符串拼接、缓存机会 | read_file、count_lines、find_pattern |
| Logic Analyst | 边界条件、异常处理、类型安全、流程控制、并发安全 | read_file、find_pattern、count_lines |

由 `_create_analyst` 工厂统一创建：`llm.bind_tools(tools)` → `prompt | llm_with_tools` → 节点函数。每个分析师有量身定制的 system prompt 和固定的输出格式要求。

**对比 TradingAgents**: `tradingagents/agents/analysts/` 目录下的四个文件。

---

### agents/researchers.py —— 第二层：研究辩论

**Approve Researcher**（多头方）：基于四条分析师报告，论证代码应该被批准合入。如果是首轮则提出核心论点，如果 Revise 方已发言则逐一反驳。每次发言后更新 `debate_state`（count+1、追加历史、设置当前响应）。

**Revise Researcher**（空头方）：论证代码需要修改后才能合入。结构与 Approve 对称，方向相反。

**Review Manager**（裁判）：辩论终结后，审阅全部辩论记录和四份报告，做出裁定。优先尝试 `with_structured_output(ReviewPlan)`，失败时自动降级为自由文本。

**对比 TradingAgents**: `tradingagents/agents/researchers/bull_researcher.py` + `bear_researcher.py` + `tradingagents/agents/managers/research_manager.py`。

---

### agents/reviewer.py —— 第三层：行动方案

将 Review Manager 的审查计划（问题列表、严重度、分类）转化为具体的代码修改步骤。输出格式为每行一个可操作的修改指令（`[文件:行号] 具体修改内容`），并预估修改工作量。

**对比 TradingAgents**: `tradingagents/agents/trader/trader.py`。

---

### agents/risk_mgmt.py —— 第四层：风险评估

三方不同风险偏好的角色进行循环辩论：

| 角色 | 立场 | 核心论点 |
|------|------|---------|
| Fast Merge Analyst | 快速合入 | 过度审查导致延迟，Minr问题可后续修复 |
| Quality First Analyst | 质量优先 | 低质量合入代价远大于延迟，问题必须现在修复 |
| Balanced Analyst | 平衡 | 区分阻塞/非阻塞问题，基于实际影响而非理论 |

由 `_create_risk_analyst` 工厂统一创建，通过 `latest_speaker` 实现三方交替。

**对比 TradingAgents**: `tradingagents/agents/risk_mgmt/` 目录下的三个文件。

---

### agents/lead_reviewer.py —— 第五层：最终裁定

首席审查官。拥有**完整的决策上下文**——四份分析师报告、辩论记录、审查计划、行动方案、风险讨论、历史审查记录——做出最终裁定（Approve / Request Changes / Reject），附带风险等级和预估修复时间。

**对比 TradingAgents**: `tradingagents/agents/managers/portfolio_manager.py`。

---

### agents/utils.py —— 辅助函数

**`create_msg_clear()`**：生成消息清除节点。每个分析师执行完成后，中间产生的工具调用消息会消耗大量 token。清除节点保留初始指令和分析师的最终报告，使下一个分析师能以干净的上下文开始分析。

**对比 TradingAgents**: `tradingagents/agents/utils/agent_utils.py` 中的 `create_msg_delete()`。

---

### memory.py —— 审查记忆

`ReviewMemory` 类提供基于 JSON 文件的持久化记忆，模仿 TradingAgents 的两阶段机制：

- **阶段 A（存储）**：审查完成后，调用 `save_review()` 追加记录
- **阶段 B（注入）**：下次审查时，调用 `get_past_context()` 检索同文件历史 + 跨文件参考，注入到 Lead Reviewer 的 system prompt 中

使用临时文件 + `os.replace()` 实现原子写入，避免并发损坏。支持按文件过滤、按数量限制。

**对比 TradingAgents**: `tradingagents/agents/utils/memory.py` 中的 `TradingMemoryLog`。

---

### checkpointer.py —— 断点续传

对 LangGraph 原生 `SqliteSaver` 的薄封装，提供上下文管理器接口：

```python
with get_checkpointer("data/checkpoints.db") as saver:
    app = workflow.compile(checkpointer=saver)
    app.invoke(state, {"configurable": {"thread_id": "my-review"}})
```

同一个 `thread_id` 中断后重新运行会从上次成功的节点恢复，不同 `thread_id` 互不干扰。

**对比 TradingAgents**: `tradingagents/graph/checkpointer.py`。

---

### main.py —— CLI 入口

负责参数解析、LLM 初始化、图编译、流式执行、结果展示。支持：

- 命令行参数控制所有选项（分析师选择、辩论轮数、断点续传、模型等）
- 交互式输入文件路径（无参数时）
- `graph.stream()` 流式输出，实时显示每个节点的执行进度
- 记忆系统自动加载历史上下文
- 审查结果自动存入持久化记忆

**对比 TradingAgents**: `cli/main.py`。

---

## 处理流程

### 完整执行流程

```
python -m code_review.main path/to/file.py
    │
    ▼
1. 参数解析 + LLM 初始化
    │
    ▼
2. 记忆加载 (记忆阶段B)
   ReviewMemory.get_past_context() → 检索同文件历史 + 其他文件参考
    │
    ▼
3. 状态初始化
   create_initial_state(file_path, past_context) → 所有字段空白，计数器归零
    │
    ▼
4. 图编译
   build_workflow(llm, analysts, rounds).compile()
    │  (可选: 叠加 SqliteSaver 支持断点续传)
    ▼
5. 图执行 (stream/invoke)
    │
    ├── 第一层: 分析师管道
    │   │
    │   ├── Style Analyst ──读文件 → 统计 → 搜索模式──→ 生成风格报告
    │   │       ↓ (消息清除)
    │   ├── Security Analyst ──读文件 → SQL检测 → 搜索危险模式──→ 生成安全报告
    │   │       ↓ (消息清除)
    │   ├── Performance Analyst ──读文件 → 统计 → 搜索瓶颈──→ 生成性能报告
    │   │       ↓ (消息清除)
    │   └── Logic Analyst ──读文件 → 搜索模式 → 分析流程──→ 生成逻辑报告
    │   │
    │   ├── 第二层: 研究辩论
    │   │   Approve Researcher ←→ Revise Researcher (N 轮)
    │   │           ↓ (count > 2*max_rounds)
    │   │   Review Manager → 结构化输出: ReviewPlan
    │   │
    │   ├── 第三层: 行动方案
    │   │   Action Reviewer → 结构化输出: ActionPlan
    │   │
    │   ├── 第四层: 风险评估
    │   │   FastMerge → QualityFirst → Balanced → (循环 N 轮)
    │   │           ↓ (count > 3*max_rounds)
    │   │
    │   └── 第五层: 最终裁定
    │       Lead Reviewer → 结构化输出: FinalDecision
    │
    ▼
6. 结果展示 (流式模式下实时打印每个节点的输出)
    │
    ▼
7. 记忆存储 (记忆阶段A)
   ReviewMemory.save_review(verdict, findings_count, risk_level)
    │
    ▼
8. 返回: 最终裁定 (Approve / Request Changes / Reject) + 完整审查报告
```

### 单分析师 ReAct 循环

每个分析师节点的执行流程是典型的 ReAct（Reasoning + Acting）循环：

```
Style Analyst (LLM)
    │
    ├── 消息中有 tool_calls ──→ 路由到 tools_style (ToolNode)
    │                                │
    │    read_file / count_lines /    │
    │    find_pattern 执行             │
    │                                │
    │    ←───── 结果返回 ─────────────┘
    │         (再次进入 Analyst)
    │
    └── 消息中没有 tool_calls ──→ 路由到 Clear Style
                                      │
                                  清除中间消息，
                                  保留初始 prompt + 最终报告
                                      │
                                  下一个节点
```

### 辩论循环详细机制

以 Approve/Revise 辩论为例：

```
Round 1:
  state["debate_state"]["count"] = 0
  Approve Researcher 发言 → count=1, current_response="Approve: ..."
    → router 检查: count(1) < 2*max_rounds(4), 且 current_response 以 "Approve" 开头
    → 返回 "Revise Researcher"

  Revise Researcher 发言 → count=2, current_response="Revise: ..."
    → router 检查: count(2) < 4, 以 "Revise" 开头
    → 返回 "Approve Researcher"

Round 2:
  Approve Researcher 发言 → count=3
    → 返回 "Revise Researcher"
  Revise Researcher 发言 → count=4
    → router 检查: count(4) >= 2*max_rounds(4)
    → 返回 "Review Manager" (辩论终止)
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 图编排 | LangGraph StateGraph + 条件路由 |
| LLM 集成 | langchain-openai（兼容所有 OpenAI 格式端点） |
| 工具系统 | LangChain `@tool` + `ToolNode` |
| 结构化输出 | Pydantic v2 + `with_structured_output` |
| 断点续传 | SQLite + `SqliteSaver` |
| 持久化 | JSON 文件 + 原子写入（`os.replace`） |
| CLI | argparse + `graph.stream()` |

---

## 使用指南

```bash
# 安装依赖
pip install langgraph langchain-core langchain-openai langgraph-checkpoint-sqlite pydantic

# 设置 API Key
export OPENAI_API_KEY=your-key-here

# 基本用法
python -m code_review.main test_target.py

# 选择分析师
python -m code_review.main test.py --analysts style security

# 增加辩论深度
python -m code_review.main test.py --debate-rounds 3 --risk-rounds 3

# 断点续传
python -m code_review.main test.py --checkpoint --thread-id review-v1

# 非流式
python -m code_review.main test.py --no-stream

# 使用 Ollama 本地模型
python -m code_review.main test.py --base-url http://localhost:11434/v1 --model llama3

# 查看图结构
python -m code_review.main --dry-run

# 交互模式（不带文件参数）
python -m code_review.main
```

---

## 与 TradingAgents 的架构对应关系

| TradingAgents | Code Review Agent |
|---------------|-------------------|
| 市场/社媒/新闻/基本面分析师 | 风格/安全/性能/逻辑分析师 |
| `get_stock_data` / `get_indicators` 等工具 | `read_file` / `find_pattern` / `check_sql_injection` |
| 多头 ↔ 空头研究员（投资辩论） | Approve ↔ Revise 研究员（合入辩论） |
| Research Manager → `ResearchPlan` | Review Manager → `ReviewPlan` |
| Trader → `TraderProposal` | Action Reviewer → `ActionPlan` |
| 激进 ↔ 保守 ↔ 中立（风险辩论） | FastMerge ↔ QualityFirst ↔ Balanced |
| Portfolio Manager → `PortfolioDecision` | Lead Reviewer → `FinalDecision` |
| `TradingMemoryLog`（延迟解析） | `ReviewMemory`（JSON 持久化） |
| `SqliteSaver` per ticker | `SqliteSaver` per thread_id |
| `ConditionalLogic` 类 | `conditional_logic.py` 模块函数 |
| `GraphSetup.setup_graph()` | `build_workflow()` |
| `Propagator.create_initial_state()` | `create_initial_state()` |
>>>>>>> 6a502ab (first commit)
