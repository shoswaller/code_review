"""code_review/memory.py —— 持久化审查记忆

对照 TradingAgents: tradingagents/agents/utils/memory.py

记录每次审查的结果，在下一次审查时注入历史上下文。
"""

import json
import os
from datetime import datetime


class ReviewMemory:
    """简单的文件持久化审查记忆。

    两阶段机制：
    阶段A（存储）：审查完成后存储审查记录
    阶段B（注入）：下次审查时注入历史上下文
    """

    def __init__(self, store_path: str = "./data/review_history.json"):
        self.store_path = store_path
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        if not os.path.exists(self.store_path):
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _read_all(self):
        with open(self.store_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []

    def save_review(
        self,
        file_path: str,
        verdict: str,
        findings_count: int,
        risk_level: str = "",
    ):
        """保存一次审查记录（阶段A）。"""
        records = self._read_all()
        records.append({
            "file": file_path,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "verdict": verdict,
            "findings_count": findings_count,
            "risk_level": risk_level,
            "was_useful": True,
        })
        # 原子写入: 写临时文件 → os.replace
        tmp = self.store_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.store_path)

    def get_past_context(self, file_path: str = None, limit: int = 3) -> str:
        """获取历史审查摘要（阶段B）。"""
        records = self._read_all()

        if file_path:
            same_file = [r for r in records if r["file"] == file_path]
            cross_file = [r for r in records if r["file"] != file_path]
        else:
            same_file = []
            cross_file = records

        lines = []

        if same_file:
            recent_same = same_file[-limit:]
            lines.append("## 本文件历史审查")
            for r in recent_same:
                lines.append(
                    f"- [{r['date']}] 裁定: {r['verdict']} | "
                    f"发现 {r['findings_count']} 个问题 | 风险: {r.get('risk_level', '未知')}"
                )

        if cross_file:
            recent_cross = cross_file[-limit:]
            lines.append("\n## 其他文件审查参考")
            for r in recent_cross:
                lines.append(
                    f"- [{r['date']}] {r['file']}: {r['verdict']} "
                    f"({r['findings_count']} 个问题)"
                )

        if not lines:
            return "无历史审查记录。"

        return "\n".join(lines)
