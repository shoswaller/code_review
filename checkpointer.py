"""code_review/checkpointer.py —— SQLite 断点续传

对照 TradingAgents: tradingagents/graph/checkpointer.py
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from langgraph.checkpoint.sqlite import SqliteSaver


@contextmanager
def get_checkpointer(db_path: str = "./data/checkpoints.db") -> Generator[SqliteSaver, None, None]:
    """创建 SqliteSaver 上下文管理器。

    使用示例:
        with get_checkpointer() as saver:
            app = workflow.compile(checkpointer=saver)
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()
