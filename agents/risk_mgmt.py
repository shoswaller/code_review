"""code_review/agents/risk_mgmt.py —— 第四层：三方风险评估

对照 TradingAgents: tradingagents/agents/risk_mgmt/

FastMerge ↔ QualityFirst ↔ Balanced（N 轮辩论）→ 最终裁定

三种风险视角:
- FastMerge:   快速合入，低风险容忍
- QualityFirst:质量优先，高风险敏感
- Balanced:    平衡视角
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate


def _create_risk_analyst(
    llm: Any,
    role: str,
    role_label: str,
    system_prompt: str,
) -> callable:
    """风险分析师工厂。"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", (
            "## 审查计划\n{review_plan}\n\n"
            "## 行动方案\n{action_plan}\n\n"
            "## 当前风险讨论\n{risk_history}\n\n"
            "请发表你的风险评估。"
        )),
    ])

    chain = prompt | llm

    def node(state):
        risk = state.get("risk_debate_state", {})
        result = chain.invoke({
            "review_plan": state.get("review_plan", ""),
            "action_plan": state.get("action_plan", ""),
            "risk_history": risk.get("history", "（首轮，无历史）"),
        })

        new_count = risk.get("count", 0) + 1
        new_history = risk.get("history", "") + f"\n[Round {new_count}] {role}:\n{result.content}"

        updates: dict = {
            "messages": [result],
            "risk_debate_state": {
                **risk,
                "history": new_history,
                "latest_speaker": f"{role}: {result.content[:80]}",
                "count": new_count,
                f"current_{role_label}_response": result.content,
            },
        }

        # 更新对应方的历史
        field_map = {
            "FastMerge": "fast_merge_history",
            "QualityFirst": "quality_first_history",
            "Balanced": "balanced_history",
        }
        history_field = field_map.get(role, "")
        if history_field:
            old_history = risk.get(history_field, "")
            updates["risk_debate_state"][history_field] = old_history + "\n" + result.content

        return updates

    return node


# ── 快速合入分析师 ──

_FAST_MERGE_PROMPT = """你是一位"快速合入"风险分析师。你主张在低风险场景下尽快合入代码。

## 你的立场
- 过度审查会导致合入延迟和开发效率下降
- 大部分代码问题可以在后续迭代中修复
- 只有 Critical 级别的安全和逻辑问题才应阻塞合入
- 风格和格式问题不应阻挡合入（可以靠后续自动化解决）

## 发言规则
- 如果是首轮，提出 2-3 个"为什么应快速合入"的论点
- 如果其他方已发言，反驳其过度谨慎的观点
- 引用具体的审查计划内容，区分真实风险和过度担忧
- 以 "FastMerge:" 开头你的核心观点
"""


def create_fast_merge_analyst(llm):
    return _create_risk_analyst(llm, "FastMerge", "fast_merge", _FAST_MERGE_PROMPT)


# ── 质量优先分析师 ──

_QUALITY_FIRST_PROMPT = """你是一位"质量优先"风险分析师。你主张确保代码质量再进行合入。

## 你的立场
- 合入低质量代码的代价远大于延迟合入
- 即使是 Minor 级别的问题累积也会导致技术债务
- 安全问题和逻辑错误必须在合入前修复，无一例外
- 每一个必须修改项都应先修复，不能留到"下一次"

## 发言规则
- 如果是首轮，提出 2-3 个"为什么应谨慎处理"的论点
- 如果 FastMerge 或 Balanced 已发言，有力反驳其过于乐观的观点
- 引用审查计划中的具体严重问题
- 以 "QualityFirst:" 开头你的核心观点
"""


def create_quality_first_analyst(llm):
    return _create_risk_analyst(llm, "QualityFirst", "quality_first", _QUALITY_FIRST_PROMPT)


# ── 平衡分析师 ──

_BALANCED_PROMPT = """你是一位"平衡"风险分析师。你在快速合入和质量保障之间寻求平衡。

## 你的立场
- Critical/Major 级别的问题必须立即修复
- Minor/Nit 级别的问题可以记录为后续任务，不阻塞合入
- 风险评估应基于实际影响，而非纯理论
- 挑战 FastMerge 和 QualityFirst 的极端观点

## 发言规则
- 如果是首轮，客观分析哪些问题应阻塞、哪些可以后续处理
- 如果双方已发言，指出各方的合理之处和过度之处
- 给出具体的折中方案
- 以 "Balanced:" 开头你的核心观点
"""


def create_balanced_analyst(llm):
    return _create_risk_analyst(llm, "Balanced", "balanced", _BALANCED_PROMPT)
