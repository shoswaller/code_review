# 系统架构

本项目是一个多智能体代码审查工作流。核心思想是让不同角色分阶段处理同一份代码审查任务，最后由 Lead Reviewer 汇总裁定。

## 总体流程

```text
输入文件或项目目录
  -> 专项分析师流水线
  -> Approve / Revise 辩论
  -> Review Manager 生成审查计划
  -> Action Reviewer 生成修复方案
  -> Fast Merge / Quality First / Balanced 风险辩论
  -> Lead Reviewer 输出最终裁定
```

项目模式会在上述流程前增加项目扫描和架构分析，并在逐文件审查后生成项目级报告。

## 五层工作流

### 1. 专项分析师流水线

由 `style`、`security`、`performance`、`logic` 四类分析师组成。每个分析师都是一个 ReAct 风格节点，可以调用自己被授权的工具，直到生成对应领域的审查报告。

| 分析师 | 关注点 | 输出字段 |
| --- | --- | --- |
| Style Analyst | 命名、格式、组织、注释质量 | `style_report` |
| Security Analyst | SQL 注入、危险函数、硬编码密钥等 | `security_report` |
| Performance Analyst | 复杂度、循环 I/O、重复计算等 | `performance_report` |
| Logic Analyst | 边界条件、异常处理、死循环、类型问题 | `logic_report` |

每个分析师后都有 Clear 节点，用于清理工具调用消息，避免后续 Agent 被无关上下文污染。

### 2. 研究辩论

Approve Researcher 和 Revise Researcher 从相反立场讨论审查结果：

- Approve Researcher：寻找可合入理由，强调风险可控。
- Revise Researcher：寻找阻塞问题，强调先修复再合入。
- Review Manager：综合四份报告和辩论历史，生成结构化 `ReviewPlan`。

辩论轮数由 `--debate-rounds` 控制。

### 3. 行动方案

Action Reviewer 读取 `review_plan`，生成更可执行的 `ActionPlan`，包括建议动作、修复步骤和工作量估计。

### 4. 风险辩论

三种风险偏好进行多轮讨论：

- Fast Merge Analyst：偏向快速合入，只阻塞高风险问题。
- Quality First Analyst：偏向质量优先，强调长期维护成本。
- Balanced Analyst：在交付速度和质量风险之间折中。

风险辩论轮数由 `--risk-rounds` 控制。

### 5. 最终裁定

Lead Reviewer 汇总全部上游产物、历史审查上下文和风险讨论，输出最终结果：

- `Approve`
- `Request Changes`
- `Reject`

## 项目模式

项目模式由 `run_project_review()` 驱动，分三步：

1. `project_scanner.py` 发现源码文件并生成项目概览。
2. 对每个文件复用单文件五层审查流程。
3. `project_reporter.py` 汇总健康度、问题分布和修复建议，生成 `CODE_REVIEW_REPORT.md`。

文件扫描默认排除 `.git`、`node_modules`、`venv`、缓存目录、构建产物等常见无关目录。

## 核心模块

| 文件 | 职责 |
| --- | --- |
| `main.py` | CLI 入口，加载配置，区分单文件/项目模式，执行工作流 |
| `setup.py` | 构建 LangGraph `StateGraph`，定义节点和边 |
| `state.py` | 定义 `AgentState`、辩论状态和风险辩论状态 |
| `schemas.py` | 定义 Pydantic 输出模型和 Markdown 渲染函数 |
| `tools.py` | 定义代码读取、模式搜索、SQL 注入检测、项目分析等工具 |
| `conditional_logic.py` | 定义工具循环、研究辩论和风险辩论的路由逻辑 |
| `memory.py` | 保存和读取历史审查记录 |
| `checkpointer.py` | 封装 SQLite checkpoint |
| `project_scanner.py` | 项目文件发现和结构统计 |
| `project_reporter.py` | 项目级审查报告生成 |
| `agents/` | 各类 Agent 工厂函数 |

## 数据流

`AgentState` 是所有节点共享的状态对象。它继承自 LangGraph 的 `MessagesState`，并扩展出审查流程所需字段：

- `file_path` / `file_content`
- `style_report` / `security_report` / `performance_report` / `logic_report`
- `debate_state`
- `review_plan`
- `action_plan`
- `risk_debate_state`
- `final_decision`
- `past_context`

每层 Agent 读取上游字段，写入自己的结果字段，后续节点再继续消费这些结果。
