import sys
from pathlib import Path

from langchain_core.messages import AIMessage


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code_review.main import _run


class FakeApp:
    def stream(self, initial_state, config):
        yield {
            "Style Analyst": {
                "messages": [AIMessage(content="style report")],
                "style_report": "style report",
            }
        }
        yield {
            "Lead Reviewer": {
                "messages": [AIMessage(content="final")],
                "final_decision": "**\u88c1\u5b9a**: APPROVE",
            }
        }


class FakeMemory:
    store_path = "memory.json"

    def get_past_context(self, file_path):
        return ""

    def save_review(self, **kwargs):
        self.saved = kwargs


class Args:
    stream = True
    checkpoint = False
    thread_id = None


def test_stream_mode_accumulates_final_decision(capsys):
    memory = FakeMemory()

    _run(FakeApp(), "target.py", memory, Args())

    output = capsys.readouterr().out
    assert "**\u88c1\u5b9a**: APPROVE" in output
    assert memory.saved["verdict"] == "APPROVE"
