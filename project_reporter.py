"""code_review/project_reporter.py —— 项目级汇总报告生成

汇总所有文件的审查结果，生成项目级审查报告。
"""

import re
from pathlib import Path
from typing import List

from .schemas import (
    FileReviewSummary,
    ProjectOverview,
    ProjectReviewReport,
)
from .project_scanner import discover_files, analyze_project_structure, count_stats


def parse_findings_from_report(report_text: str) -> dict:
    """从单文件审查报告的文本中提取问题统计。

    解析报告中的 [Critical], [Major], [Minor], [Nit] 标记。
    """
    result = {
        "critical_count": 0,
        "major_count": 0,
        "minor_count": 0,
        "nit_count": 0,
        "style_issues": 0,
        "security_issues": 0,
        "performance_issues": 0,
        "logic_issues": 0,
    }

    if not report_text:
        return result

    # 统计严重度
    for match in re.finditer(
        r"\[(Critical|Major|Minor|Nit)\]",
        report_text,
        re.IGNORECASE,
    ):
        sev = match.group(1).capitalize()
        key = {"Critical": "critical_count", "Major": "major_count",
               "Minor": "minor_count", "Nit": "nit_count"}.get(sev, "")
        if key:
            result[key] += 1

    # 按类别统计
    for match in re.finditer(
        r"\((style|security|performance|logic)\)",
        report_text,
        re.IGNORECASE,
    ):
        cat = match.group(1).lower()
        key = f"{cat}_issues"
        if key in result:
            result[key] += 1

    return result


def create_file_summary(
    file_path: str,
    verdict: str,
    file_review_report: str = "",
) -> FileReviewSummary:
    """为单个文件创建审查摘要。"""
    stats = count_stats(file_path)
    findings = parse_findings_from_report(file_review_report)

    return FileReviewSummary(
        file_path=file_path,
        verdict=verdict,
        lines=stats["lines"],
        **findings,
    )


def _calculate_health_score(
    file_summaries: List[FileReviewSummary],
    total_files: int,
) -> int:
    """根据问题密度计算项目健康度评分 0-100。

    每个 Critical 扣 15 分，Major 扣 5 分，Minor 扣 2 分，Nit 扣 0.5 分。
    按文件数归一化，最低 0 分。
    """
    if total_files == 0:
        return 100

    penalty = 0
    for s in file_summaries:
        penalty += s.critical_count * 15
        penalty += s.major_count * 5
        penalty += s.minor_count * 2
        penalty += s.nit_count * 0.5

    # 归一化：基准为每文件扣 3 分
    normalized = penalty / max(total_files, 1) * 3
    score = max(0, min(100, 100 - int(normalized)))
    return score


def _extract_top_issues(file_summaries: List[FileReviewSummary]) -> List[str]:
    """提取 TOP 问题列表（按严重度优先排序）。"""
    critical_files = sorted(
        [s for s in file_summaries if s.critical_count > 0],
        key=lambda s: (-s.critical_count, -s.major_count),
    )
    issues: List[str] = []
    for s in critical_files[:5]:
        fname = Path(s.file_path).name
        issues.append(
            f"[{fname}] Critical={s.critical_count} Major={s.major_count} "
            f"Minor={s.minor_count} — 裁定: {s.verdict}"
        )

    major_files = sorted(
        [s for s in file_summaries if s.critical_count == 0 and s.major_count > 0],
        key=lambda s: (-s.major_count, -s.minor_count),
    )
    for s in major_files[:5]:
        if len(issues) >= 10:
            break
        fname = Path(s.file_path).name
        issues.append(
            f"[{fname}] Major={s.major_count} Minor={s.minor_count} "
            f"— 裁定: {s.verdict}"
        )

    return issues


def compose_project_report(
    project_root: str,
    file_summaries: List[FileReviewSummary],
    file_reports: dict,
    include_exts: List[str] | None = None,
    exclude_dirs: List[str] | None = None,
) -> ProjectReviewReport:
    """汇总所有文件的审查结果，生成项目级审查报告。

    Args:
        project_root: 项目根目录
        file_summaries: 各文件审查摘要列表
        file_reports: {file_path: report_text} 单文件报告原文
        include_exts: 扫描时所用的扩展名
        exclude_dirs: 扫描时排除的目录
    """
    files = list(file_reports.keys()) if file_reports else [s.file_path for s in file_summaries]
    overview = analyze_project_structure(project_root, files)

    total_findings = sum(
        s.critical_count + s.major_count + s.minor_count + s.nit_count
        for s in file_summaries
    )
    health_score = _calculate_health_score(file_summaries, overview.total_files)
    top_issues = _extract_top_issues(file_summaries)

    # 汇总所有 Critical / Major 发现
    critical_findings = []
    major_findings = []
    for s in file_summaries:
        short_name = Path(s.file_path).name
        if s.critical_count > 0:
            critical_findings.append(
                f"{short_name} — {s.critical_count} Critical, "
                f"{s.major_count} Major 问题"
            )
        elif s.major_count > 0:
            major_findings.append(
                f"{short_name} — {s.major_count} Major, "
                f"{s.minor_count} Minor 问题"
            )

    # 生成总体建议
    if health_score >= 80:
        recommendation = "项目整体质量良好，建议修复 Critical/Major 问题后合入。"
    elif health_score >= 60:
        recommendation = "项目存在一定技术债务，建议优先修复 Critical 问题，制定技术债务清理计划。"
    elif health_score >= 40:
        recommendation = "项目质量问题较多，建议进行全面重构，优先解决安全和逻辑问题。"
    else:
        recommendation = "项目质量严重不达标，建议暂缓合入，进行全面代码整改。"

    return ProjectReviewReport(
        overview=overview,
        file_summaries=file_summaries,
        health_score=health_score,
        total_findings=total_findings,
        critical_findings=critical_findings,
        major_findings=major_findings,
        top_issues=top_issues,
        recommendation=recommendation,
    )


def render_project_report(report: ProjectReviewReport) -> str:
    """将项目审查报告渲染为 Markdown 文本。"""
    ov = report.overview
    lines = [
        "# 项目代码审查报告",
        "",
        "## 项目概览",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 项目路径 | {ov.project_root} |",
        f"| 代码文件数 | {ov.total_files} |",
        f"| 总代码行数 | {ov.total_lines} |",
        f"| 函数/方法数 | {ov.total_functions} |",
        f"| 类/接口数 | {ov.total_classes} |",
        f"| 健康度评分 | **{report.health_score}/100** |",
        f"| 发现问题总数 | {report.total_findings} |",
        "",
        "### 语言分布",
    ]

    for lang, count in sorted(ov.language_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"- {lang}: {count} 文件")

    lines.extend([
        "",
        "### 目录结构",
        "```",
        ov.directory_tree,
        "```",
        "",
        "---",
        "",
        "## 健康度评分: {}/100".format(report.health_score),
        "",
        _health_bar(report.health_score),
        "",
    ])

    # 各文件摘要
    lines.extend([
        "",
        "## 各文件审查摘要",
        "",
        "| 文件 | 行数 | 裁定 | Critical | Major | Minor | Nit |",
        "|------|------|------|----------|-------|-------|-----|",
    ])
    for s in report.file_summaries:
        fname = Path(s.file_path).name
        lines.append(
            f"| {fname} | {s.lines} | {s.verdict} | "
            f"{s.critical_count} | {s.major_count} | {s.minor_count} | {s.nit_count} |"
        )

    # TOP 问题
    if report.top_issues:
        lines.extend([
            "",
            "## TOP 10 最需关注的问题",
            "",
        ])
        for i, issue in enumerate(report.top_issues, 1):
            lines.append(f"{i}. {issue}")

    # Critical / Major 汇总
    if report.critical_findings:
        lines.extend([
            "",
            "## Critical 级别问题",
            "",
        ])
        for f in report.critical_findings:
            lines.append(f"- {f}")

    if report.major_findings:
        lines.extend([
            "",
            "## Major 级别问题",
            "",
        ])
        for f in report.major_findings:
            lines.append(f"- {f}")

    # 总体建议
    lines.extend([
        "",
        "---",
        "",
        "## 总体建议",
        "",
        report.recommendation,
    ])

    return "\n".join(lines)


def _health_bar(score: int) -> str:
    """生成健康度评分可视化条。"""
    filled = int(score / 5)
    empty = 20 - filled
    if score >= 80:
        color_block = "█"
    elif score >= 60:
        color_block = "▓"
    elif score >= 40:
        color_block = "▒"
    else:
        color_block = "░"
    bar = color_block * filled + "·" * empty
    return f"`[{bar}]`"
