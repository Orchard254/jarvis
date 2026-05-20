"""Sub-agent smoke tests: all 6 agents load, run, and return valid result shape."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import SubAgentTask, SubAgentResult
from agents.sub_agent_registry import registry


def _mock_execute(tool_name: str, args: dict) -> dict:
    return {"success": True, "data": {}, "message": "mock ok"}


def _mock_verify(tool_name: str, result: dict, goal: str) -> dict:
    return {"status": "CONFIRMED"}


def test_registry_has_all_agents():
    agents = registry.list_agents()
    names = {a["name"] for a in agents}
    for expected in ("research", "file", "system", "perception", "interaction", "memory"):
        assert expected in names, f"Missing sub-agent: {expected}"


def _make_agent(name: str):
    agent = registry.get(name)
    assert agent is not None, f"Agent '{name}' not found"
    agent.__init__(execute_fn=_mock_execute, verify_fn=_mock_verify)
    return agent


def test_research_agent():
    agent = _make_agent("research")
    task = SubAgentTask(goal="search for news", context={"query": "test", "max_results": 2})
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)
    assert isinstance(result.summary, str)
    assert isinstance(result.data, dict)
    assert isinstance(result.tool_calls, list)


def test_file_agent():
    agent = _make_agent("file")
    task = SubAgentTask(goal="read test.txt", context={"operation": "read", "path": "/tmp/test.txt"})
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)


def test_system_agent():
    agent = _make_agent("system")
    task = SubAgentTask(goal="check system stats", context={"operation": "stats"})
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)


def test_perception_agent():
    agent = _make_agent("perception")
    task = SubAgentTask(goal="describe the screen")
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)
    assert "source" in result.data
    assert result.data.get("vision_attempted") is True


def test_interaction_agent():
    agent = _make_agent("interaction")
    task = SubAgentTask(
        goal="click at (100, 200)",
        context={"actions": [{"tool": "click", "params": {"x": 100, "y": 200}}]},
    )
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)


def test_memory_agent():
    agent = _make_agent("memory")
    task = SubAgentTask(goal="store my preference", context={"operation": "store", "key": "theme", "value": "dark"})
    result = agent.run(task)
    assert isinstance(result, SubAgentResult)
    assert isinstance(result.success, bool)


def test_system_agent_auto_detection():
    agent = _make_agent("system")
    task1 = SubAgentTask(goal="Set system volume to 40 percent")
    result1 = agent.run(task1)
    assert result1.success is True
    assert len(result1.tool_calls) > 0
    assert result1.tool_calls[0]["tool"] == "set_volume"
    assert result1.tool_calls[0]["level"] == 40

    task2 = SubAgentTask(goal="Change brightness to 80")
    result2 = agent.run(task2)
    assert result2.success is True
    assert len(result2.tool_calls) > 0
    assert result2.tool_calls[0]["tool"] == "set_brightness"
    assert result2.tool_calls[0]["level"] == 80
