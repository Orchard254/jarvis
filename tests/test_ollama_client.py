"""Tests for brain/ollama_client.py — chat() function with mocked requests."""

import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from brain.ollama_client import chat, OllamaError


def _mock_response(data, status=200):
    class MockResp:
        def raise_for_status(self):
            if status >= 400:
                raise Exception(f"HTTP {status}")
        def json(self):
            return data
    return MockResp()


def test_chat_returns_content(monkeypatch):
    def mock_post(*a, **kw):
        return _mock_response({
            "message": {"content": "Hello from LLM"},
            "model": "test-model",
        })

    monkeypatch.setattr("requests.post", mock_post)
    result = chat(messages=[{"role": "user", "content": "hi"}])
    assert result["content"] == "Hello from LLM"
    assert result["model"] == "test-model"
    assert result["done"] is True


def test_chat_returns_tool_calls(monkeypatch):
    def mock_post(*a, **kw):
        return _mock_response({
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "get_battery", "arguments": {}},
                }],
            },
            "model": "test-model",
        })

    monkeypatch.setattr("requests.post", mock_post)
    result = chat(messages=[{"role": "user", "content": "check battery"}], tools=[{"function": {"name": "get_battery"}}])
    assert result["content"] == ""
    assert result["tool_calls"] is not None
    assert result["tool_calls"][0]["function"]["name"] == "get_battery"


def test_chat_handles_openai_format(monkeypatch):
    def mock_post(*a, **kw):
        return _mock_response({
            "choices": [{
                "message": {"content": "Hello", "tool_calls": []},
            }],
            "model": "gpt-test",
        })

    monkeypatch.setattr("requests.post", mock_post)
    result = chat(messages=[{"role": "user", "content": "hi"}])
    assert result["content"] == "Hello"


def test_chat_retries_on_failure_then_succeeds(monkeypatch):
    attempts = [0]

    def mock_post(*a, **kw):
        attempts[0] += 1
        if attempts[0] < 3:
            raise Exception("Server error")
        return _mock_response({
            "message": {"content": "Got it after retry"},
            "model": "test",
        })

    monkeypatch.setattr("requests.post", mock_post)
    result = chat(messages=[{"role": "user", "content": "hi"}], max_retries=3)
    assert result["content"] == "Got it after retry"
    assert attempts[0] == 3


def test_chat_raises_after_max_retries(monkeypatch):
    def mock_post(*a, **kw):
        raise Exception("Always fails")

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("brain.ollama_client.FALLBACK_TO_LOCAL", False)
    with pytest.raises(OllamaError):
        chat(messages=[{"role": "user", "content": "hi"}], max_retries=1)


def test_chat_parses_string_arguments(monkeypatch):
    def mock_post(*a, **kw):
        return _mock_response({
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "open_app", "arguments": '{"app_name": "notepad"}'},
                }],
            },
            "model": "test",
        })

    monkeypatch.setattr("requests.post", mock_post)
    result = chat(messages=[{"role": "user", "content": "open notepad"}], tools=[{"function": {"name": "open_app"}}])
    assert result["tool_calls"][0]["function"]["arguments"] == {"app_name": "notepad"}
