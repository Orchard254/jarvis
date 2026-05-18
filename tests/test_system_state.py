"""Tests for core/system_state.py."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.system_state import SystemState


class TestSystemState:
    def test_initial_state_has_keys(self):
        state = SystemState()
        snap = state.snapshot()
        assert "active_window" in snap
        assert "cpu_percent" in snap
        assert "mouse_position" in snap

    def test_get_returns_default_for_missing(self):
        state = SystemState()
        assert state.get("nonexistent", "fallback") == "fallback"

    def test_get_returns_value(self):
        state = SystemState()
        assert isinstance(state.get("cpu_percent"), (int, float))

    def test_update_preserves_last_action(self):
        state = SystemState()
        state.update("get_battery", {"arg": 1}, {"success": True, "timestamp": "now"})
        assert state.get("last_action") == "get_battery"

    def test_update_extracts_active_window_from_data(self):
        state = SystemState()
        state.update("focus_window", {"window": "Notepad"},
                     {"success": True, "data": {"active_window": "Notepad"}, "timestamp": "now"})
        assert state.get("active_window") == "Notepad"

    def test_snapshot_returns_copy(self):
        state = SystemState()
        snap1 = state.snapshot()
        snap2 = state.snapshot()
        snap1["cpu_percent"] = 999
        assert snap2["cpu_percent"] != 999

    def test_update_with_title_extracts(self):
        state = SystemState()
        state.update("open_app", {"app_name": "Calc"},
                     {"success": True, "data": {"title": "Calculator"}, "timestamp": "now"})
        assert state.get("active_window") == "Calculator"
