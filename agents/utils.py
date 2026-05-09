"""code_review/agents/utils.py —— 辅助函数

对照 TradingAgents: tradingagents/agents/utils/agent_utils.py
"""

from langchain_core.messages import HumanMessage, AIMessage


def create_msg_clear():
    """创建消息清除节点——保留初始 prompt 和最终报告，清除中间的工具调用消息。

    对照 TradingAgents: create_msg_delete()

    为什么需要？每个分析师会产生多条工具调用消息，
    不清除的话下一个分析师的上下文窗口会被大量无用消息占满。
    """

    def clear_messages(state):
        messages = state["messages"]
        if len(messages) <= 2:
            return {"messages": messages}

        # 策略：保留第一条（初始 prompt）+ 最新一条 AI 消息（报告）
        kept = [messages[0]]
        for msg in reversed(messages[1:]):
            if isinstance(msg, AIMessage) and not hasattr(msg, "tool_calls"):
                kept.append(msg)
                break
            elif isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and not msg.tool_calls:
                kept.append(msg)
                break

        if len(kept) == 1:
            kept.append(messages[-1])

        return {"messages": kept}

    return clear_messages


def extract_report_text(state, field_name: str) -> str:
    """从状态中提取最新报告文本。每个分析师节点使用此函数来读取前一个分析师的报告。"""
    content = state.get(field_name, "")
    if isinstance(content, str) and content:
        return content
    return "（暂无）"
