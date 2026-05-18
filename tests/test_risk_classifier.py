"""Tests for safety/risk_classifier.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from safety.risk_classifier import classify_risk, requires_approval


class TestClassifyRisk:
    def test_high_risk_tool(self):
        assert classify_risk("shutdown") == "high"

    def test_medium_risk_tool(self):
        assert classify_risk("send_message") == "medium"

    def test_low_risk_tool(self):
        assert classify_risk("get_battery") == "low"

    def test_path_system32_escalates(self):
        assert classify_risk("read_file", {"path": "C:/Windows/System32/config"}) == "high"

    def test_path_windows_dir_escalates(self):
        assert classify_risk("read_file", {"path": "C:\\Windows\\System32"}) == "high"

    def test_path_windows_substring_no_false_positive(self):
        assert classify_risk("read_file", {"path": "C:/Users/Test/windows_theme.png"}) == "low"

    def test_command_shutdown_escalates(self):
        assert classify_risk("execute_code", {"command": "shutdown /s /t 0"}) == "high"

    def test_empty_params_no_escalation(self):
        assert classify_risk("read_file") == "low"

    def test_params_none(self):
        assert classify_risk("read_file", None) == "low"

    def test_unknown_tool_is_low(self):
        assert classify_risk("some_random_tool") == "low"


class TestRequiresApproval:
    def test_high_risk_requires_approval(self):
        assert requires_approval("shutdown") is True

    def test_low_risk_no_approval(self):
        assert requires_approval("get_battery") is False

    def test_medium_risk_no_approval_in_interactive(self):
        assert requires_approval("send_message", autonomous=False) is False

    def test_medium_risk_requires_approval_in_autonomous(self):
        assert requires_approval("write_file", autonomous=True) is True
