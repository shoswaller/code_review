"""code_review/project_scanner.py —— 项目文件扫描与结构分析

扫描目录结构，发现所有代码文件，生成项目概览数据。
"""

import os
import re
from pathlib import Path
from typing import List, Set

from .schemas import ProjectOverview


DEFAULT_INCLUDE_EXTS: Set[str] = {".py", ".js", ".ts", ".tsx", ".jsx",
                                   ".java", ".go", ".rs", ".c", ".cpp",
                                   ".h", ".hpp", ".cs", ".rb", ".php",
                                   ".swift", ".kt", ".scala", ".sh", ".ps1"}

DEFAULT_EXCLUDE_DIRS: Set[str] = {
    "__pycache__", ".git", ".svn", ".hg",
    "node_modules", "venv", ".venv", "env", ".env",
    ".tox", ".eggs", "build", "dist", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".next", ".nuxt",
    "coverage", ".coverage", "htmlcov",
    ".idea", ".vscode", ".claude",
    "target", "out", ".gradle", ".settings",
    "vendor", "bower_components",
    "migrations", ".turbo", ".cache",
    "data", "logs", "tmp", "temp",
}


def discover_files(
    root_dir: str,
    include_exts: List[str] | None = None,
    exclude_dirs: List[str] | None = None,
    exclude_patterns: List[str] | None = None,
) -> List[str]:
    """递归发现项目目录下的所有代码文件。

    Args:
        root_dir: 项目根目录
        include_exts: 包含的扩展名列表，默认 DEFAULT_INCLUDE_EXTS
        exclude_dirs: 排除的目录名列表
        exclude_patterns: 排除的路径模式（glob 风格）

    Returns:
        按路径排序的文件绝对路径列表
    """
    root = Path(root_dir).resolve()
    if not root.is_dir():
        return []

    exts = set(include_exts) if include_exts else DEFAULT_INCLUDE_EXTS
    excl_dirs = set(exclude_dirs) if exclude_dirs else DEFAULT_EXCLUDE_DIRS

    files: List[str] = []
    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        # 跳过排除的目录
        if any(d in excl_dirs for d in entry.parts):
            continue
        # 匹配扩展名
        if entry.suffix.lower() not in exts:
            continue
        # 匹配排除模式
        if exclude_patterns:
            rel = str(entry.relative_to(root))
            if any(Path(rel).match(p) for p in exclude_patterns):
                continue
        files.append(str(entry))

    files.sort()
    return files


def count_stats(file_path: str) -> dict:
    """统计单个文件的代码行数和符号数。"""
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"lines": 0, "functions": 0, "classes": 0}
    lines = content.split("\n")
    func_names = re.findall(r"^\s*(?:def|function|func|fn)\s+(\w+)", content, re.MULTILINE)
    class_names = re.findall(r"^\s*(?:class|interface|struct)\s+(\w+)", content, re.MULTILINE)
    return {
        "lines": len(lines),
        "functions": len(func_names),
        "classes": len(class_names),
    }


def _build_directory_tree(root: Path, files: List[str], max_depth: int = 4) -> str:
    """构建项目目录树的文本表示。"""
    root = root.resolve()
    file_set = {Path(f).resolve() for f in files}
    all_dirs: Set[Path] = set()
    for f in file_set:
        p = f.relative_to(root)
        for parent in list(p.parents)[:-1]:
            all_dirs.add(root / parent)

    lines: List[str] = [str(root.name)]
    entries = list(all_dirs) + list(file_set)
    entries.sort(key=lambda e: (e.is_file(), str(e)))

    for entry in entries:
        try:
            rel = entry.relative_to(root)
        except ValueError:
            continue
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        indent = "│   " * (depth - 1)
        name = entry.name
        if entry.is_dir():
            lines.append(f"{indent}├── {name}/")
        else:
            lines.append(f"{indent}├── {name}")

    return "\n".join(lines)


def analyze_project_structure(
    root_dir: str,
    files: List[str],
) -> ProjectOverview:
    """分析项目结构，生成 ProjectOverview。

    Args:
        root_dir: 项目根目录
        files: 所有代码文件的绝对路径列表
    """
    root = Path(root_dir).resolve()
    total_lines = 0
    total_funcs = 0
    total_classes = 0
    lang_dist: dict = {}

    for fp in files:
        stats = count_stats(fp)
        total_lines += stats["lines"]
        total_funcs += stats["functions"]
        total_classes += stats["classes"]

        ext = Path(fp).suffix.lower()
        lang_name = _ext_to_lang(ext)
        lang_dist[lang_name] = lang_dist.get(lang_name, 0) + 1

    directory_tree = _build_directory_tree(root, files)

    return ProjectOverview(
        project_root=str(root),
        total_files=len(files),
        total_lines=total_lines,
        total_functions=total_funcs,
        total_classes=total_classes,
        language_distribution=lang_dist,
        directory_tree=directory_tree,
    )


def _ext_to_lang(ext: str) -> str:
    """扩展名 → 语言名称映射。"""
    mapping = {
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript(React)",
        ".jsx": "JavaScript(React)",
        ".java": "Java",
        ".go": "Go",
        ".rs": "Rust",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++ Header",
        ".hpp": "C++ Header",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".sh": "Shell",
        ".ps1": "PowerShell",
    }
    return mapping.get(ext, ext.lstrip("."))
