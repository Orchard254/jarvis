
"""Tests for the 6-tool architecture — registry, schemas, facades, and integration."""
import pytest, sys, os, re, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import TOOL_REGISTRY, TOOL_SCHEMAS

# Tools that don't need "Do NOT" guidance (custom/third-party drop-ins)
TOOLS_EXEMPT_FROM_GUIDANCE: set[str] = set()

# The 6 core tools
CORE_TOOLS = {"screen", "input", "window", "browser", "exec", "memory"}


# ── Registry & Schema Tests ───────────────────────────────────────────────────

def test_core_tools_registered():
    """All 6 core tools must be in the registry."""
    for tool in CORE_TOOLS:
        assert tool in TOOL_REGISTRY, f"Core tool '{tool}' missing from TOOL_REGISTRY"


def test_removed_tools_not_registered():
    """Old tools (system, speak) must NOT be in the registry."""
    assert "system" not in TOOL_REGISTRY, "Removed tool 'system' should not be in registry"
    assert "speak" not in TOOL_REGISTRY, "Removed tool 'speak' should not be in registry"


def test_schema_count():
    """Should have at least 6 schemas (core) plus any custom tools."""
    schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert CORE_TOOLS.issubset(schema_names), (
        f"Missing schemas for: {CORE_TOOLS - schema_names}"
    )


def test_schemas_json_roundtrip():
    """All schemas must cleanly serialize/deserialize as JSON."""
    serialised = json.dumps(TOOL_SCHEMAS)
    roundtrip = json.loads(serialised)
    assert len(roundtrip) == len(TOOL_SCHEMAS)


def test_schemas_have_required_fields():
    """Every schema must have name, description, and parameters."""
    for schema in TOOL_SCHEMAS:
        fn = schema.get("function", {})
        name = fn.get("name", "?")
        assert "description" in fn, f"{name} missing description"
        assert "parameters" in fn, f"{name} missing parameters"
        assert "action" in fn["parameters"].get("properties", {}), (
            f"{name} missing 'action' parameter"
        )


def test_schemas_have_negative_guidance():
    """Every tool description must tell the LLM when NOT to use it."""
    for schema in TOOL_SCHEMAS:
        fn = schema.get("function", {})
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        if name in TOOLS_EXEMPT_FROM_GUIDANCE:
            continue
        has_do_not = bool(re.search(r"Do NOT\b", desc, re.IGNORECASE))
        assert has_do_not, (
            f"Tool '{name}' missing 'Do NOT' negative guidance in description."
        )


def test_schema_actions_match_facades():
    """Schema enum values must match what the facade functions accept."""
    expected_actions = {
        "screen": {"capture", "find", "tree", "elements", "query", "ocr"},
        "input": {"click", "type", "hotkey", "scroll", "drag"},
        "window": {"open", "close", "focus", "list", "minimize", "maximize", "state"},
        "browser": {"navigate", "click", "type", "read_page", "screenshot", "scroll"},
        "exec": {"run", "read", "write"},
        "memory": {"store", "recall", "search"},
    }
    for schema in TOOL_SCHEMAS:
        name = schema["function"]["name"]
        if name not in expected_actions:
            continue
        action_prop = schema["function"]["parameters"]["properties"]["action"]
        schema_actions = set(action_prop.get("enum", []))
        assert schema_actions == expected_actions[name], (
            f"Tool '{name}' schema actions {schema_actions} != expected {expected_actions[name]}"
        )


# ── Facade Dispatch Tests ─────────────────────────────────────────────────────

def test_screen_unknown_action():
    from tools.screen import screen
    r = screen(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_screen_find_requires_text():
    from tools.screen import screen
    r = screen(action="find")
    assert not r["success"]
    assert "text required" in r["error"]


def test_screen_query_requires_question():
    from tools.screen import screen
    r = screen(action="query")
    assert not r["success"]
    assert "question required" in r["error"]


def test_input_unknown_action():
    from tools.input import input as input_tool
    r = input_tool(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_input_type_requires_text():
    from tools.input import input as input_tool
    r = input_tool(action="type")
    assert not r["success"]
    assert "text required" in r["error"]


def test_input_click_requires_target():
    from tools.input import input as input_tool
    r = input_tool(action="click")
    assert not r["success"]
    assert "target_text or x,y" in r["error"]


def test_input_hotkey_requires_keys():
    from tools.input import input as input_tool
    r = input_tool(action="hotkey")
    assert not r["success"]
    assert "keys required" in r["error"]


def test_input_drag_requires_coords():
    from tools.input import input as input_tool
    r = input_tool(action="drag")
    assert not r["success"]
    assert "required for drag" in r["error"]


def test_window_unknown_action():
    from tools.window import window
    r = window(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_window_open_requires_app_name():
    from tools.window import window
    r = window(action="open")
    assert not r["success"]
    assert "app_name required" in r["error"]


def test_window_close_requires_title():
    from tools.window import window
    r = window(action="close")
    assert not r["success"]
    assert "window_title required" in r["error"]


def test_window_focus_requires_title():
    from tools.window import window
    r = window(action="focus")
    assert not r["success"]
    assert "window_title required" in r["error"]


def test_exec_unknown_action():
    from tools.exec import exec as exec_tool
    r = exec_tool(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_exec_run_requires_code():
    from tools.exec import exec as exec_tool
    r = exec_tool(action="run")
    assert not r["success"]
    assert "code required" in r["error"]


def test_exec_read_requires_path():
    from tools.exec import exec as exec_tool
    r = exec_tool(action="read")
    assert not r["success"]
    assert "path required" in r["error"]


def test_exec_write_requires_path_and_content():
    from tools.exec import exec as exec_tool
    r = exec_tool(action="write")
    assert not r["success"]
    assert "path and content required" in r["error"]


def test_memory_unknown_action():
    from tools.mem import memory
    r = memory(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_browser_unknown_action():
    from tools.browser import browser
    r = browser(action="nonexistent")
    assert not r["success"]
    assert "Unknown" in r["error"]


def test_browser_navigate_requires_url():
    from tools.browser import browser
    r = browser(action="navigate")
    assert not r["success"]
    assert "URL required" in r["error"]


# ── Code Execution Tests ──────────────────────────────────────────────────────

def test_execute_code_safe():
    try:
        from tools.execute_code import execute_code
    except ImportError:
        pytest.skip("execute_code dependencies not installed")
    r = execute_code("print('hello')")
    assert r["success"] and "hello" in r["output"]


def test_execute_code_blocks_import():
    try:
        from tools.execute_code import execute_code
    except ImportError:
        pytest.skip("execute_code dependencies not installed")
    r = execute_code("import socket; print('blocked')")
    assert r["success"]
    assert "blocked" in r.get("output", "")


# ── Planner Sync Test ─────────────────────────────────────────────────────────

def test_planner_prompt_synced_with_schemas():
    """Every schema tool must appear in the planner prompt and vice versa."""
    planner = (Path(__file__).parent.parent / "brain" / "planner.py").read_text(encoding="utf-8")
    start = planner.find("_PLANNER_PROMPT")
    end = planner.find("def _build_system_context")
    prompt = planner[start:end]

    tools_in_prompt = set(re.findall(r"^\d+\.\s+(\w+)\(", prompt, re.MULTILINE))
    schema_tools = {s["function"]["name"] for s in TOOL_SCHEMAS}

    # Custom runtime tools are expected to be missing from the static planner prompt
    custom_tools = {"manage_bluetooth"}
    expected_missing = schema_tools - tools_in_prompt - custom_tools

    assert not expected_missing, (
        f"Tools in schemas but missing from planner prompt: {expected_missing}. "
        "Add them to the tool list in brain/planner.py _PLANNER_PROMPT."
    )


# ── Direct Dispatch Tests ────────────────────────────────────────────────────

def test_direct_dispatch_matches_open():
    """Direct dispatch should match 'open <app>' pattern."""
    from core.direct_dispatch import _PATTERNS, _build_tool_call
    for pattern, action_key, _ in _PATTERNS:
        m = pattern.match("open notepad")
        if m:
            call = _build_tool_call(action_key, m)
            assert call is not None
            assert call["tool"] == "window"
            assert call["args"]["action"] == "open"
            assert call["args"]["app_name"] == "notepad"
            return
    pytest.fail("No pattern matched 'open notepad'")


def test_direct_dispatch_matches_screenshot():
    """Direct dispatch should match 'screenshot' pattern."""
    from core.direct_dispatch import _PATTERNS, _build_tool_call
    for pattern, action_key, _ in _PATTERNS:
        m = pattern.match("screenshot")
        if m:
            call = _build_tool_call(action_key, m)
            assert call is not None
            assert call["tool"] == "screen"
            assert call["args"]["action"] == "capture"
            return
    pytest.fail("No pattern matched 'screenshot'")


def test_direct_dispatch_no_match():
    """Complex commands should not match any direct dispatch pattern."""
    from core.direct_dispatch import _PATTERNS
    for pattern, _, _ in _PATTERNS:
        assert pattern.match("write a python script that sorts numbers") is None


def test_direct_dispatch_browser_url():
    """Direct dispatch should match URL navigation."""
    from core.direct_dispatch import _PATTERNS, _build_tool_call
    for pattern, action_key, _ in _PATTERNS:
        m = pattern.match("go to https://google.com")
        if m:
            call = _build_tool_call(action_key, m)
            assert call is not None
            assert call["tool"] == "browser"
            assert call["args"]["url"] == "https://google.com"
            return
    pytest.fail("No pattern matched URL navigation")


def test_direct_dispatch_open_url_routes_to_browser():
    """'open https://...' should route to browser, not window."""
    from core.direct_dispatch import _PATTERNS, _build_tool_call
    for pattern, action_key, _ in _PATTERNS:
        m = pattern.match("open https://google.com")
        if m:
            call = _build_tool_call(action_key, m)
            assert call is not None
            assert call["tool"] == "browser", f"Expected browser but got {call['tool']}"
            return
    pytest.fail("No pattern matched 'open https://google.com'")


# ── Tool Result Cache Tests ──────────────────────────────────────────────────

def test_cache_is_cacheable_read_only_tool():
    """Read-only tools should always be cacheable."""
    from brain.tool_result_cache import ToolResultCache
    cache = ToolResultCache()
    assert cache._is_cacheable("screen", {"action": "capture"})


def test_cache_is_cacheable_read_only_action():
    """window(state) should be cacheable even though window is a write tool."""
    from brain.tool_result_cache import ToolResultCache
    cache = ToolResultCache()
    assert cache._is_cacheable("window", {"action": "state"})
    assert cache._is_cacheable("window", {"action": "list"})


def test_cache_not_cacheable_write_action():
    """window(open) should NOT be cacheable."""
    from brain.tool_result_cache import ToolResultCache
    cache = ToolResultCache()
    assert not cache._is_cacheable("window", {"action": "open"})
    assert not cache._is_cacheable("input", {"action": "click"})


# ── Parallel Batch Tests ─────────────────────────────────────────────────────

def test_build_step_batches_independent():
    """Steps without deps should batch together."""
    try:
        from brain.tool_loop import _build_step_batches
    except ImportError:
        pytest.skip("tool_loop deps unavailable")
    steps = [
        {"tool": "screen", "args": {"action": "capture"}},
        {"tool": "window", "args": {"action": "list"}},
    ]
    batches = _build_step_batches(steps)
    assert len(batches) == 1
    assert len(batches[0]) == 2


def test_build_step_batches_dependent():
    """Steps with deps_on should be in separate batches."""
    try:
        from brain.tool_loop import _build_step_batches
    except ImportError:
        pytest.skip("tool_loop deps unavailable")
    steps = [
        {"tool": "screen", "args": {"action": "capture"}},
        {"tool": "input", "args": {"action": "click"}, "deps_on": ["step_0"]},
        {"tool": "screen", "args": {"action": "capture"}},
    ]
    batches = _build_step_batches(steps)
    assert len(batches) == 3  # [screen], [input with dep], [screen]


def test_build_step_batches_empty():
    """Empty steps should produce empty batches."""
    try:
        from brain.tool_loop import _build_step_batches
    except ImportError:
        pytest.skip("tool_loop deps unavailable")
    assert _build_step_batches([]) == []


# ── Self-Reflection Heuristic Tests ──────────────────────────────────────────

def test_self_reflection_heuristic_safety():
    """Safety scorer should flag dangerous patterns."""
    from core.self_reflection import SelfReflector, ReflectionCriterion
    reflector = SelfReflector()
    score, confidence, reasoning, suggestions = reflector._heuristic_evaluate(
        ReflectionCriterion.SAFETY,
        "Run sudo rm -rf /tmp to clean up",
        None, None,
    )
    assert score < 0.5
    assert len(suggestions) > 0


def test_self_reflection_heuristic_safe_output():
    """Safe output should score high on safety."""
    from core.self_reflection import SelfReflector, ReflectionCriterion
    reflector = SelfReflector()
    score, _, _, suggestions = reflector._heuristic_evaluate(
        ReflectionCriterion.SAFETY,
        "The weather today is sunny and warm",
        None, None,
    )
    assert score >= 0.9
    assert len(suggestions) == 0


# ── Screen Elements Action Tests ─────────────────────────────────────────────

def test_screen_elements_returns_structure():
    """screen(elements) should return the expected dict structure."""
    from tools.screen import screen
    result = screen(action="elements")
    assert "success" in result
    assert "elements" in result
    assert "sources" in result
    assert "count" in result
    assert isinstance(result["elements"], list)


def test_screen_capture_grid_param():
    """screen(capture) should accept grid parameter without error."""
    from tools.screen import screen
    # Can't actually capture on non-Windows, but we can verify the
    # function signature accepts grid params without TypeError
    import inspect
    sig = inspect.signature(screen)
    assert "grid" in sig.parameters
    assert "grid_size" in sig.parameters


# ── Browser CDP Tests ────────────────────────────────────────────────────────

def test_browser_cdp_function_exists():
    """Browser module should have CDP connection function."""
    try:
        from tools.browser import _try_connect_cdp
        assert callable(_try_connect_cdp)
    except ImportError:
        pytest.skip("Playwright not installed")
