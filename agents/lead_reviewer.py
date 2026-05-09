"""code_review/agents/lead_reviewer.py —— 第五层：最终裁定

对照 TradingAgents: tradingagents/agents/managers/portfolio_manager.py

综合所有前序分析、辩论和风险评估，输出最终的审查裁定。
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from ..schemas import FinalDecision, render_final_decision


_LEAD_REVIEWER_PROMPT = """你是一位首席代码审查官。你拥有以下全部信息来做出最终裁定:

## 你的决策输入
1. 四位分析师的专业报告（风格、安全、性能、逻辑）
2. Approve/Revise 研究员的辩论记录
3. 审查经理的审查计划（含所有发现和分类）
4. 行动方案审查员的具体修改步骤
5. 三方风险辩论（FastMerge / QualityFirst / Balanced）
6. 历史审查记录（past_context）

## 你的输出（严格遵守此格式）

**裁定**: [APPROVE / REQUEST_CHANGES / REJECT]
- APPROVE: 代码可以安全合入，无阻塞问题
- REQUEST_CHANGES: 存在必须修复的问题，修复后重新提交
- REJECT: 存在根本性问题，需要大幅重写

**摘要**: [2-3 句概括性总结]

**论据**: [详细说明裁定理由，引用具体发现]

**风险等级**: [High / Medium / Low]
- High: 合入会导致严重安全或可用性问题
- Medium: 有一定风险，需要关注
- Low: 风险可控，可正常合入

**预估修复时间**: [如 "30分钟" / "2小时" / "1天" / "不需要"]

## 历史上下文
{past_context}

## 分析师报告
{reports}

## 审查计划与行动方案
{review_plan}

## 风险辩论记录
{risk_discussion}
"""


def create_lead_reviewer(llm: Any):
    prompt = ChatPromptTemplate.from_messages([
        ("system", _LEAD_REVIEWER_PROMPT),
    ])

    try:
        llm_structured = llm.with_structured_output(FinalDecision)
        use_structured = True
    except (NotImplementedError, TypeError, ValueError):
        llm_structured = llm
        use_structured = False

    chain_structured = prompt | llm_structured
    chain_fallback = prompt | llm

    def node(state):
        reports = _format_reports(state)
        review_plan = state.get("review_plan", "") + "\n\n" + state.get("action_plan", "")
        risk_discussion = state.get("risk_debate_state", {}).get("history", "无风险讨论")
        past_context = state.get("past_context", "无历史记录。")

        invoke_args = {
            "reports": reports,
            "review_plan": review_plan,
            "risk_discussion": risk_discussion,
            "past_context": past_context,
        }

        if use_structured:
            try:
                decision: FinalDecision = chain_structured.invoke(invoke_args)
                rendered = render_final_decision(decision)
                return {
                    "messages": [AIMessage(content=rendered)],
                    "final_decision": rendered,
                }
            except Exception as e:
                print(f"  [WARN] Structured output failed for FinalDecision ({e})")

        result = chain_fallback.invoke(invoke_args)
        return {
            "messages": [result],
            "final_decision": result.content,
        }

    return node


def _format_reports(state) -> str:
    sections = []
    for field, label in [
        ("style_report", "风格审查"),
        ("security_report", "安全审查"),
        ("performance_report", "性能审查"),
        ("logic_report", "逻辑审查"),
    ]:
        content = state.get(field, "")
        sections.append(f"### {label}\n{content}" if content else f"### {label}\n（未生成）")
    return "\n\n".join(sections)
