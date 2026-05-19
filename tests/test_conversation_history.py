"""Conversation history hydration and lean Jarvis LLM settings."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.conversation_history import episodes_to_chat_messages, merge_histories
from memory import episodic, memory_manager


def test_episodes_to_chat_messages_pairs_command_response():
    episodes = [
        {
            "event_type": "command",
            "command_text": "open notepad",
            "tool_result": None,
        },
        {
            "event_type": "response",
            "command_text": "open notepad",
            "tool_result": {"response": "Opened Notepad."},
        },
        {
            "event_type": "command",
            "command_text": "what time is it",
            "tool_result": None,
        },
        {
            "event_type": "response",
            "command_text": "what time is it",
            "tool_result": {"response": "3:00 PM"},
        },
    ]
    msgs = episodes_to_chat_messages(episodes)
    assert len(msgs) == 4
    assert msgs[0] == {"role": "user", "content": "open notepad"}
    assert msgs[1]["content"] == "Opened Notepad."
    assert msgs[2]["role"] == "user"
    assert msgs[3]["content"] == "3:00 PM"


def test_merge_histories_dedupes_session_tail():
    persisted = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    in_memory = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "done"},
    ]
    merged = merge_histories(persisted, in_memory)
    assert len(merged) == 4
    assert merged[-1]["content"] == "done"


def test_memory_manager_conversation_history(monkeypatch):
    import uuid
    import settings

    monkeypatch.setattr(settings, "LOAD_CONVERSATION_HISTORY", True, raising=False)
    episodic.init_db()
    sid = f"test_conv_{uuid.uuid4().hex}"
    mm = memory_manager.MemoryManager(session_id=sid)
    mm.write_episodic("command", command_text="run test", success=True)
    mm.write_episodic(
        "response",
        command_text="run test",
        success=True,
        tool_result={"response": "ok"},
    )
    episodes = episodic.get_session_events(mm.session_id, limit=10)
    assert len(episodes) >= 2
    assert any(e.get("event_type") == "response" for e in episodes)
    hist = episodes_to_chat_messages(episodes)
    assert len(hist) == 2, f"episodes={episodes!r}"
    assert hist[0]["role"] == "user"
    assert hist[1]["role"] == "assistant"
    monkeypatch.setattr(settings, "LOAD_CONVERSATION_HISTORY", True, raising=False)
    assert len(mm.get_conversation_history(limit=5)) == 2


def test_conversation_history_disabled(monkeypatch):
    import settings

    monkeypatch.setattr(settings, "LOAD_CONVERSATION_HISTORY", False, raising=False)
    mm = memory_manager.MemoryManager(session_id="disabled_hist_test")
    assert mm.get_conversation_history() == []


def test_jarvis_omits_tool_schemas_by_default(monkeypatch):
    captured = {}

    def mock_chat_stream(messages, tools=None, **kwargs):
        captured["tools"] = tools
        return {
            "content": "Hello.",
            "tool_calls": None,
            "model": "test",
            "done": True,
        }

    monkeypatch.setattr("brain.ollama_client.chat_stream", mock_chat_stream)
    monkeypatch.setattr("brain.ollama_client.chat", mock_chat_stream)

    from agents.jarvis import run as jarvis_run

    jarvis_run(
        "hi",
        [],
        lambda n, a: {"success": True},
        lambda n, r, e: {"status": "CONFIRMED"},
        attach_tool_schemas=False,
    )
    assert captured.get("tools") == []
