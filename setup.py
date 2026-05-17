"""code_review/setup.py —— 构建完整的五层审查图

对照 TradingAgents: tradingagents/graph/setup.py

图结构:
START → [Style Analyst ↔ tools_style → Clear Style]
     → [Security Analyst ↔ tools_security → Clear Security]
     → [Performance Analyst ↔ tools_performance → Clear Performance]
     → [Logic Analyst ↔ tools_logic → Clear Logic]
     → [Approve Researcher ↔ Revise Researcher] → Review Manager
     → Action Reviewer
     → [Fast Merge ↔ Quality First ↔ Balanced] → Lead Reviewer
     → END
"""

from typing import Any, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import AgentState, DebateState, RiskDebateState
from .tools import ANALYST_TOOLS
from .agents import (
    create_style_analyst,
    create_security_analyst,
    create_performance_analyst,
    create_logic_analyst,
    create_approve_researcher,
    create_revise_researcher,
    create_review_manager,
    create_action_reviewer,
    create_fast_merge_analyst,
    create_quality_first_analyst,
    create_balanced_analyst,
    create_lead_reviewer,
    create_msg_clear,
)
from .conditional_logic import (
    should_continue_style,
    should_continue_security,
    should_continue_performance,
    should_continue_logic,
    should_continue_debate,
    should_continue_risk,
)


def build_workflow(
    llm: Any,
    selected_analysts: Optional[List[str]] = None,
    max_debate_rounds: int = 2,
    max_risk_rounds: int = 2,
) -> StateGraph:
    """构建 StateGraph（未编译）。

    Args:
        llm: LangChain LLM 实例
        selected_analysts: 选择的分析师列表，默认全部。可选: style/security/performance/logic
        max_debate_rounds: Approve/Revise 最大辩论轮数
        max_risk_rounds: 风险辩论最大轮数
    """
    if selected_analysts is None:
        selected_analysts = ["style", "security", "performance", "logic"]

    # ── 分析师配置 ──
    analyst_config = {
        "style": {
            "create_fn": create_style_analyst,
            "tools": ANALYST_TOOLS["style"],
            "router": should_continue_style,
            "label": "Style",
        },
        "security": {
            "create_fn": create_security_analyst,
            "tools": ANALYST_TOOLS["security"],
            "router": should_continue_security,
            "label": "Security",
        },
        "performance": {
            "create_fn": create_performance_analyst,
            "tools": ANALYST_TOOLS["performance"],
            "router": should_continue_performance,
            "label": "Performance",
        },
        "logic": {
            "create_fn": create_logic_analyst,
            "tools": ANALYST_TOOLS["logic"],
            "router": should_continue_logic,
            "label": "Logic",
        },
    }

    # ── 创建图 ──
    workflow = StateGraph(AgentState)

    # ==================================================================
    # 第一层: 分析师管道
    # ==================================================================
    for name in selected_analysts:
        cfg = analyst_config[name]
        label = cfg["label"]

        # 添加分析师节点
        workflow.add_node(f"{label} Analyst", cfg["create_fn"](llm))
        # 添加消息清除节点
        workflow.add_node(f"Clear {label}", create_msg_clear())
        # 添加工具节点（按分析师职责隔离）
        workflow.add_node(f"tools_{name}", ToolNode(cfg["tools"]))

    # 入口 → 第一个分析师
    first_label = analyst_config[selected_analysts[0]]["label"]
    workflow.add_edge(START, f"{first_label} Analyst")

    # 串联分析师
    for i, name in enumerate(selected_analysts):
        cfg = analyst_config[name]
        label = cfg["label"]

        # 分析师 ↔ 工具循环（对照 TradingAgents: setup.py L122-L127）
        router = cfg["router"]
        tool_node = f"tools_{name}"
        clear_node = f"Clear {label}"

        workflow.add_conditional_edges(
            f"{label} Analyst",
            router,
            {tool_node: tool_node, clear_node: clear_node},
        )
        workflow.add_edge(tool_node, f"{label} Analyst")

        # 串联: 当前清除节点 → 下一个分析师 或 进入辩论
        if i < len(selected_analysts) - 1:
            next_label = analyst_config[selected_analysts[i + 1]]["label"]
            workflow.add_edge(clear_node, f"{next_label} Analyst")
        else:
            workflow.add_edge(clear_node, "Approve Researcher")

    # ==================================================================
    # 第二层: 研究辩论（对照 TradingAgents: setup.py L137-L153）
    # ==================================================================
    workflow.add_node("Approve Researcher", create_approve_researcher(llm))
    workflow.add_node("Revise Researcher", create_revise_researcher(llm))
    workflow.add_node("Review Manager", create_review_manager(llm))

    # 使用 lambda 注入 max_rounds 参数
    def _debate_router(state):
        return should_continue_debate(state, max_rounds=max_debate_rounds)

    workflow.add_conditional_edges(
        "Approve Researcher",
        _debate_router,
        {
            "Revise Researcher": "Revise Researcher",
            "Review Manager": "Review Manager",
        },
    )
    workflow.add_conditional_edges(
        "Revise Researcher",
        _debate_router,
        {
            "Approve Researcher": "Approve Researcher",
            "Review Manager": "Review Manager",
        },
    )

    # ==================================================================
    # 第三层: 行动方案
    # ==================================================================
    workflow.add_node("Action Reviewer", create_action_reviewer(llm))
    workflow.add_edge("Review Manager", "Action Reviewer")

    # ==================================================================
    # 第四层: 风险三方辩论（对照 TradingAgents: setup.py L154-L178）
    # ==================================================================
    workflow.add_node("Fast Merge Analyst", create_fast_merge_analyst(llm))
    workflow.add_node("Quality First Analyst", create_quality_first_analyst(llm))
    workflow.add_node("Balanced Analyst", create_balanced_analyst(llm))
    workflow.add_node("Lead Reviewer", create_lead_reviewer(llm))

    workflow.add_edge("Action Reviewer", "Fast Merge Analyst")

    def _risk_router(state):
        return should_continue_risk(state, max_rounds=max_risk_rounds)

    workflow.add_conditional_edges(
        "Fast Merge Analyst",
        _risk_router,
        {
            "Quality First Analyst": "Quality First Analyst",
            "Lead Reviewer": "Lead Reviewer",
        },
    )
    workflow.add_conditional_edges(
        "Quality First Analyst",
        _risk_router,
        {
            "Balanced Analyst": "Balanced Analyst",
            "Lead Reviewer": "Lead Reviewer",
        },
    )
    workflow.add_conditional_edges(
        "Balanced Analyst",
        _risk_router,
        {
            "Fast Merge Analyst": "Fast Merge Analyst",
            "Lead Reviewer": "Lead Reviewer",
        },
    )

    workflow.add_edge("Lead Reviewer", END)

    return workflow


def build_project_workflow(
    llm: Any,
    selected_analysts: list | None = None,
    max_debate_rounds: int = 2,
    max_risk_rounds: int = 2,
) -> StateGraph:
    """构建项目审查图 —— 先进行项目级架构分析，再转入逐文件审查。

    项目审查图结构:
    START → [Project Architect ↔ tools_project] → END
    （逐文件审查由 main.py 中的 run_project_review 使用 build_workflow 逐个执行）
    """
    if selected_analysts is None:
        selected_analysts = ["style", "security", "performance", "logic"]

    from .agents import create_project_architect, create_msg_clear
    from .tools import ANALYST_TOOLS
    from .conditional_logic import _make_analyst_router

    workflow = StateGraph(AgentState)

    # 项目架构分析节点
    workflow.add_node("Project Architect", create_project_architect(llm))
    workflow.add_node("Clear Project", create_msg_clear())
    workflow.add_node("tools_project", ToolNode(ANALYST_TOOLS["project"]))

    workflow.add_edge(START, "Project Architect")

    project_router = _make_analyst_router("tools_project", "Clear Project")
    workflow.add_conditional_edges(
        "Project Architect",
        project_router,
        {"tools_project": "tools_project", "Clear Project": "Clear Project"},
    )
    workflow.add_edge("tools_project", "Project Architect")
    workflow.add_edge("Clear Project", END)

    return workflow


def create_initial_state(
    file_path: str,
    past_context: str = "",
) -> dict:
    """创建图的初始状态（对照 TradingAgents: Propagator.create_initial_state）。"""
    return {
        "messages": [("human", f"请审查文件: {file_path}")],
        "file_path": file_path,
        "file_content": "",
        "style_report": "",
        "security_report": "",
        "performance_report": "",
        "logic_report": "",
        "debate_state": DebateState(
            approve_history="",
            revise_history="",
            history="",
            current_response="",
            judge_decision="",
            count=0,
        ),
        "review_plan": "",
        "action_plan": "",
        "risk_debate_state": RiskDebateState(
            fast_merge_history="",
            quality_first_history="",
            balanced_history="",
            history="",
            latest_speaker="",
            current_fast_merge_response="",
            current_quality_first_response="",
            current_balanced_response="",
            judge_decision="",
            count=0,
        ),
        "final_decision": "",
        "past_context": past_context,
    }
