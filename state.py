"""code_review/state.py —— AgentState 定义

对照 TradingAgents: tradingagents/agents/utils/agent_states.py
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class DebateState(TypedDict):
    """Approve/Revise 辩论的跟踪状态。"""
    approve_history: Annotated[str, "Approve 方所有发言"]
    revise_history: Annotated[str, "Revise 方所有发言"]
    history: Annotated[str, "完整辩论记录"]
    current_response: Annotated[str, "最新发言（以 Approve: 或 Revise: 开头）"]
    judge_decision: Annotated[str, "Review Manager 的裁定"]
    count: Annotated[int, "辩论消息计数"]


class RiskDebateState(TypedDict):
    """三方风险评估的跟踪状态。"""
    fast_merge_history: Annotated[str, "FastMerge 方所有发言"]
    quality_first_history: Annotated[str, "QualityFirst 方所有发言"]
    balanced_history: Annotated[str, "Balanced 方所有发言"]
    history: Annotated[str, "完整风险讨论记录"]
    latest_speaker: Annotated[str, "最后发言方: FastMerge/QualityFirst/Balanced"]
    current_fast_merge_response: Annotated[str, "FastMerge 最新发言"]
    current_quality_first_response: Annotated[str, "QualityFirst 最新发言"]
    current_balanced_response: Annotated[str, "Balanced 最新发言"]
    judge_decision: Annotated[str, "Lead Reviewer 的裁定"]
    count: Annotated[int, "风险讨论消息计数"]


class AgentState(MessagesState):
    """全局状态 —— 所有节点共享。"""
    # 输入
    file_path: Annotated[str, "待审查的源文件路径"]
    file_content: Annotated[str, "文件内容缓存"]

    # 第一层：分析师报告
    style_report: Annotated[str, "风格审查报告"]
    security_report: Annotated[str, "安全审查报告"]
    performance_report: Annotated[str, "性能审查报告"]
    logic_report: Annotated[str, "逻辑审查报告"]

    # 第二层：研究辩论
    debate_state: Annotated[DebateState, "通过/修改辩论状态"]
    review_plan: Annotated[str, "Review Manager 的审查计划"]

    # 第三层：行动方案
    action_plan: Annotated[str, "Action Reviewer 的具体修改方案"]

    # 第四层：风险评估
    risk_debate_state: Annotated[RiskDebateState, "三方风险评估状态"]

    # 第五层：最终裁定
    final_decision: Annotated[str, "Lead Reviewer 的最终裁定"]

    # 记忆
    past_context: Annotated[str, "历史审查记录上下文，注入到初始 state"]
