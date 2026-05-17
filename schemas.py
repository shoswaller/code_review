"""code_review/schemas.py —— Pydantic 结构化输出模型

对照 TradingAgents: tradingagents/agents/schemas.py
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ── 评级枚举 ──

class Verdict(str, Enum):
    APPROVE = "Approve"
    REQUEST_CHANGES = "Request Changes"
    REJECT = "Reject"


class Severity(str, Enum):
    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    NIT = "Nit"


class RiskTolerance(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# ── 第二层：Review Manager 结构化输出 ──

class ReviewFinding(BaseModel):
    file: str = Field(description="相关文件路径")
    line_range: str = Field(description="行号范围，如 'L15-L20'")
    severity: Severity = Field(description="严重级别")
    category: str = Field(description="问题类别: style/security/performance/logic")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="具体修改建议")


class ReviewPlan(BaseModel):
    """审查经理的结构化审查计划。

    对照 TradingAgents: ResearchPlan
    """
    recommendation: str = Field(description="初步建议: Approve/Request Changes/Reject")
    summary: str = Field(description="一句话总结")
    findings: List[ReviewFinding] = Field(description="所有审查发现")
    must_fix: List[str] = Field(description="必须修改否则阻塞合入的问题")
    nice_to_have: List[str] = Field(description="建议修改但不阻塞合入的问题")


# ── 第三层：Action Reviewer 结构化输出 ──

class ActionPlan(BaseModel):
    """具体修改行动方案。

    对照 TradingAgents: TraderProposal
    """
    action: str = Field(description="总体操作: Fix/Approve/Reject")
    reasoning: str = Field(description="决策推演")
    changes: List[str] = Field(description="具体修改步骤列表")
    estimated_effort: str = Field(description="预估修改工作量，如 '30分钟' / '2小时'")


# ── 第五层：Lead Reviewer 结构化输出 ──

class FinalDecision(BaseModel):
    """最终审查裁定。

    对照 TradingAgents: PortfolioDecision
    """
    verdict: Verdict = Field(description="最终裁定")
    executive_summary: str = Field(description="决策摘要")
    review_thesis: str = Field(description="审查论据")
    risk_assessment: RiskTolerance = Field(description="风险评估: High/Medium/Low")
    time_estimate: str = Field(description="预估修复时间")


# ── 渲染为 Markdown（供下游 LLM 消费） ──

def render_review_plan(plan: ReviewPlan) -> str:
    lines = [
        f"## 审查计划",
        f"**建议**: {plan.recommendation}",
        f"**摘要**: {plan.summary}",
        "",
        "### 审查发现",
    ]
    for f in plan.findings:
        lines.append(
            f"- [{f.severity.value}] `{f.file}:{f.line_range}` "
            f"({f.category}): {f.description} → *{f.suggestion}*"
        )
    lines.append("\n### 必须修改")
    for item in plan.must_fix:
        lines.append(f"- {item}")
    lines.append("\n### 建议修改")
    for item in plan.nice_to_have:
        lines.append(f"- {item}")
    return "\n".join(lines)


def render_action_plan(plan: ActionPlan) -> str:
    lines = [
        f"## 行动方案",
        f"**操作**: {plan.action}",
        f"**推演**: {plan.reasoning}",
        f"**预估工作量**: {plan.estimated_effort}",
        "",
        "### 修改步骤",
    ]
    for i, step in enumerate(plan.changes, 1):
        lines.append(f"{i}. {step}")
    return "\n".join(lines)


# ── 项目级数据结构 ──

class FileReviewSummary(BaseModel):
    """单文件审查摘要，用于项目级汇总。"""
    file_path: str = Field(description="文件路径")
    verdict: str = Field(description="该文件的审查裁定")
    lines: int = Field(description="文件行数")
    critical_count: int = Field(default=0, description="Critical 问题数")
    major_count: int = Field(default=0, description="Major 问题数")
    minor_count: int = Field(default=0, description="Minor 问题数")
    nit_count: int = Field(default=0, description="Nit 问题数")
    style_issues: int = Field(default=0)
    security_issues: int = Field(default=0)
    performance_issues: int = Field(default=0)
    logic_issues: int = Field(default=0)


class ProjectOverview(BaseModel):
    """项目概览。"""
    project_root: str = Field(description="项目根目录")
    total_files: int = Field(description="代码文件总数")
    total_lines: int = Field(description="总代码行数")
    total_functions: int = Field(description="总函数/方法数")
    total_classes: int = Field(description="总类数")
    language_distribution: dict = Field(default_factory=dict, description="语言分布")
    directory_tree: str = Field(description="目录树结构")


class ProjectReviewReport(BaseModel):
    """项目级审查汇总报告。"""
    overview: ProjectOverview = Field(description="项目概览")
    file_summaries: List[FileReviewSummary] = Field(description="各文件审查摘要")
    health_score: int = Field(description="项目健康度评分 0-100")
    total_findings: int = Field(description="发现的问题总数")
    critical_findings: List[str] = Field(description="Critical 级别问题列表")
    major_findings: List[str] = Field(description="Major 级别问题列表")
    top_issues: List[str] = Field(description="TOP 10 最需关注的问题")
    recommendation: str = Field(description="项目级总体建议")


def render_final_decision(decision: FinalDecision) -> str:
    lines = [
        f"## 最终审查裁定",
        f"",
        f"**裁定**: {decision.verdict.value}",
        f"**摘要**: {decision.executive_summary}",
        f"**论据**: {decision.review_thesis}",
        f"**风险等级**: {decision.risk_assessment.value}",
        f"**预估修复时间**: {decision.time_estimate}",
    ]
    return "\n".join(lines)
