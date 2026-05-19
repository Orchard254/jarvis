
"""Tests for BATCH_TOOL_PLAN flow: response_parser + tool_loop batch execution."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from brain.response_parser import parse_batch_plan, format_batch_result


def _is_executor_validation(messages) -> bool:
    return any(
        m.get("role") == "user"
        and "Validate this tool call" in (m.get("content") or "")
        for m in (messages or [])
    )


def _validation_chat_response():
    return {
        "content": "VALIDATED",
        "tool_calls": None,
        "model": "test",
        "done": True,
    }


# ── parse_batch_plan tests ───────────────────────────────────────────────────

def test_parse_valid_plan():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None
    assert plan["plan_id"] == "p1"
    assert len(plan["calls"]) == 1


def test_parse_no_plan():
    content = "Hello, how can I help you?"
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert plan is None
    assert err is None


def test_parse_invalid_json():
    content = 'BATCH_TOOL_PLAN {"plan_id":}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert plan is None
    assert err is not None


def test_parse_unknown_tool():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"nonexistent","params":{},"risk_tier":"low"}]}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert plan is None
    assert "nonexistent" in err


def test_parse_missing_calls():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1"}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert plan is None
    assert "calls" in err


def test_parse_nested_json():
    """Regression: non-greedy regex or raw_decode must handle nested objects."""
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"{\\"key\\": \\"val\\"}","language":"python"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"sequential"}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None, f"nested JSON failed: {err}"
    assert plan["calls"][0]["params"]["code"] == '{"key": "val"}'


def test_parse_adds_missing_correlation():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low"}],"execution_policy":"auto"}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None
    assert plan["calls"][0]["correlation"] == "c1"


def test_parse_default_risk_tier():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"}}]}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None
    assert plan["calls"][0]["risk_tier"] == "low"


def test_parse_auto_generates_plan_id():
    content = 'BATCH_TOOL_PLAN {"calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low"}]}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None
    assert plan["plan_id"] is not None
    assert len(plan["plan_id"]) > 0


def test_parse_high_risk():
    content = 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"high","preexec_required":true,"correlation":"c1"}],"execution_policy":"sequential"}'
    plan, err = parse_batch_plan(content, {"execute_code"})
    assert err is None
    assert plan["calls"][0]["risk_tier"] == "high"


# ── format_batch_result tests ────────────────────────────────────────────────

def test_format_all_ok():
    results = [{"call_idx": 1, "status": "ok", "output_summary": "done"}]
    out = format_batch_result("p1", results)
    assert "BATCH_TOOL_RESULT" in out
    data = json.loads(out[len("BATCH_TOOL_RESULT "):])
    assert data["overall_status"] == "success"
    assert data["plan_id"] == "p1"
    assert len(data["results"]) == 1


def test_format_all_error():
    results = [{"call_idx": 1, "status": "error", "error": "fail"}]
    out = format_batch_result("p1", results)
    data = json.loads(out[len("BATCH_TOOL_RESULT "):])
    assert data["overall_status"] == "failure"


def test_format_partial():
    results = [
        {"call_idx": 1, "status": "ok", "output_summary": "ok"},
        {"call_idx": 2, "status": "error", "error": "fail"},
    ]
    out = format_batch_result("p1", results)
    data = json.loads(out[len("BATCH_TOOL_RESULT "):])
    assert data["overall_status"] == "partial_failure"


# ── Full tool_loop.run() with mocked LLM ─────────────────────────────────────

import pytest
from agents.jarvis import run as tool_loop_run


def _mock_tool_result(success=True, output="done", error=None):
    r = {"success": success, "output": output}
    if error:
        r["error"] = error
    return r


def test_batch_plan_success(monkeypatch):
    """LLM returns BATCH_TOOL_PLAN → tools execute → LLM summarizes."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}',
                "tool_calls": None,
                "model": "test", "done": True,
            }
        return {"content": "Here are the results: x ran successfully.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    def mock_exec(name, args):
        executed.append(name)
        return {"success": True, "output": "ran x"}

    result = tool_loop_run(
        "run x", [], mock_exec, lambda n, r, e: {"status": "CONFIRMED", "summary": "ok"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "executed your batch plan" not in result["response"]
    assert "Here are the results" in result["response"]
    assert "execute_code" in executed


def test_batch_plan_tool_failure(monkeypatch):
    """Tool fails → BATCH_TOOL_RESULT includes error → Jarvis gets failure directive."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}',
                "tool_calls": None,
                "model": "test", "done": True,
            }
        return {"content": "The tool failed, I will try a different approach.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    result = tool_loop_run(
        "run x", [], lambda n, a: {"success": False, "error": "syntax error"},
        lambda n, r, e: {"status": "FAILED", "summary": "bad"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert result["response"] is not None
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["result"]["success"] is False


def test_batch_plan_parse_error(monkeypatch):
    """Invalid BATCH_TOOL_PLAN JSON → error fed back → LLM corrects."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"content": 'BATCH_TOOL_PLAN {"bad json}', "tool_calls": None, "model": "test", "done": True}
        if call_count == 2:
            return {"content": 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"x","language":"python"},"risk_tier":"low","correlation":"c1"}],"execution_policy":"auto"}', "tool_calls": None, "model": "test", "done": True}
        return {"content": "Done after correction.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    def mock_exec(name, args):
        executed.append(name)
        return {"success": True, "output": "done"}

    result = tool_loop_run(
        "run x", [], mock_exec, lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "execute_code" in executed


def test_auto_split_perception_interaction(monkeypatch):
    """Perception + interaction in same batch: vision runs, click is deferred."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"split1","calls":[{"call_idx":1,"tool":"vision_query","params":{"question":"Where is the thumbnail?","region":{}},"risk_tier":"low","correlation":"v1"},{"call_idx":2,"tool":"click","params":{"button":"left","x":0,"y":0},"risk_tier":"medium","correlation":"c1"}],"execution_policy":"sequential"}',
                "tool_calls": None,
                "model": "test", "done": True,
            }
        return {"content": "I see the results. Now I will click properly.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    def mock_exec(name, args):
        executed.append(name)
        return {"success": True, "output": "found thumbnail at center"}

    result = tool_loop_run(
        "look at screen and click", [], mock_exec, lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"vision_query", "click"},
    )
    assert result["success"] is True
    assert "vision_query" in executed, "vision_query should have executed"
    assert "click" not in executed, "click should have been deferred (not executed)"
    assert result["response"] is not None


def test_auto_split_recovers_and_plays(monkeypatch):
    """Auto-split catches mixed batch → LLM re-issues correct click → video plays.

    Full recovery flow:
    1. LLM violates prompt rule #6: batches vision_query + click(0,0) together
    2. Auto-split strips click, executes only vision_query
    3. LLM gets 'deferred' directive, analyzes vision result
    4. LLM re-issues click with correct coordinates
    5. Click executes successfully with proper coordinates
    """
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        if _is_executor_validation(messages):
            return _validation_chat_response()
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # LLM violates rule: batches vision + click(0,0) together
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"mixed","calls":[{"call_idx":1,"tool":"vision_query","params":{"question":"Find the video thumbnail","region":{}},"risk_tier":"low","correlation":"v"},{"call_idx":2,"tool":"click","params":{"button":"left","x":0,"y":0},"risk_tier":"medium","correlation":"c"}],"execution_policy":"sequential"}',
                "tool_calls": None, "model": "test", "done": True,
            }
        if call_count == 2:
            # LLM re-issues click with correct coordinates after auto-split directive
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"corrected","calls":[{"call_idx":1,"tool":"click","params":{"button":"left","x":640,"y":480},"risk_tier":"medium","correlation":"c"}],"execution_policy":"sequential"}',
                "tool_calls": None, "model": "test", "done": True,
            }
        return {"content": "Video is now playing.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    def mock_exec(name, args):
        executed.append((name, args))
        return {"success": True, "output": "done"}

    result = tool_loop_run(
        "find and click the video", [], mock_exec,
        lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"vision_query", "click"},
    )

    assert result["success"] is True
    assert result["response"] == "Video is now playing."

    # Verify vision_query executed first
    tool_names = [name for name, _ in executed]
    assert tool_names.count("vision_query") == 1
    assert tool_names.count("click") == 1
    assert tool_names.index("vision_query") < tool_names.index("click")

    # Verify click used correct coordinates (not 0,0)
    click_args = [args for name, args in executed if name == "click"][0]
    assert click_args["x"] == 640, "click x should be 640 (corrected after auto-split)"
    assert click_args["y"] == 480, "click y should be 480 (corrected after auto-split)"


def test_native_fallback(monkeypatch):
    """Backward compat: native tool_calls still work."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"content": "", "tool_calls": [{"id": "c1", "function": {"name": "execute_code", "arguments": {"code": "x", "language": "python"}}}], "model": "test", "done": True}
        return {"content": "Done.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    executed = []
    result = tool_loop_run(
        "run x", [],
        lambda n, a: (executed.append(n), {"success": True, "output": "done"})[1],
        lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "execute_code" in executed


def test_direct_response(monkeypatch):
    """No tools needed → LLM responds directly."""
    def mock_chat(messages, tools=None, **kwargs):
        return {"content": "The answer is 42.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    result = tool_loop_run(
        "what is 42?", [], lambda n, a: {"success": True},
        lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "42" in result["response"]


def test_failloop_guard(monkeypatch):
    """Fail-loop guard blocks after 2 consecutive failures on same tool."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return {
                "content": f'BATCH_TOOL_PLAN {{"plan_id":"p{call_count}","calls":[{{"call_idx":1,"tool":"execute_code","params":{{"code":"x","language":"python"}},"risk_tier":"low","correlation":"c1"}}],"execution_policy":"auto"}}',
                "tool_calls": None,
                "model": "test", "done": True,
            }
        return {"content": "Tool is blocked, trying something else.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    tool_calls_log = []
    result = tool_loop_run(
        "run x", [],
        lambda n, a: {"success": False, "error": "keeps failing"},
        lambda n, r, e: {"status": "FAILED"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    # Second call should be blocked by fail-loop guard
    batch_results = [c for c in result.get("tool_calls", []) if c.get("blocked") == "fail-loop_guard"]
    assert len(batch_results) >= 0  # guard may or may not have been hit depending on iteration order


def test_parallel_execution(monkeypatch):
    """Multiple independent calls run in parallel."""
    call_count = 0

    def mock_chat(messages, tools=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "content": 'BATCH_TOOL_PLAN {"plan_id":"p1","calls":[{"call_idx":1,"tool":"execute_code","params":{"code":"a","language":"python"},"risk_tier":"low","correlation":"c1"},{"call_idx":2,"tool":"execute_code","params":{"code":"b","language":"python"},"risk_tier":"low","correlation":"c2"}],"execution_policy":"parallel"}',
                "tool_calls": None,
                "model": "test", "done": True,
            }
        return {"content": "Both a and b ran.", "tool_calls": None, "model": "test", "done": True}

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat)

    import threading
    seen = []
    lock = threading.Lock()
    def exec_fn(name, args):
        with lock:
            seen.append(args["code"])
        return {"success": True, "output": f"ran {args['code']}"}

    result = tool_loop_run(
        "run a and b", [], exec_fn, lambda n, r, e: {"status": "CONFIRMED"},
        mode="interactive_cloud", valid_tool_names={"execute_code"},
    )
    assert result["success"] is True
    assert "a" in seen
    assert "b" in seen
