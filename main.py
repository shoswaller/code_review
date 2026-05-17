"""code_review/main.py —— Code Review 多智能体系统入口

用法（单文件）:
    python -m code_review.main path/to/file.py
    python -m code_review.main path/to/file.py --config my-config.json
    python -m code_review.main path/to/file.py --analysts style security logic
    python -m code_review.main path/to/file.py --debate-rounds 3 --stream
    python -m code_review.main path/to/file.py --checkpoint --thread-id my-review

用法（项目模式）:
    python -m code_review.main ./my-project --project
    python -m code_review.main ./my-project --project --ext .py,.js
    python -m code_review.main ./my-project --project --exclude node_modules,venv

对照 TradingAgents: cli/main.py
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from .setup import build_workflow, build_project_workflow, create_initial_state
from .memory import ReviewMemory
from .checkpointer import get_checkpointer
from .project_scanner import discover_files, analyze_project_structure
from .project_reporter import (
    create_file_summary,
    compose_project_report,
    render_project_report,
)

# ==================================================================
# 配置加载（JSON 配置文件，零额外依赖）
# ==================================================================

def load_config(config_path: str | None = None) -> dict:
    """读取本地 JSON 配置文件，返回配置字典。

    配置优先级（高 → 低）:
        CLI 参数 > 已存在的环境变量 > 配置文件 > 硬编码默认值
    """
    if config_path is None:
        config_path = str(Path(__file__).parent / "config.json")

    path = Path(config_path)
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        print(f"[配置] 已加载配置文件: {path}")
        return cfg
    except (json.JSONDecodeError, OSError) as e:
        print(f"[配置] 警告: 读取配置文件失败 ({e})，忽略。")
        return {}


def _apply_config(cfg: dict):
    """将配置值填入环境变量（仅在对应环境变量未设置时）。"""
    mappings = [
        ("base_url", "OPENAI_BASE_URL"),
        ("api_key", "OPENAI_API_KEY"),
        ("model",   "REVIEW_MODEL"),
    ]
    for cfg_key, env_key in mappings:
        if cfg_key in cfg and env_key not in os.environ:
            os.environ[env_key] = str(cfg[cfg_key])


def _resolve_llm_kwargs(args, cfg: dict) -> dict:
    """按优先级组装 LLM 参数: CLI > 环境变量 > 配置文件 > 默认值。

    args 的 default 已经由 argparse 从环境变量填充，
    所以只需在 args 值为空时回退到配置文件即可。
    """
    kwargs = {"model": args.model or cfg.get("model", "gpt-4o")}

    base_url = args.base_url or cfg.get("base_url") or os.getenv("OPENAI_BASE_URL")
    api_key = args.api_key or cfg.get("api_key") or os.getenv("OPENAI_API_KEY")

    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    # 从配置文件透传 ChatOpenAI 的额外参数（如 temperature, model_kwargs 等）
    for key in ("temperature", "top_p", "max_tokens", "model_kwargs"):
        if key in cfg:
            kwargs[key] = cfg[key]

    return kwargs


def parse_args():
    parser = argparse.ArgumentParser(
        description="Code Review 多智能体系统 —— 基于 LangGraph 的五层代码审查",
    )
    parser.add_argument("file", nargs="?", help="待审查的文件路径")
    parser.add_argument(
        "--model", default=os.getenv("REVIEW_MODEL", "gpt-4o"),
        help="LLM 模型名称 (默认: gpt-4o)"
    )
    parser.add_argument(
        "--analysts", nargs="+",
        choices=["style", "security", "performance", "logic"],
        default=["style", "security", "performance", "logic"],
        help="选择启用的分析师 (默认: 全部)"
    )
    parser.add_argument(
        "--debate-rounds", type=int, default=2,
        help="Approve/Revise 最大辩论轮数 (默认: 2)"
    )
    parser.add_argument(
        "--risk-rounds", type=int, default=2,
        help="风险辩论最大轮数 (默认: 2)"
    )
    parser.add_argument(
        "--stream", action="store_true", default=True,
        help="使用流式输出 (默认开启)"
    )
    parser.add_argument(
        "--no-stream", dest="stream", action="store_false",
        help="使用 invoke 模式（非流式）"
    )
    parser.add_argument(
        "--checkpoint", action="store_true",
        help="启用断点续传 (使用 SQLite)"
    )
    parser.add_argument(
        "--thread-id", default=None,
        help="断点续传的 thread_id (默认自动生成)"
    )
    parser.add_argument(
        "--base-url", default=os.getenv("OPENAI_BASE_URL"),
        help="API Base URL (支持任意 OpenAI 兼容端点)"
    )
    parser.add_argument(
        "--api-key", default=os.getenv("OPENAI_API_KEY"),
        help="API Key"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只打印图结构，不执行"
    )
    parser.add_argument(
        "--project", "-p", action="store_true",
        help="项目模式：审查整个项目目录"
    )
    parser.add_argument(
        "--ext", default=None,
        help="项目模式下过滤的文件扩展名（逗号分隔），如 '.py,.js'"
    )
    parser.add_argument(
        "--exclude", default=None,
        help="项目模式下排除的目录名（逗号分隔），如 'node_modules,venv'"
    )
    parser.add_argument(
        "--max-files", type=int, default=50,
        help="项目模式下最多审查的文件数（默认 50，防止成本过高）"
    )
    return parser.parse_args()


# ==================================================================
# 流式输出格式化
# ==================================================================

_STAGE_ICONS: dict[str, str] = {}


def _stage_label(node_name: str) -> str:
    for key, icon in _STAGE_ICONS.items():
        if key in node_name:
            return f"{icon} {node_name}"
    return node_name


def _truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... (截断，共 {len(text)} 字符)"


def _merge_stream_update(state: dict, node_output: dict) -> dict:
    """把 LangGraph stream 的节点增量合并为可读取的最终状态。"""
    for key, value in node_output.items():
        if key == "messages":
            state.setdefault("messages", [])
            state["messages"].extend(value)
        elif isinstance(value, dict) and isinstance(state.get(key), dict):
            state[key] = {**state[key], **value}
        else:
            state[key] = value
    return state


# ==================================================================
# 主流程
# ==================================================================

def main():
    # ── 加载本地配置文件（在 CLI 解析之前，让配置值填入环境变量） ──
    cfg = load_config()
    _apply_config(cfg)

    args = parse_args()

    # ── 交互式选择文件 ──
    file_path = args.file
    if not file_path:
        file_path = input("请输入待审查文件或项目路径: ").strip()

    path = Path(file_path).resolve()

    # 自动检测：如果路径是目录或指定了 --project，进入项目模式
    is_project_mode = args.project or path.is_dir()

    if is_project_mode:
        run_project_review(args, cfg)
        return

    # ── 单文件模式（原有逻辑） ──
    file_path = str(path)
    if not path.exists():
        print(f"错误: 文件 '{file_path}' 不存在。")
        sys.exit(1)
    if not path.is_file():
        print(f"错误: '{file_path}' 是目录。使用 --project 启用项目模式。")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Code Review 多智能体系统")
    print(f"  目标文件: {file_path}")
    print(f"  分析师: {', '.join(args.analysts)}")
    print(f"  辩论轮数: {args.debate_rounds} | 风险轮数: {args.risk_rounds}")
    print(f"  模型: {args.model}")
    print(f"  模式: {'流式(stream)' if args.stream else '非流式(invoke)'}")
    print(f"{'='*60}\n")

    # ── 初始化 LLM（优先级: CLI > 环境变量 > 配置文件 > 默认值） ──
    llm_kwargs = _resolve_llm_kwargs(args, cfg)
    llm = ChatOpenAI(**llm_kwargs)

    # ── 记忆系统（阶段B: 解析历史） ──
    memory = ReviewMemory()
    past_context = memory.get_past_context(file_path)
    if past_context != "无历史审查记录。":
        print(f"[记忆] 加载历史审查上下文:\n{past_context}\n")

    # ── 构建图 ──
    workflow = build_workflow(
        llm,
        selected_analysts=args.analysts,
        max_debate_rounds=args.debate_rounds,
        max_risk_rounds=args.risk_rounds,
    )

    if args.dry_run:
        print("图结构:")
        app = workflow.compile()
        app.get_graph().print_ascii()
        return

    # ── 可选: 断点续传 ──
    if args.checkpoint:
        with get_checkpointer() as saver:
            app = workflow.compile(checkpointer=saver)
            _run(app, file_path, memory, args)
    else:
        app = workflow.compile()
        _run(app, file_path, memory, args)


def run_project_review(args, cfg: dict):
    """项目审查模式：扫描 → 架构分析 → 逐文件审查 → 汇总报告。"""
    root = str(Path(args.file).resolve())
    if not os.path.isdir(root):
        print(f"错误: '{root}' 不是有效目录。")
        sys.exit(1)

    # 解析扩展名和排除目录
    include_exts = None
    if args.ext:
        include_exts = [e.strip() for e in args.ext.split(",")]
    exclude_dirs = None
    if args.exclude:
        exclude_dirs = [d.strip() for d in args.exclude.split(",")]

    # ── Phase 1: 扫描文件 ──
    print(f"正在扫描项目: {root}")
    files = discover_files(root, include_exts=include_exts, exclude_dirs=exclude_dirs)

    if not files:
        print("未发现任何代码文件。")
        sys.exit(1)

    total = len(files)
    print(f"发现 {total} 个代码文件")

    # 限制文件数
    if total > args.max_files:
        print(f"文件数超过 --max-files ({args.max_files})，仅审查前 {args.max_files} 个文件（按路径排序）。")
        files = files[:args.max_files]
        total = len(files)

    print(f"{'='*60}")
    print(f"  Code Review 多智能体系统 —— 项目模式")
    print(f"  项目路径: {root}")
    print(f"  文件数: {total}")
    print(f"  分析师: {', '.join(args.analysts)}")
    print(f"  辩论轮数: {args.debate_rounds} | 风险轮数: {args.risk_rounds}")
    print(f"  模型: {args.model}")
    print(f"{'='*60}\n")

    # ── 初始化 LLM ──
    llm_kwargs = _resolve_llm_kwargs(args, cfg)
    llm = ChatOpenAI(**llm_kwargs)

    # ── Phase 1b: 项目架构分析 ──
    print(f"\n{'─'*60}")
    print("  Phase 1: 项目架构分析")
    print(f"{'─'*60}\n")

    project_state = {
        "messages": [HumanMessage(content=f"请分析项目结构: {root}")],
        "file_path": root,
        "file_content": "",
        "style_report": "",
        "security_report": "",
        "performance_report": "",
        "logic_report": "",
    }

    project_workflow = build_project_workflow(llm)
    project_app = project_workflow.compile()

    project_context = ""
    try:
        project_result = project_app.invoke(project_state)
        project_context = project_result.get("project_overview", "")
        if project_context:
            print(f"\n{project_context[:800]}")
    except Exception as e:
        print(f"  [WARN] 项目架构分析失败: {e}，继续逐文件审查。")

    # ── Phase 2: 逐文件审查 ──
    print(f"\n{'─'*60}")
    print("  Phase 2: 逐文件审查")
    print(f"{'─'*60}\n")

    memory = ReviewMemory()
    file_workflow = build_workflow(
        llm,
        selected_analysts=args.analysts,
        max_debate_rounds=args.debate_rounds,
        max_risk_rounds=args.risk_rounds,
    )
    file_app = file_workflow.compile()
    file_reports: dict = {}
    file_summaries = []

    for idx, fp in enumerate(files, 1):
        print(f"\n[{idx}/{total}] 审查: {fp}")
        print("-" * 40)

        try:
            initial_state = create_initial_state(
                fp,
                past_context=project_context + "\n" + memory.get_past_context(fp),
            )

            if args.stream:
                final_state = dict(initial_state)
                for chunk in file_app.stream(initial_state):
                    node_name, node_output = next(iter(chunk.items()))
                    final_state = _merge_stream_update(final_state, node_output)
                    msgs = node_output.get("messages", [])
                    if msgs and isinstance(msgs[-1], AIMessage):
                        if not (hasattr(msgs[-1], "tool_calls") and msgs[-1].tool_calls):
                            print(f"  [{node_name}] {_truncate(msgs[-1].content, 120)}")
            else:
                final_state = file_app.invoke(initial_state)

            final_decision = final_state.get("final_decision", "")
            verdict_match = re.search(r"\*\*裁定\*\*[：:]\s*(.+)", final_decision or "")
            verdict = verdict_match.group(1).strip() if verdict_match else "Unknown"

            file_reports[fp] = final_decision
            summary = create_file_summary(fp, verdict, final_decision)
            file_summaries.append(summary)

            memory.save_review(file_path=fp, verdict=verdict, findings_count=0)
            print(f"  → 裁定: {verdict} | Critical={summary.critical_count} "
                  f"Major={summary.major_count} Minor={summary.minor_count}")

        except Exception as e:
            print(f"  [ERROR] 审查 '{fp}' 时出错: {e}")
            file_reports[fp] = f"审查失败: {e}"
            summary = create_file_summary(fp, "Error", "")
            file_summaries.append(summary)

    # ── Phase 3: 汇总报告 ──
    print(f"\n{'─'*60}")
    print("  Phase 3: 生成汇总报告")
    print(f"{'─'*60}\n")

    include_exts_for_report = None
    if args.ext:
        include_exts_for_report = [e.strip() for e in args.ext.split(",")]
    exclude_dirs_for_report = None
    if args.exclude:
        exclude_dirs_for_report = [d.strip() for d in args.exclude.split(",")]

    report = compose_project_report(
        project_root=root,
        file_summaries=file_summaries,
        file_reports=file_reports,
        include_exts=include_exts_for_report,
        exclude_dirs=exclude_dirs_for_report,
    )
    rendered = render_project_report(report)

    print(rendered)

    # 保存报告
    report_path = Path(root) / "CODE_REVIEW_REPORT.md"
    try:
        report_path.write_text(rendered, encoding="utf-8")
        print(f"\n报告已保存到: {report_path}")
    except OSError as e:
        print(f"  [WARN] 无法保存报告: {e}")

    print(f"\n[记忆] 审查结果已保存到 {memory.store_path}")


def _run(app, file_path, memory, args):
    """执行图并处理输出。"""
    initial_state = create_initial_state(
        file_path,
        past_context=memory.get_past_context(file_path),
    )

    config = {}
    if args.checkpoint and args.thread_id:
        config = {"configurable": {"thread_id": args.thread_id}}

    start_time = time.time()

    if args.stream:
        # ── 流式模式（对照 TradingAgents: _run_graph debug 模式） ──
        print(f"{'─'*60}")
        print("  开始审查...")
        print(f"{'─'*60}\n")

        final_state = dict(initial_state)
        for chunk in app.stream(initial_state, config):
            node_name, node_output = next(iter(chunk.items()))
            final_state = _merge_stream_update(final_state, node_output)

            msgs = node_output.get("messages", [])
            if not msgs:
                continue

            last_msg = msgs[-1]

            # 判断消息类型
            if isinstance(last_msg, AIMessage):
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    # 工具调用
                    for tc in last_msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        print(f"  {_stage_label(node_name)} → 调用工具: {tool_name}")
                else:
                    # 纯文本输出
                    print(f"\n{'='*50}")
                    print(f"  {_stage_label(node_name)}")
                    print(f"{'='*50}")
                    print(f"{_truncate(last_msg.content, 500)}")

                    # 检查是否有报告字段更新
                    for field in ["style_report", "security_report", "performance_report", "logic_report"]:
                        val = node_output.get(field, "")
                        if val and val != chunk.get(field, ""):
                            print(f"  [-> {field} 已生成]")
                            break

            elif isinstance(last_msg, ToolMessage):
                content_preview = _truncate(str(last_msg.content), 200)
                print(f"  ← 工具返回 ({len(str(last_msg.content))} 字符)")
                # print(last_msg.content)
        elapsed = time.time() - start_time

    else:
        # ── 非流式模式 ──
        final_state = app.invoke(initial_state, config)
        elapsed = time.time() - start_time

    # ── 结果展示 ──
    print(f"\n{'='*60}")
    print(f"  审查完成 (耗时 {elapsed:.1f}s)")
    print(f"{'='*60}")

    final_decision = final_state.get("final_decision", "")
    if final_decision:
        print(f"\n{final_decision}")

    # ── 记忆系统（阶段A: 存储） ──
    # 提取裁定关键词
    verdict_match = re.search(r"\*\*裁定\*\*[：:]\s*(.+)", final_decision or "")
    verdict = verdict_match.group(1).strip() if verdict_match else "Unknown"
    memory.save_review(
        file_path=file_path,
        verdict=verdict,
        findings_count=0,  # 可从结构化输出中统计
    )
    print(f"\n[记忆] 审查结果已保存到 {memory.store_path}")

    # ── 可选的详细报告 ──
    print(f"\n提示: 将 final_state 打印以查看完整中间结果")


if __name__ == "__main__":
    main()
