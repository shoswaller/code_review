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


# ── 项目级工具 ──

@tool
def list_project_files(directory: str, pattern: str = "*") -> str:
    """列出项目目录下所有匹配的源文件。用于了解项目结构。
    参数 directory: 项目根目录路径。
    参数 pattern: 文件名匹配模式，默认 * 表示所有。"""
    import os as _os
    from pathlib import Path as _Path

    root = _Path(directory)
    if not root.is_dir():
        return f"错误: '{directory}' 不是有效目录。"

    files = sorted(root.rglob(pattern))
    # 过滤常见的非代码目录
    skip_dirs = {"__pycache__", ".git", "node_modules", "venv", ".venv",
                 "build", "dist", ".idea", ".vscode", ".claude"}
    result = []
    for f in files:
        if f.is_file() and not any(d in skip_dirs for d in f.parts):
            result.append(str(f.relative_to(root)))

    if not result:
        return f"在 '{directory}' 中未找到匹配 '{pattern}' 的文件。"
    return f"在 '{directory}' 中找到 {len(result)} 个文件:\n" + "\n".join(result[:100])


@tool
def get_directory_structure(root_dir: str, max_depth: int = 3) -> str:
    """返回项目目录的树形结构。用于了解项目组织方式。
    参数 root_dir: 项目根目录。
    参数 max_depth: 最大深度，默认 3。"""
    from pathlib import Path as _Path

    root = _Path(root_dir)
    if not root.is_dir():
        return f"错误: '{root_dir}' 不是有效目录。"

    skip = {"__pycache__", ".git", "node_modules", "venv", ".venv",
            "build", "dist", ".idea", ".vscode", ".claude"}

    lines = [root.name + "/"]

    def _walk(path: _Path, depth: int, prefix: str = ""):
        if depth > max_depth:
            return
        try:
            entries = sorted([e for e in path.iterdir() if e.name not in skip],
                           key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                ext_prefix = "    " if i == len(entries) - 1 else "│   "
                _walk(entry, depth + 1, prefix + ext_prefix)
            elif entry.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx",
                                           ".java", ".go", ".rs", ".c", ".cpp",
                                           ".h", ".hpp", ".cs", ".rb", ".php",
                                           ".swift", ".kt", ".sh", ".ps1"}:
                lines.append(f"{prefix}{connector}{entry.name}")

    _walk(root, 1)
    return "\n".join(lines[:80])


@tool
def analyze_imports(file_path: str = "", content: str = "") -> str:
    """分析 Python 文件的 import 依赖关系。
    参数 file_path 和 content 二选一。"""
    if not content and file_path:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return f"无法读取文件: {file_path}"
    if not content:
        return "请提供 file_path 或 content。"

    import re as _re
    internal = []
    external = []
    stdlib = _re.findall(r"^(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)", content, _re.MULTILINE)

    _STDLIB = {"os", "sys", "re", "json", "time", "datetime", "pathlib", "typing",
               "collections", "itertools", "functools", "math", "random", "io",
               "subprocess", "logging", "unittest", "argparse", "hashlib", "uuid",
               "copy", "textwrap", "shutil", "tempfile", "glob", "fnmatch"}

    for m in stdlib:
        name = m[0] or m[1]
        if not name:
            continue
        top = name.split(".")[0]
        if top in _STDLIB:
            continue
        if top.startswith("."):
            internal.append(name)
        elif any(name.startswith(pkg) for pkg in
                 {"langchain", "pydantic", "langgraph", "openai", "anthropic"}):
            external.append(name)
        else:
            external.append(name)

    parts = []
    if internal:
        parts.append(f"内部/相对导入: {', '.join(internal)}")
    if external:
        parts.append(f"外部/第三方导入: {', '.join(external)}")
    if not parts:
        parts.append("未发现明显的非标准库依赖。")
    return "\n".join(parts)


@tool
def detect_project_type(root_dir: str) -> str:
    """检测项目的技术栈类型。通过分析目录结构和配置文件来判断。
    参数 root_dir: 项目根目录。"""
    from pathlib import Path as _Path

    root = _Path(root_dir)
    if not root.is_dir():
        return f"错误: '{root_dir}' 不是有效目录。"

    root_files = {f.name for f in root.iterdir() if f.is_file()}
    result = []

    if "package.json" in root_files:
        result.append("Node.js/JavaScript 项目")
    if "pyproject.toml" in root_files or "setup.py" in root_files or "requirements.txt" in root_files:
        result.append("Python 项目")
    if "pom.xml" in root_files or "build.gradle" in root_files:
        result.append("Java/Kotlin 项目")
    if "Cargo.toml" in root_files:
        result.append("Rust 项目")
    if "go.mod" in root_files:
        result.append("Go 项目")
    if ".sln" in root_files or any(f.endswith(".csproj") for f in root_files):
        result.append(".NET/C# 项目")
    if "CMakeLists.txt" in root_files:
        result.append("C/C++ 项目")
    if "composer.json" in root_files:
        result.append("PHP 项目")
    if "Gemfile" in root_files:
        result.append("Ruby 项目")

    if not result:
        result.append("通用项目（未检测到特定技术栈标识）")

    return "检测到: " + " | ".join(result)


# 按分析师类型分组的工具列表（对照 TradingAgents: trading_graph.py _create_tool_nodes）
ANALYST_TOOLS = {
    "style":       [read_file, count_lines, find_pattern],
    "security":    [read_file, find_pattern, check_sql_injection],
    "performance": [read_file, count_lines, find_pattern],
    "logic":       [read_file, find_pattern, count_lines],
    "project":     [list_project_files, get_directory_structure, analyze_imports,
                    detect_project_type, read_file, count_lines],
}
