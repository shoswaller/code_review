"""code_review/agents/__init__.py —— 所有 Agent 工厂函数的统一导出

对照 TradingAgents: tradingagents/agents/__init__.py
"""

from .analysts import (
    create_style_analyst,
    create_security_analyst,
    create_performance_analyst,
    create_logic_analyst,
    create_project_architect,
)
from .researchers import (
    create_approve_researcher,
    create_revise_researcher,
    create_review_manager,
)
from .reviewer import create_action_reviewer
from .risk_mgmt import (
    create_fast_merge_analyst,
    create_quality_first_analyst,
    create_balanced_analyst,
)
from .lead_reviewer import create_lead_reviewer
from .utils import create_msg_clear
