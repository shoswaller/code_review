"""code_review/agents/reviewer.py —— 第三层：行动方案审查员

对照 TradingAgents: tradingagents/agents/trader/trader.py

将 Review Manager 的审查计划转化为具体的代码修改步骤。
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from ..schemas import ActionPlan, render_action_plan


_ACTION_REVIEWER_PROMPT = """你是一位行动方案制定专家。基于审查经理的审查计划，制定具体的修改步骤。

## 你的任务
1. 审阅审查计划中的所有问题
2. 将问题转化为具体的代码修改步骤（可执行的修改指令）
3. 评估修改的预估工作量

## 输出格式
**操作**: [Fix / Approve / Reject]
**推演**: [决策理由，1-2 句]
**预估工作量**: [如 "30分钟" / "1小时" / "半天"]

### 修改步骤
1. [文件:行号] 具体修改内容
2. [文件:行号] 具体修改内容
...

## 审查计划
{review_plan}
"""


def create_action_reviewer(llm: Any):
    prompt = ChatPromptTemplate.from_messages([
        ("system", _ACTION_REVIEWER_PROMPT),
    ])

    try:
        llm_structured = llm.with_structured_output(ActionPlan)
        use_structured = True
    except (NotImplementedError, TypeError, ValueError):
        llm_structured = llm
        use_structured = False

    chain_structured = prompt | llm_structured
    chain_fallback = prompt | llm

    def node(state):
        review_plan = state.get("review_plan", state.get("debate_state", {}).get("judge_decision", "无审查计划"))

        if use_structured:
            try:
                plan: ActionPlan = chain_structured.invoke({"review_plan": review_plan})
                rendered = render_action_plan(plan)
                return {
                    "messages": [AIMessage(content=rendered)],
                    "action_plan": rendered,
                }
            except Exception as e:
                print(f"  [WARN] Structured output failed for ActionPlan ({e})")

        result = chain_fallback.invoke({"review_plan": review_plan})
        return {
            "messages": [result],
            "action_plan": result.content,
        }

    return node
