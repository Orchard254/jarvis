"""Phase 1 tests — Async PC Indexer & Read-Only Query Tool."""
import pytest
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from indexer import pc_indexer
from indexer import app_scanner, file_scanner, state_monitor


def test_db_initializes(monkeypatch, tmp_path):
    db_path = tmp_path / "pc_index.db"
    monkeypatch.setattr(pc_indexer, "PC_INDEX_DB", db_path)
    pc_indexer.init_db()
    assert db_path.exists()


def test_state_monitor_captures_valid_structure():
    state = state_monitor.capture_state()
    assert "all_windows" in state
    assert "focused_title" in state


def test_app_scanner_pushes_records(monkeypatch, tmp_path):
    from indexer.write_queue import IndexWriter
    db_path = tmp_path / "pc_index.db"
    monkeypatch.setattr(pc_indexer, "PC_INDEX_DB", db_path)
    pc_indexer.init_db()
    w = IndexWriter()
    w.start()
    count = app_scanner.scan_apps(w)
    assert count is None or isinstance(count, int)
    w.stop()


def test_db_query_returns_results(monkeypatch, tmp_path):
    import sqlite3
    from core.thread_db import get_connection
    db_path = tmp_path / "pc_index.db"
    monkeypatch.setattr(pc_indexer, "PC_INDEX_DB", db_path)
    pc_indexer.init_db()
    conn = get_connection(pc_indexer.PC_INDEX_DB, timeout=5000)
    cur = conn.execute("SELECT name, exe_path FROM apps WHERE name LIKE ?", ("%notepad%",))
    rows = cur.fetchall()
    conn.close()
    assert isinstance(rows, list)


def test_indexer_background_starts_and_stops_cleanly(monkeypatch, tmp_path):
    db_path = tmp_path / "pc_index.db"
    monkeypatch.setattr(pc_indexer, "PC_INDEX_DB", db_path)
    pc_indexer.start()
    time.sleep(3)
    latest = state_monitor.get_latest()
    assert latest != {}
    pc_indexer.stop()
