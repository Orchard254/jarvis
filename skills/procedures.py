"""
Procedural Brain — expert skill procedures.

Each procedure maps an intent to a safe, deterministic execution sequence.
Procedures are tested Python, not LLM output.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class Procedure:
    name: str = ""
    description: str = ""
    required_params: list[str] = []

    def preconditions(self, params: dict) -> str | None:
        return None

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        raise NotImplementedError

    def verify(self, result: dict) -> bool:
        return result.get("success", False)


class OpenApp(Procedure):
    name = "open_app"
    description = "Launch an application by name"
    required_params = ["name"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("open_app", {"name": params["name"]})


class CloseWindow(Procedure):
    name = "close_window"
    description = "Close an application window by name"
    required_params = ["target"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        target = params["target"]
        results = []
        # Primary: close_app (taskkill) — 100% reliable on Windows.
        # focus_window + press_keys(alt+f4) rarely works across UIPI boundaries.
        r = tool_fn("close_app", {"name": target})
        results.append(r)
        if not r.get("success"):
            # Fallback: try graceful close via alt+f4
            r = tool_fn("focus_window", {"title": target})
            results.append(r)
            if r.get("success"):
                r = tool_fn("press_keys", {"keys": "alt+f4"})
                results.append(r)
        all_ok = any(r.get("success") for r in results)
        return {"success": all_ok, "steps": results}


class ClearText(Procedure):
    name = "clear_text"
    description = "Select all text in a window and delete it"
    required_params = ["target"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        target = params["target"]
        results = []
        r = tool_fn("focus_window", {"title": target})
        results.append(r)
        if r.get("success"):
            r = tool_fn("press_keys", {"keys": "ctrl+a"})
            results.append(r)
            r = tool_fn("press_keys", {"keys": "backspace"})
            results.append(r)
        all_ok = all(r.get("success") for r in results)
        return {"success": all_ok, "steps": results}


class ClearAndCloseWindow(Procedure):
    name = "clear_and_close_window"
    description = "Clear all text in a window and close it"
    required_params = ["target"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        target = params["target"]
        results = []
        r = tool_fn("focus_window", {"title": target})
        results.append(r)
        if r.get("success"):
            r = tool_fn("press_keys", {"keys": "ctrl+a"})
            results.append(r)
            r = tool_fn("press_keys", {"keys": "backspace"})
            results.append(r)
            r = tool_fn("press_keys", {"keys": "alt+f4"})
            results.append(r)
        all_ok = all(r.get("success") for r in results)
        return {"success": all_ok, "steps": results}


class TypeTextInWindow(Procedure):
    name = "type_text"
    description = "Focus a window and type text into it"
    required_params = ["target", "text"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        import time
        target = params.get("target", "")
        text = params.get("text", "")
        results = []
        if target:
            r = tool_fn("focus_window", {"title": target})
            results.append(r)
            time.sleep(0.3)
        else:
            r = tool_fn("get_active_window", {})
            results.append(r)
            if r.get("success"):
                active = (r.get("data") or r).get("title", "")
                if active:
                    time.sleep(0.1)
                    r = tool_fn("focus_window", {"title": active})
                    results.append(r)
                    time.sleep(0.3)
        r = tool_fn("type_text", {"text": text})
        results.append(r)
        all_ok = all(r.get("success") for r in results)
        return {"success": all_ok, "steps": results}


class FocusWindow(Procedure):
    name = "focus_window"
    description = "Bring a window to the foreground"
    required_params = ["target"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("focus_window", {"title": params["target"]})


class ListRunningApps(Procedure):
    name = "list_running_apps"
    description = "List all running applications"
    required_params = []

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("list_running_apps", {})


class GetActiveWindow(Procedure):
    name = "get_active_window"
    description = "Get the title of the currently active window"
    required_params = []

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("get_active_window", {})


class QuerySystem(Procedure):
    name = "query_system"
    description = "Query system information"
    required_params = ["what"]

    _MAPPING = {
        "battery": "get_battery",
        "time": ("time_calendar", {"action": "get_time"}),
        "date": ("time_calendar", {"action": "get_time"}),
        "stats": "get_system_stats",
        "active_window": "get_active_window",
        "running_apps": "list_running_apps",
        "installed_apps": "list_installed_apps",
    }

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        what = params.get("what", "").lower()
        mapping = self._MAPPING.get(what)
        if mapping is None:
            return {"success": False, "error": f"Unknown query: {what}"}
        if isinstance(mapping, tuple):
            tool_name, fixed_args = mapping
            return tool_fn(tool_name, fixed_args)
        return tool_fn(mapping, {})


# Registry
_PROCEDURES: dict[str, Procedure] = {}


def register(proc: Procedure):
    _PROCEDURES[proc.name] = proc


def get(name: str) -> Procedure | None:
    return _PROCEDURES.get(name)


def match(intent_text: str) -> tuple[Procedure | None, float]:
    """Find the best-matching procedure for an intent string."""
    text = intent_text.lower().strip().replace("_", " ")
    best_proc = None
    best_score = 0.0

    for name, proc in _PROCEDURES.items():
        score = 0.0
        label = name.replace("_", " ")
        if text == label:
            score = 1.0
        elif text.startswith(label) or label.startswith(text):
            score = 0.9
        else:
            words = set(text.split())
            label_words = set(label.split())
            common = words & label_words
            if common:
                score = len(common) / max(len(words), len(label_words))
        if score > best_score:
            best_score = score
            best_proc = proc

    if best_score >= 0.3:
        return best_proc, best_score
    return None, 0.0


def decompose(intent_text: str, params: dict) -> list[dict] | None:
    """Decompose a compound intent into sub-intents."""
    text = intent_text.lower()
    target = params.get("target") or params.get("name", "")

    # Don't decompose known atomic procedure names — they match directly
    for name in _PROCEDURES:
        if text in (name, name.replace("_", " ")):
            return None

    # Handle delegate: route to delegate_to_subagent tool
    if text == "delegate":
        agent = params.get("agent", "")
        goal = params.get("goal", "")
        context = params.get("context", {})
        timeout = params.get("timeout", 120)
        sub_params = {"agent": agent, "goal": goal, "context": context, "timeout": timeout}
        return [{"action": "delegate_to_subagent", "params": sub_params}]

    # Handle manage_app: params["action"] tells us what to do
    if text in ("manage_app", "manage app"):
        sub_action = params.get("action", "").lower()
        if sub_action == "open":
            return [{"action": "open_app", "params": {"name": target}}]
        if sub_action == "close":
            return [{"action": "close_window", "params": {"target": target}}]
        if sub_action == "focus":
            return [{"action": "focus_window", "params": {"target": target}}]
        if sub_action == "clear":
            return [{"action": "clear_text", "params": {"target": target}}]
        if sub_action == "clear_and_close":
            return [
                {"action": "clear_text", "params": {"target": target}},
                {"action": "close_window", "params": {"target": target}},
            ]
        if sub_action == "list" or target in ("running_apps", "running", "processes", "apps"):
            return [{"action": "list_running_apps", "params": {}}]

    if "clear" in text and ("close" in text or "exit" in text or "quit" in text):
        return [
            {"action": "clear_text", "params": {"target": target}},
            {"action": "close_window", "params": {"target": target}},
        ]
    if ("open" in text or "launch" in text) and ("type" in text or "write" in text):
        return [
            {"action": "open_app", "params": {"name": target}},
            {"action": "type_text", "params": {"target": target, "text": params.get("text", "")}},
        ]
    if "focus" in text or "switch" in text or "bring" in text:
        return [{"action": "focus_window", "params": {"target": target}}]

    return None


class DelegateToSubagent(Procedure):
    name = "delegate_to_subagent"
    description = "Route an intent to a specialized sub-agent"
    required_params = ["goal"]

    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("delegate_to_subagent", dict(params))


# ── Simple pass-through procedures for common user-facing tools ──

class CloseApp(Procedure):
    name = "close_app"
    description = "Close a running application by name"
    required_params = ["name"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("close_app", {"name": params["name"]})

class ListInstalledApps(Procedure):
    name = "list_installed_apps"
    description = "Search installed applications by name"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("list_installed_apps", {})

class GetSystemStats(Procedure):
    name = "get_system_stats"
    description = "Get CPU, RAM, disk, and battery status"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("get_system_stats", {})

class GetBattery(Procedure):
    name = "get_battery"
    description = "Get battery percentage and charging status"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("get_battery", {})

class WebSearch(Procedure):
    name = "web_search"
    description = "Search the web and return results"
    required_params = ["query"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("web_search", {"query": params["query"]})

class Screenshot(Procedure):
    name = "screenshot"
    description = "Capture a screenshot of the primary monitor"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("screenshot", {})

class ReadClipboard(Procedure):
    name = "read_clipboard"
    description = "Read text from the clipboard"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("read_clipboard", {})

class WriteClipboard(Procedure):
    name = "write_clipboard"
    description = "Write text to the clipboard"
    required_params = ["text"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("write_clipboard", {"text": params["text"]})

class SetVolume(Procedure):
    name = "set_volume"
    description = "Set system volume level"
    required_params = ["level"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("set_volume", {"level": params["level"]})

class Notify(Procedure):
    name = "notify"
    description = "Send a desktop toast notification"
    required_params = ["title", "message"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("notify", {"title": params["title"], "message": params["message"]})

class Scroll(Procedure):
    name = "scroll"
    description = "Scroll the active window"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("scroll", dict(params))

class Wait(Procedure):
    name = "wait"
    description = "Pause execution for a duration"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("wait", dict(params))

class MinimizeWindow(Procedure):
    name = "minimize_window"
    description = "Minimize a window by title or process name"
    required_params = ["target"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("minimize_window", {"title": params["target"]})

class MaximizeWindow(Procedure):
    name = "maximize_window"
    description = "Maximize or restore a window by title or process name"
    required_params = ["target"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("maximize_window", {"title": params["target"]})

class OpenUrl(Procedure):
    name = "open_url"
    description = "Open a URL in the default web browser"
    required_params = ["url"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("open_url", {"url": params["url"]})

class GetProcessInfo(Procedure):
    name = "get_process_info"
    description = "Get detailed information about running processes"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("get_process_info", {})

class SetBrightness(Procedure):
    name = "set_brightness"
    description = "Set screen brightness level"
    required_params = ["level"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("set_brightness", {"level": params["level"]})

class LockScreen(Procedure):
    name = "lock_screen"
    description = "Lock the workstation immediately"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("lock_screen", {})

class Shutdown(Procedure):
    name = "shutdown"
    description = "Shut down the computer"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("shutdown", {})

class Restart(Procedure):
    name = "restart"
    description = "Restart the computer"
    required_params = []
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("restart", {})

class GetWindowBounds(Procedure):
    name = "get_window_bounds"
    description = "Get position and size of a window by title"
    required_params = ["target"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("get_window_bounds", {"title": params["target"]})

class TimeCalendar(Procedure):
    name = "time_calendar"
    description = "Get current time/date or manage calendar events"
    required_params = ["action"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("time_calendar", dict(params))

class MinimizeAllExcept(Procedure):
    name = "minimize_all_except"
    description = "Minimize all windows except the specified one"
    required_params = ["target"]
    def execute(self, params: dict, tool_fn: Callable) -> dict:
        return tool_fn("minimize_all_except", {"title": params["target"]})


for _p in [
    OpenApp(), CloseWindow(), ClearText(), ClearAndCloseWindow(),
    TypeTextInWindow(), FocusWindow(), GetActiveWindow(), QuerySystem(),
    DelegateToSubagent(), ListRunningApps(),
    CloseApp(), ListInstalledApps(), GetSystemStats(), GetBattery(),
    WebSearch(), Screenshot(), ReadClipboard(), WriteClipboard(),
    SetVolume(), Notify(), Scroll(), Wait(),
    MinimizeWindow(), MaximizeWindow(),
    OpenUrl(), GetProcessInfo(), SetBrightness(),
    LockScreen(), Shutdown(), Restart(),
    GetWindowBounds(), TimeCalendar(), MinimizeAllExcept(),
]:
    register(_p)
