"""code_review/main.py —— Code Review 多智能体系统入口

用法:
    python main.py path/to/file.py
    python main.py path/to/file.py --analysts style security logic
    python main.py path/to/file.py --debate-rounds 3 --stream
    python main.py path/to/file.py --checkpoint --thread-id my-review

对照 TradingAgents: cli/main.py
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from .setup import build_workflow, create_initial_state
from .memory import ReviewMemory
from .checkpointer import get_checkpointer


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
    return parser.parse_args()


# ==================================================================
# 流式输出格式化
# ==================================================================

_STAGE_ICONS = {
    "Style": "", "Security": "", "Performance": "", "Logic": "",
    "Approve": "", "Revise": "", "Review Manager": "⚖️",
    "Action": "", "Fast Merge": "", "Quality First": "",
    "Balanced": "⚖️", "Lead": "",
}


def _stage_label(node_name: str) -> str:
    for key, icon in _STAGE_ICONS.items():
        if key in node_name:
            return f"{icon} {node_name}"
    return node_name


def _truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... (截断，共 {len(text)} 字符)"


# ==================================================================
# 主流程
# ==================================================================

def main():
    args = parse_args()

    # ── 交互式选择文件 ──
    file_path = args.file
    if not file_path:
        file_path = input("请输入待审查文件路径: ").strip()
    file_path = os.path.abspath(file_path)
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在。")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Code Review 多智能体系统")
    print(f"  目标文件: {file_path}")
    print(f"  分析师: {', '.join(args.analysts)}")
    print(f"  辩论轮数: {args.debate_rounds} | 风险轮数: {args.risk_rounds}")
    print(f"  模型: {args.model}")
    print(f"  模式: {'流式(stream)' if args.stream else '非流式(invoke)'}")
    print(f"{'='*60}\n")

    # ── 初始化 LLM ──
    llm_kwargs = {"model": args.model}
    if args.base_url:
        llm_kwargs["base_url"] = args.base_url
    if args.api_key:
        llm_kwargs["api_key"] = args.api_key

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

        final_state = None
        for chunk in app.stream(initial_state, config):
            node_name = list(chunk.keys())[0]
            node_output = chunk[node_name]

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
                            print(f"  [↳ {field} 已生成]")
                            break

            elif isinstance(last_msg, ToolMessage):
                content_preview = _truncate(str(last_msg.content), 200)
                print(f"  ← 工具返回 ({len(str(last_msg.content))} 字符)")

            final_state = chunk

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
