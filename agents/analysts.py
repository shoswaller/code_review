"""code_review/agents/analysts.py —— 第一层：四个代码分析师

对照 TradingAgents: tradingagents/agents/analysts/

每个分析师:
1. 绑定特定的工具集
2. 有领域化的 system prompt
3. 返回图节点函数（接受 state，返回 {messages: [...]} + 报告字段）

工具循环由 conditional_logic 中的路由函数控制：LLM 发起 tool_call → ToolNode 执行 → 分析师继续 → ...
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from ..tools import read_file, count_lines, find_pattern, check_sql_injection


# ── 分析师工厂 ──

def _create_analyst(
    llm: Any,
    name: str,
    tools: list,
    system_prompt: str,
    report_field: str,
) -> callable:
    """分析师节点工厂。

    Args:
        llm: 语言模型实例
        name: 分析师名称（如 "Style"）
        tools: 绑定的工具列表
        system_prompt: 系统提示
        report_field: 报告中存入 state 的字段名
    """
    llm_with_tools = llm.bind_tools(tools)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "请审查文件: {file_path}\n\n提示：先用 read_file 读取文件，再用其他工具深入分析，最后给出完整的审查报告。"),
    ])

    chain = prompt | llm_with_tools

    def node(state):
        result = chain.invoke({"file_path": state["file_path"]})
        # 如果消息中不含 tool_calls，说明报告已完成，存入对应字段
        updates = {"messages": [result]}
        if isinstance(result, AIMessage) and not (hasattr(result, "tool_calls") and result.tool_calls):
            updates[report_field] = result.content
        return updates

    return node


# ── 1. 风格分析师 ──

_STYLE_PROMPT = """你是一位资深代码风格审查专家，负责审查代码的可读性和一致性。

## 审查维度
1. **命名规范**: 变量、函数、类名是否符合语言惯例（Python PEP8）
2. **代码格式**: 缩进一致性、空行使用、行长度（建议 ≤120 字符）
3. **注释质量**: 是否有必要的注释？注释是否过时或误导？
4. **代码组织**: import 顺序、函数/类的排列逻辑

## 工作流程
1. 用 read_file 读取文件内容
2. 用 count_lines 了解代码规模
3. 用 find_pattern 搜索具体模式（如过长的行、不一致的命名风格等）
4. 输出风格审查报告

## 输出格式
### 风格审查报告
**总体评价**: [1-2 句]
**发现的问题**:
- [严重度] 问题描述 → 具体建议
"""


def create_style_analyst(llm):
    return _create_analyst(
        llm, "Style",
        [read_file, count_lines, find_pattern],
        _STYLE_PROMPT,
        "style_report",
    )


# ── 2. 安全分析师 ──

_SECURITY_PROMPT = """你是一位资深代码安全审查专家，负责发现代码中的安全漏洞和风险。

## 审查维度
1. **注入风险**: SQL 注入、命令注入、模板注入
2. **危险函数**: eval()、exec()、pickle.loads() 等
3. **硬编码密钥**: API key、密码、token 硬编码
4. **路径遍历**: 文件操作是否校验路径？
5. **不安全的反序列化**: pickle、yaml.load 等

## 工作流程
1. 用 read_file 读取文件
2. 用 check_sql_injection 检查 SQL 注入
3. 用 find_pattern 搜索 eval、exec、硬编码密钥等模式
4. 输出安全审查报告

## 输出格式
### 安全审查报告
**风险等级**: [高/中/低]
**发现的安全问题**:
- [严重度] 问题描述（含行号）→ 修复建议
"""


def create_security_analyst(llm):
    return _create_analyst(
        llm, "Security",
        [read_file, find_pattern, check_sql_injection],
        _SECURITY_PROMPT,
        "security_report",
    )


# ── 3. 性能分析师 ──

_PERFORMANCE_PROMPT = """你是一位资深代码性能审查专家，负责发现性能瓶颈和优化机会。

## 审查维度
1. **算法复杂度**: 嵌套循环导致的 O(n²) 或更差
2. **不必要的 I/O**: 循环中的文件/数据库/网络请求
3. **内存使用**: 大对象持有、未释放资源、内存泄漏风险
4. **字符串操作**: 循环中的 += 拼接（应用 list+join）
5. **缓存机会**: 重复计算的结果是否可缓存？

## 工作流程
1. 用 read_file 读取文件
2. 用 count_lines 了解代码规模
3. 用 find_pattern 搜索嵌套循环、循环内 I/O 等模式
4. 输出性能审查报告

## 输出格式
### 性能审查报告
**总体评价**: [1-2 句]
**性能问题**:
- [严重度] 问题描述（含行号）→ 优化建议
"""


def create_performance_analyst(llm):
    return _create_analyst(
        llm, "Performance",
        [read_file, count_lines, find_pattern],
        _PERFORMANCE_PROMPT,
        "performance_report",
    )


# ── 4. 逻辑/正确性分析师 ──

_LOGIC_PROMPT = """你是一位资深代码逻辑审查专家，负责发现逻辑错误和边界条件问题。

## 审查维度
1. **边界条件**: 空列表/None/零值处理、数组越界
2. **异常处理**: try-except 是否过于宽泛（裸 except）？是否正确重新抛出？
3. **类型安全**: 类型转换是否正确？是否存在隐式类型转换风险？
4. **流程控制**: 死循环风险、不可达代码、缺失的 return
5. **并发安全**: 共享状态是否有竞态风险？

## 工作流程
1. 用 read_file 读取文件
2. 用 find_pattern 搜索 except: / except Exception / while True 等模式
3. 逐一分析关键函数的逻辑流
4. 输出逻辑审查报告

## 输出格式
### 逻辑审查报告
**总体评价**: [1-2 句]
**逻辑问题**:
- [严重度] 问题描述（含行号）→ 修复建议
"""


def create_logic_analyst(llm):
    return _create_analyst(
        llm, "Logic",
        [read_file, find_pattern, count_lines],
        _LOGIC_PROMPT,
        "logic_report",
    )
