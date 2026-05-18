# Code Review Agents

基于 LangGraph + LangChain 的多智能体代码审查工具。它把一次代码审查拆成“专项分析、正反辩论、行动方案、风险评估、最终裁定”几个阶段，适合用于学习多 Agent 工作流，也可以作为自动化代码审查原型。

## 主要功能

- 单文件审查：对指定源码文件生成审查结论。
- 项目级审查：扫描目录，逐文件审查并汇总项目报告。
- 四类专项分析师：`style`、`security`、`performance`、`logic`。
- 多轮辩论：Approve / Revise 两方讨论是否应合入。
- 风险评估：Fast Merge、Quality First、Balanced 三种视角给出风险意见。
- 结构化输出：ReviewPlan、ActionPlan、FinalDecision 等结果由 Pydantic 模型约束。
- 可选断点续跑：通过 SQLite checkpoint 保存 LangGraph 执行状态。
- 历史记忆：将审查摘要保存到本地 JSON，后续审查可复用上下文。

## 安装

建议从项目父目录运行，因为本项目作为 `code_review` 包被调用：

```bash
cd E:\project\study
pip install langgraph langchain-core langchain-openai langgraph-checkpoint-sqlite pydantic grandalf
```

## 配置

复制配置模板：

```bash
copy code_review\config.json.example code_review\config.json
```

编辑 `code_review/config.json`：

```json
{
  "base_url": "https://api.deepseek.com",
  "api_key": "sk-your-api-key-here",
  "model": "deepseek-chat",
  "model_kwargs": {
    "temperature": 0.1
  }
}
```

也可以通过环境变量或命令行参数覆盖：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `REVIEW_MODEL`
- `--api-key`
- `--base-url`
- `--model`

## 使用方式

### 审查单个文件

```bash
python -m code_review.main code_review/test_target.py
```

指定分析师和辩论轮数：

```bash
python -m code_review.main code_review/test_target.py --analysts style security --debate-rounds 3 --risk-rounds 2
```

非流式输出：

```bash
python -m code_review.main code_review/test_target.py --no-stream
```

只查看图结构，不调用 LLM：

```bash
python -m code_review.main code_review/test_target.py --dry-run
```

启用断点续跑：

```bash
python -m code_review.main code_review/test_target.py --checkpoint --thread-id review-v1
```

### 审查整个项目

```bash
python -m code_review.main .\my-project --project
```

限制文件类型、排除目录和最大文件数：

```bash
python -m code_review.main .\my-project --project --ext .py,.js --exclude node_modules,venv --max-files 20
```

项目模式会先扫描项目结构，再逐文件运行审查流程，最后生成项目级汇总报告 `CODE_REVIEW_REPORT.md`。

## 常用参数

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `file` | 待审查文件或目录 | 无 |
| `--project`, `-p` | 启用项目级审查 | 关闭 |
| `--model` | LLM 模型名 | `gpt-4o` |
| `--analysts` | 启用的分析师 | `style security performance logic` |
| `--debate-rounds` | Approve/Revise 辩论轮数 | `2` |
| `--risk-rounds` | 风险辩论轮数 | `2` |
| `--stream` / `--no-stream` | 流式或非流式输出 | 流式 |
| `--checkpoint` | 启用 SQLite 断点续跑 | 关闭 |
| `--thread-id` | checkpoint 线程 ID | 自动生成 |
| `--ext` | 项目模式下包含的扩展名 | 常见源码扩展 |
| `--exclude` | 项目模式下排除的目录 | 常见缓存/依赖目录 |
| `--max-files` | 项目模式最多审查文件数 | `50` |
| `--base-url` | OpenAI 兼容接口地址 | 配置或环境变量 |
| `--api-key` | API Key | 配置或环境变量 |
| `--dry-run` | 只打印图结构 | 关闭 |

## 测试

```bash
cd E:\project\study
python -m pytest code_review/tests -v
```

## 文档

- [系统架构](doc/architecture.md)
- [实现说明](doc/implementation.md)
- [命令行与配置](doc/usage.md)
