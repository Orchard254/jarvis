"""Tests for safety/confidence_gate.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from safety.confidence_gate import check


class TestConfidenceGate:
    def test_high_confidence_passes(self):
        ok, reason = check({"confidence": 0.95, "tool_name": "get_battery"})
        assert ok is True
        assert reason == ""

    def test_low_confidence_blocked(self):
        ok, reason = check({"confidence": 0.5, "tool_name": "get_battery"})
        assert ok is False
        assert "below threshold" in reason

    def test_approved_bypasses_gate(self):
        ok, reason = check({"confidence": 0.0, "approved": True})
        assert ok is True

    def test_uncertainty_phrases_reduce_confidence(self):
        ok, reason = check({
            "confidence": 0.85,
            "llm_response": "I'm not sure, this could break things, risky operation",
            "tool_name": "get_battery",
        })
        assert ok is False

    def test_mild_uncertainty_smaller_reduction(self):
        ok, reason = check({
            "confidence": 1.0,
            "llm_response": "I think it might work",
            "tool_name": "get_battery",
        })
        assert ok is True

    def test_high_risk_increases_threshold(self):
        ok, reason = check({
            "confidence": 0.78,
            "tool_name": "shutdown",
            "_server_risk": "high",
        })
        assert ok is False
        assert "0.80" in reason or "below threshold" in reason

    def test_destructive_caps_confidence(self):
        ok, reason = check({
            "confidence": 1.0,
            "destructive": True,
            "tool_name": "write_file",
        })
        assert ok is True

    def test_no_tool_name_does_not_crash(self):
        ok, reason = check({"confidence": 0.99})
        assert ok is True

    def test_empty_plan_defaults(self):
        ok, reason = check({})
        assert ok is True

    def test_uncertainty_with_high_risk_blocks(self):
        ok, reason = check({
            "confidence": 0.85,
            "llm_response": "I'm not sure, I don't know if this is safe",
            "_server_risk": "high",
        })
        assert ok is False
