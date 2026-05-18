"""Tests for Director + Execution agent flow."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from agents.director import JarvisAgent
from agents.execution import ExecutionAgent


def _mock_exec(tool_name, args):
    return {"success": True, "output": f"ran {tool_name}", "data": {}}


def _mock_verify(tool_name, result, expected):
    return {"status": "CONFIRMED"}


def test_director_process_returns_dict():
    agent = JarvisAgent()
    result = agent.process("hello", history=[])
    assert isinstance(result, dict)
    assert "response" in result or "delegate_task" in result


def test_execution_execute_task_returns_list():
    agent = ExecutionAgent(_mock_exec, _mock_verify)
    results = agent.execute_task("open notepad")
    assert isinstance(results, list)


def test_execution_execute_task_result_has_tool():
    agent = ExecutionAgent(_mock_exec, _mock_verify)
    results = agent.execute_task("open notepad")
    if results:
        assert "tool" in results[0]


def test_director_summarize_returns_string():
    agent = JarvisAgent()
    summary = agent.summarize("open notepad", [{"tool": "open_app", "result": {"success": True}}], [])
    assert isinstance(summary, str)
    assert len(summary) > 0
