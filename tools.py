"""code_review/tools.py —— 代码分析工具

对照 TradingAgents: tradingagents/agents/utils/core_stock_tools.py 等
每个工具都用 @tool 装饰器，供 LangGraph ToolNode 执行。
"""

import os
import re
from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """读取指定路径的源文件，返回完整内容。"""
    if not os.path.exists(file_path):
        return f"错误：文件 '{file_path}' 不存在。"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) == 0:
            return "文件为空。"
        return content
    except Exception as e:
        return f"读取文件失败: {e}"


@tool
def count_lines(file_path: str = "", content: str = "") -> str:
    """统计代码文件的行数、函数数量和类数量。
    参数 file_path 或 content 二选一。"""
    if file_path and not content:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return f"无法读取文件: {file_path}"
    if not content:
        return "请提供 file_path 或 content。"
    lines = content.split("\n")
    func_names = re.findall(r"^\s*def\s+(\w+)", content, re.MULTILINE)
    class_names = re.findall(r"^\s*class\s+(\w+)", content, re.MULTILINE)
    imports = re.findall(r"^(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", content, re.MULTILINE)
    return (
        f"文件统计:\n"
        f"- 总行数: {len(lines)}\n"
        f"- 函数: {len(func_names)} 个 ({', '.join(func_names) if func_names else '无'})\n"
        f"- 类: {len(class_names)} 个 ({', '.join(class_names) if class_names else '无'})\n"
        f"- 涉及模块: {len(imports)} 个"
    )


@tool
def find_pattern(pattern: str, content: str = "", file_path: str = "") -> str:
    """在代码中搜索指定的正则表达式模式，返回所有匹配行及行号。
    参数 pattern 是正则表达式，content 为代码内容（可选，优先使用）."""
    if not content and file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return f"无法读取文件: {file_path}"
    if not content:
        return "请提供 content 或 file_path。"
    matches = []
    for i, line in enumerate(content.split("\n"), 1):
        try:
            if re.search(pattern, line):
                matches.append(f"  L{i}: {line.strip()[:120]}")
        except re.error:
            return f"正则表达式错误: '{pattern}'"
    if not matches:
        return f"未找到匹配 '{pattern}' 的行。"
    return f"找到 {len(matches)} 处匹配 '{pattern}':\n" + "\n".join(matches[:50])


@tool
def check_sql_injection(content: str = "", file_path: str = "") -> str:
    """检查代码中潜在的 SQL 注入风险：字符串拼接构造SQL、未参数化查询。"""
    if not content and file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return f"无法读取文件: {file_path}"
    if not content:
        return "请提供 content 或 file_path。"
    issues = []
    patterns = [
        (r"execute\s*\(\s*['\"].*%.*['\"]", "SQL 字符串拼接(f-string/%)"),
        (r"execute\s*\(\s*['\"].*\{.*\}.*['\"]", "SQL 字符串拼接(f-string)"),
        (r"execute\s*\(\s*['\"].*\+.*['\"]", "SQL 字符串拼接(+)"),
        (r"\.execute\s*\(\s*[^)]*format\s*\(", "SQL .format() 拼接"),
    ]
    for pat, desc in patterns:
        for i, line in enumerate(content.split("\n"), 1):
            if re.search(pat, line, re.IGNORECASE):
                issues.append(f"  L{i}: [{desc}] {line.strip()[:100]}")
    if not issues:
        return "未发现明显的 SQL 注入风险。"
    return f"发现 {len(issues)} 处潜在 SQL 注入风险:\n" + "\n".join(issues[:30])


# 按分析师类型分组的工具列表（对照 TradingAgents: trading_graph.py _create_tool_nodes）
ANALYST_TOOLS = {
    "style":       [read_file, count_lines, find_pattern],
    "security":    [read_file, find_pattern, check_sql_injection],
    "performance": [read_file, count_lines, find_pattern],
    "logic":       [read_file, find_pattern, count_lines],
}
