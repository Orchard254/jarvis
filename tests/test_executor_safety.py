"""Tests for safety/executor.py — the unified safety funnel."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from safety.executor import execute


def _make_tool(success=True, **extras):
    def tool_fn(**kwargs):
        return {"success": success, **extras}
    return tool_fn


def test_basic_execute_success(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("get_battery", _make_tool(battery_percent=85), {})
    assert result["success"] is True
    assert result["data"]["battery_percent"] == 85


def test_execute_non_dict_return(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    def bad_tool(**kw):
        return "not a dict"
    result = execute("get_battery", bad_tool, {})
    assert result["success"] is False


def test_execute_blocked_path(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("read_file", _make_tool(), {"path": "C:/Users/Test/.ssh/id_rsa"})
    assert result["success"] is False
    assert result.get("blocked") is True


def test_execute_code_blocks_disallowed_import(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("execute_code", _make_tool(),
                     {"code": "import some_hacked_lib", "language": "python"})
    assert result["success"] is False
    assert result.get("blocked") is True


def test_write_file_blocks_dangerous_content(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("write_file", _make_tool(),
                     {"path": "C:/Users/Test/test.ps1", "content": "schtasks /create ..."})
    assert result["success"] is False
    assert result.get("blocked") is True


def test_approved_bypasses_high_risk(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("write_file", _make_tool(),
                     {"path": "C:/test.txt", "content": "hello"},
                     plan={"approved": True, "confidence": 0.95})
    assert result["success"] is True


def test_missing_required_param_blocked(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("write_file", _make_tool(), {})
    assert result["success"] is False
    assert result.get("blocked") is True


def test_result_envelope_has_timestamp(monkeypatch):
    monkeypatch.setattr("safety.audit_log.log_call", lambda *a, **kw: None)
    monkeypatch.setattr("safety.audit_log.log_blocked", lambda *a, **kw: None)
    result = execute("get_battery", _make_tool(), {})
    assert "timestamp" in result
    assert "message" in result
    assert "data" in result
