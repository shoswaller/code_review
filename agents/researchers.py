"""code_review/agents/researchers.py —— 第二层：研究辩论

对照 TradingAgents: tradingagents/agents/researchers/ + managers/research_manager.py

Approve 研究员 ↔ Revise 研究员（N 轮辩论）→ Review Manager（裁定）
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from ..schemas import ReviewPlan, render_review_plan


# ── Approve 研究员（Bull 方） ──

_APPROVE_PROMPT = """你是一位"同意合入"研究员。你的任务是基于四条分析报告，论证代码应该被批准合入。

## 规则
- 如果是第一轮辩论（辩论历史为空），提出 2-3 个核心支持论点
- 如果 Revise 研究员已提出反对意见，逐一进行有理据的反驳
- 引用具体的分析报告内容作为证据
- 不虚构不存在的事实

## 输出格式
在辩论回复末尾，用以下 JSON 更新辩论状态:
```json
{{"count": <当前轮次>, "current_response": "Approve: <你的核心论据摘要>"}}
```

## 分析师报告
{reports}

## 辩论历史
{debate_history}
"""


def create_approve_researcher(llm: Any):
    prompt = ChatPromptTemplate.from_messages([
        ("system", _APPROVE_PROMPT),
    ])

    chain = prompt | llm

    def node(state):
        reports = _format_reports(state)
        debate = state["debate_state"]

        result = chain.invoke({
            "reports": reports,
            "debate_history": debate.get("history", "（首轮，无历史）"),
        })

        new_count = debate["count"] + 1
        new_response = f"Approve: {_extract_summary(result.content)}"
        new_history = debate.get("history", "") + f"\n[Round {new_count}] Approve Researcher:\n{result.content}"

        return {
            "messages": [result],
            "debate_state": {
                "approve_history": debate.get("approve_history", "") + "\n" + result.content,
                "revise_history": debate.get("revise_history", ""),
                "history": new_history,
                "current_response": new_response,
                "judge_decision": "",
                "count": new_count,
            },
        }

    return node


# ── Revise 研究员（Bear 方） ──

_REVISE_PROMPT = """你是一位"需要修改"研究员。你的任务是基于四条分析报告，论证代码需要修改后才能合入。

## 规则
- 如果是第一轮辩论，提出 2-3 个必须修改的关键问题
- 如果 Approve 研究员已提出支持意见，逐一反驳
- 引用具体的分析报告行号作为证据
- 区分"阻塞性问题"和"建议性问题"

## 输出格式
在辩论回复末尾，用以下 JSON 更新辩论状态:
```json
{{"count": <当前轮次>, "current_response": "Revise: <你的核心论据摘要>"}}
```

## 分析师报告
{reports}

## 辩论历史
{debate_history}
"""


def create_revise_researcher(llm: Any):
    prompt = ChatPromptTemplate.from_messages([
        ("system", _REVISE_PROMPT),
    ])

    chain = prompt | llm

    def node(state):
        reports = _format_reports(state)
        debate = state["debate_state"]

        result = chain.invoke({
            "reports": reports,
            "debate_history": debate.get("history", "（首轮，无历史）"),
        })

        new_count = debate["count"] + 1
        new_response = f"Revise: {_extract_summary(result.content)}"
        new_history = debate.get("history", "") + f"\n[Round {new_count}] Revise Researcher:\n{result.content}"

        return {
            "messages": [result],
            "debate_state": {
                "approve_history": debate.get("approve_history", ""),
                "revise_history": debate.get("revise_history", "") + "\n" + result.content,
                "history": new_history,
                "current_response": new_response,
                "judge_decision": "",
                "count": new_count,
            },
        }

    return node


# ── Review Manager（裁判） ──

_REVIEW_MANAGER_PROMPT = """你是一位经验丰富的审查经理。Approver 和 Revise 研究员已完成辩论，请你做出裁定。

## 你的任务
1. 审阅四份分析师报告和完整的辩论记录
2. 裁定代码应: Approve（批准）/ Request Changes（需要修改）/ Reject（拒绝）
3. 列出所有发现的问题，标注严重度和所属类别
4. 区分"必须修改"和"建议修改"

## 输出格式（严格遵守）
**建议**: [Approve / Request Changes / Reject]
**摘要**: [一句话总结]

### 审查发现
- [严重度] `文件:行号` (类别): 问题描述 → 修改建议

### 必须修改
- [问题描述]

### 建议修改
- [问题描述]

**前提**: 在辩论中分析的所有证据基础上做出判断。

## 分析师报告
{reports}

## 辩论记录
{debate_history}
"""


def create_review_manager(llm: Any):
    prompt = ChatPromptTemplate.from_messages([
        ("system", _REVIEW_MANAGER_PROMPT),
    ])

    # 尝试结构化输出，否则用自由文本
    try:
        llm_structured = llm.with_structured_output(ReviewPlan)
        use_structured = True
    except (NotImplementedError, TypeError, ValueError):
        llm_structured = llm
        use_structured = False

    chain_structured = prompt | llm_structured
    chain_fallback = prompt | llm

    def node(state):
        reports = _format_reports(state)
        debate = state["debate_state"]

        if use_structured:
            try:
                plan: ReviewPlan = chain_structured.invoke({
                    "reports": reports,
                    "debate_history": debate.get("history", ""),
                })
                rendered = render_review_plan(plan)
                return {
                    "messages": [AIMessage(content=rendered)],
                    "review_plan": rendered,
                    "debate_state": {
                        **state["debate_state"],
                        "judge_decision": plan.recommendation,
                    },
                }
            except Exception as e:
                # 结构化输出失败 → 降级为自由文本
                print(f"  [WARN] Structured output failed ({e}), using free text")

        result = chain_fallback.invoke({
            "reports": reports,
            "debate_history": debate.get("history", ""),
        })
        return {
            "messages": [result],
            "review_plan": result.content,
            "debate_state": {
                **state["debate_state"],
                "judge_decision": result.content[:100],
            },
        }

    return node


# ── 辅助函数 ──

def _format_reports(state) -> str:
    """将四个分析师的报告拼接为统一格式。"""
    sections = []
    for field, label in [
        ("style_report", "风格审查"),
        ("security_report", "安全审查"),
        ("performance_report", "性能审查"),
        ("logic_report", "逻辑审查"),
    ]:
        content = state.get(field, "")
        if content:
            sections.append(f"### {label}\n{content}")
        else:
            sections.append(f"### {label}\n（未生成）")
    return "\n\n".join(sections)


def _extract_summary(text: str, max_len: int = 100) -> str:
    """从文本中提取简短摘要。"""
    clean = text.strip().replace("\n", " ")
    return clean[:max_len] + ("..." if len(clean) > max_len else "")
