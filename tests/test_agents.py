"""Two-agent architecture smoke tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.execution import run_plan, split_perception_interaction, validate_tool_call
from agents.jarvis import run as jarvis_run


def test_split_perception_interaction():
    plan = {
        "plan_id": "p1",
        "calls": [
            {"call_idx": 1, "tool": "vision_query", "params": {}, "risk_tier": "low"},
            {"call_idx": 2, "tool": "click", "params": {"x": 1, "y": 2}, "risk_tier": "medium"},
        ],
        "execution_policy": "sequential",
    }
    run_plan_slice, deferred = split_perception_interaction(plan)
    assert len(run_plan_slice["calls"]) == 1
    assert run_plan_slice["calls"][0]["tool"] == "vision_query"
    assert len(deferred) == 1
    assert deferred[0]["tool"] == "click"


def test_jarvis_delegates_batch_to_execution(monkeypatch):
    monkeypatch.setattr(
        "agents.execution.validate_tool_call",
        lambda *a, **k: None,
    )

    calls = []

    def mock_chat(messages, tools=None, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            return {
                "content": (
                    'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,'
                    '"tool":"execute_code","params":{"code":"1+1","language":"python"},'
                    '"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}'
                ),
                "tool_calls": None,
                "model": "test",
                "done": True,
            }
        return {"content": "Done.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []

    result = jarvis_run(
        "calc",
        [],
        lambda n, a: executed.append(n) or {"success": True, "output": "2"},
        lambda n, r, e: {"status": "CONFIRMED"},
        valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "execute_code" in executed
