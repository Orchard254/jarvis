"""Phase 3 tests — Orchestrator routing."""
import pytest, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator

def test_orchestrator_instantiates():
    orc = Orchestrator()
    assert orc.running is True
    assert len(orc._history) == 0

def test_orchestrator_handle_returns_string():
    orc = Orchestrator()
    resp = orc.handle("notify me with a test")
    assert isinstance(resp, str) and len(resp) > 0

def test_history_append():
    orc = Orchestrator()
    orc._update_history("hello", "hi there")
    assert len(orc._history) == 2
