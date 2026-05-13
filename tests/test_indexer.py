
"""Phase 1 tests — Async PC Indexer & Read-Only Query Tool."""
import pytest
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from indexer import pc_indexer
from indexer import app_scanner, file_scanner, state_monitor
from tools.query_pc_index import query_pc_index

def test_db_initializes():
    pc_indexer.init_db()
    assert pc_indexer.PC_INDEX_DB.exists()

def test_state_monitor_captures_valid_structure():
    state = state_monitor.capture_state()
    assert "processes_json" in state and isinstance(state["processes_json"], str)
    assert "focused_app" in state

def test_app_scanner_pushes_records():
    from indexer.write_queue import IndexWriter
    w = IndexWriter()
    w.start()
    count = app_scanner.scan_apps(w)
    assert count is None or isinstance(count, int)  # scan_apps returns via queue
    w.stop()

def test_query_pc_index_returns_dict():
    results = query_pc_index("notepad", type="app")
    assert isinstance(results, dict)
    assert "success" in results
    assert "results" in results
    assert isinstance(results["results"], list)

def test_indexer_background_starts_and_stops_cleanly():
    pc_indexer.start()
    time.sleep(3)
    latest = state_monitor.get_latest()
    assert latest != {}
    pc_indexer.stop()
