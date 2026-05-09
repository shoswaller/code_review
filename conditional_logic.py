"""code_review/conditional_logic.py —— 条件路由判定

对照 TradingAgents: tradingagents/graph/conditional_logic.py

每个判定函数根据当前 state 返回下一个节点的名字。
"""

from .state import AgentState


# ── 分析师工具循环的判定工厂 ──

def _make_analyst_router(tool_node: str, clear_node: str):
    """为每个分析师生成独立的工具循环判定函数。

    对照 TradingAgents: ConditionalLogic.should_continue_market / _social / _news / _fundamentals
    """
    def router(state: AgentState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return tool_node
        return clear_node
    return router


# 为四个分析师分别创建判定函数
should_continue_style = _make_analyst_router("tools_style", "Clear Style")
should_continue_security = _make_analyst_router("tools_security", "Clear Security")
should_continue_performance = _make_analyst_router("tools_performance", "Clear Performance")
should_continue_logic = _make_analyst_router("tools_logic", "Clear Logic")


# ── 辩论循环判定 ──

def should_continue_debate(state: AgentState, max_rounds: int = 2) -> str:
    """Approve/Revise 辩论路由。

    对照 TradingAgents: ConditionalLogic.should_continue_debate

    规则：
    - 当 count >= 2 * max_rounds 时，辩论终止 → Review Manager
    - 当前发言以 "Approve:" 开头 → 下一轮由 Revise 发言
    - 否则 → 下一轮由 Approve 发言
    """
    debate = state["debate_state"]
    if debate["count"] >= 2 * max_rounds:
        return "Review Manager"
    if debate["current_response"].startswith("Approve"):
        return "Revise Researcher"
    return "Approve Researcher"


# ── 风险辩论循环判定 ──

def should_continue_risk(state: AgentState, max_rounds: int = 2) -> str:
    """三方风险辩论路由。

    对照 TradingAgents: ConditionalLogic.should_continue_risk_analysis

    规则：
    - 当 count >= 3 * max_rounds 时 → Lead Reviewer
    - FastMerge → QualityFirst → Balanced → FastMerge → ...
    """
    risk = state.get("risk_debate_state", {})
    count = risk.get("count", 0)
    speaker = risk.get("latest_speaker", "")

    if count >= 3 * max_rounds:
        return "Lead Reviewer"

    if speaker.startswith("FastMerge"):
        return "Quality First Analyst"
    if speaker.startswith("QualityFirst"):
        return "Balanced Analyst"
    return "Fast Merge Analyst"
