
"""Phase 4 tests — Brain, context pruning, and tool loop logic (mocked)."""
import pytest, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from brain.ollama_client import OllamaError
from brain.context_manager import prune_history, estimate_tokens
from brain.prompt_builder import build_system_prompt, get_pruned_schemas
from brain.response_parser import validate_tool_calls
from brain.tool_loop import run

def test_system_prompt_contains_rules():
    prompt = build_system_prompt()
    assert "query_pc_index" in prompt
    assert "execute_code" in prompt

def test_context_manager_prunes_heavy_history():
    msgs = [{"role": "user", "content": "test"}] * 30
    pruned = prune_history(msgs, budget=50)
    assert len(pruned) < 30

def test_response_parser_validates_tools():
    valid, err = validate_tool_calls([{"function": {"name": "execute_code", "arguments": {"code": "x"}}}], {"execute_code"})
    assert valid is True

def test_response_parser_blocks_unknown():
    valid, err = validate_tool_calls([{"function": {"name": "fake_tool", "arguments": {}}}], {"execute_code"})
    assert valid is False

def test_tool_loop_executes_callbacks(monkeypatch):
    call_count = 0
    def mock_chat(messages, tools=None, temperature=0.2, model=None, max_retries=2):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"content": "", "tool_calls": [{"id": "1", "function": {"name": "read_pc_state", "arguments": {}}}], "model": "test", "done": True}
        return {"content": "Done.", "tool_calls": None, "model": "test", "done": True}

    def mock_chat_stream(messages, tools=None, model=None, temperature=0.2, print_chunks=True):
        return mock_chat(messages, tools=tools, temperature=temperature, model=model)

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat_stream)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    verified = []
    def mock_exec(name, args):
        executed.append(name)
        return {"success": True}
    def mock_verify(name, res, exp):
        verified.append(name)
        return {"status": "CONFIRMED", "summary": "ok"}

    result = run("test", [], mock_exec, mock_verify, mode="interactive_cloud")
    assert call_count == 2
    assert "read_pc_state" in executed
    assert result["success"] is True
    assert "Done." in result["response"]
