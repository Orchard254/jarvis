
"""Phase 2 tests — 9 primitives, safety sandbox, verification router."""
import pytest, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import TOOL_REGISTRY
from safety import executor
from verification import verifier

def test_all_9_tools_registered():
    assert len(TOOL_REGISTRY) == 9

def test_execute_code_safe():
    from tools.execute_code import execute_code
    r = execute_code("print('hello')")
    assert r["success"] and "hello" in r["stdout"]

def test_execute_code_blocks_import():
    from tools.execute_code import execute_code
    r = execute_code("import socket; print('blocked')")
    assert r.get("blocked") or not r["success"]

def test_capture_screen_detects_valid():
    from tools.capture_screen import capture_screen
    r = capture_screen()
    assert r["success"] or r.get("screen_blocked")

def test_safety_executor_runs():
    from tools.notify_user import notify_user
    r = executor.execute("notify_user", notify_user, {"message":"test", "urgency":"low"})
    assert r["success"]

def test_verification_router():
    from tools.execute_code import execute_code
    res = execute_code("import time; time.sleep(0.1)")
    report = verifier.verify_action("execute_code", res, expected="success")
    assert report["status"] in ("CONFIRMED", "INCONCLUSIVE")
