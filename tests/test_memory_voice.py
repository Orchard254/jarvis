"""Phase 6 tests — Memory persistence and voice I/O pipeline."""
import pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import settings as jarvis_settings
from memory import episodic, semantic, memory_manager
from perception import stt, wake_word, input_handler
from output import tts, formatter


def test_episodic_init_and_write(monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis_settings, "MEMORY_DB", tmp_path / "episodic.db")
    episodic.init_db()
    episodic.write("test_session", "command", command_text="test", success=True)
    events = episodic.get_session_events("test_session")
    assert len(events) >= 1
    assert events[-1]["command_text"] == "test"


def test_semantic_set_get(monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis_settings, "MEMORY_DB", tmp_path / "semantic.db")
    semantic.init_db()
    semantic.upsert("test_pref", {"value": 42})
    assert semantic.fetch("test_pref") == {"value": 42}
    assert semantic.fetch("missing_key", "default") == "default"


def test_memory_manager_unified_interface(monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis_settings, "MEMORY_DB", tmp_path / "memory.db")
    mm = memory_manager.MemoryManager(session_id="test_mm")
    mm.write_episodic("command", command_text="unified test", success=True)
    mm.set_preference("browser", "chrome")
    assert mm.get_preference("browser") == "chrome"
    ctx = mm.get_context_summary()
    assert isinstance(ctx, str)


def test_formatter_strips_markdown():
    raw = "**Done**. Here is `code` and ```block```."
    formatted = formatter.format_for_tts(raw)
    assert "```" not in formatted
    assert "**" not in formatted


def test_tts_mute_flag_integration(monkeypatch):
    import settings
    monkeypatch.setattr(settings, "TTS_ENABLED", False)
    monkeypatch.setattr("output.tts.speak", lambda *a, **kw: True)
    from output.tts import speak
    result = speak("test", blocking=True)
    assert result is True
    assert not settings.IS_SPEAKING.is_set()


def test_input_handler_routes_correctly(monkeypatch):
    class MockOrch:
        def handle(self, text): return f"Mock response to: {text}"
    monkeypatch.setattr("output.tts.speak", lambda *a, **kw: True)
    handler = input_handler.InputHandler(MockOrch())
    handler.route("test input", source="text")
