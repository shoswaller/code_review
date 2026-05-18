# 命令行与配置

## 运行位置

推荐从项目父目录运行：

```bash
cd E:\project\study
python -m code_review.main code_review/test_target.py
```

这样可以保证 `from .setup import ...` 这类相对导入正常工作。

## 配置文件

默认读取 `code_review/config.json`。可从模板复制：

```bash
copy code_review\config.json.example code_review\config.json
```

配置示例：

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

配置优先级通常为：命令行参数 > 环境变量 > 配置文件 > 默认值。

## 单文件审查

```bash
python -m code_review.main code_review/test_target.py
```

指定模型：

```bash
python -m code_review.main code_review/test_target.py --model deepseek-chat
```

指定 OpenAI 兼容接口：

```bash
python -m code_review.main code_review/test_target.py --base-url https://api.deepseek.com --api-key sk-your-key
```

只启用部分分析师：

```bash
python -m code_review.main code_review/test_target.py --analysts security logic
```

控制辩论轮数：

```bash
python -m code_review.main code_review/test_target.py --debate-rounds 3 --risk-rounds 3
```

非流式输出：

```bash
python -m code_review.main code_review/test_target.py --no-stream
```

查看图结构，不执行 LLM：

```bash
python -m code_review.main code_review/test_target.py --dry-run
```

启用 checkpoint：

```bash
python -m code_review.main code_review/test_target.py --checkpoint --thread-id my-review
```

## 项目级审查

```bash
python -m code_review.main .\my-project --project
```

只审查指定扩展名：

```bash
python -m code_review.main .\my-project --project --ext .py,.ts,.tsx
```

排除目录：

```bash
python -m code_review.main .\my-project --project --exclude node_modules,venv,dist
```

限制文件数量：

```bash
python -m code_review.main .\my-project --project --max-files 20
```

项目级审查会生成 `CODE_REVIEW_REPORT.md`。

## 参数速查

| 参数 | 说明 |
| --- | --- |
| `file` | 待审查文件或目录 |
| `--project`, `-p` | 启用项目级审查 |
| `--model` | 模型名称 |
| `--analysts` | 启用分析师，可选 `style security performance logic` |
| `--debate-rounds` | Approve/Revise 辩论轮数 |
| `--risk-rounds` | 风险辩论轮数 |
| `--stream` | 使用流式输出 |
| `--no-stream` | 使用非流式输出 |
| `--checkpoint` | 启用 SQLite checkpoint |
| `--thread-id` | checkpoint 线程 ID |
| `--base-url` | OpenAI 兼容 API 地址 |
| `--api-key` | API Key |
| `--dry-run` | 只打印图结构 |
| `--ext` | 项目模式包含的扩展名 |
| `--exclude` | 项目模式排除的目录 |
| `--max-files` | 项目模式最多审查文件数 |

## 测试

```bash
cd E:\project\study
python -m pytest code_review/tests -v
```
