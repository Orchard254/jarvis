"""
Execution Agent — Tool Orchestration + Micro-Planning.

Handles:
  - Receiving high-level INTENT from Jarvis
  - Expanding into concrete tool sequences (deterministic, no LLM)
  - Executing tools through the safety pipeline
  - Verification and retries
  - Reporting consolidated results back to Jarvis

This is the tactical operator (the hands), NOT a second brain.
Expansion rules are pure Python — no LLM calls, no goal drift.
"""

import json
import logging

from brain import ollama_client
from brain.prompt_builder import build_executor_prompt
from settings import EXECUTOR_MODEL

logger = logging.getLogger(__name__)


# ── Expander registry ────────────────────────────────────────────────────────
EXPANDERS: dict[str, callable] = {}


def expander(action: str):
    """Decorator to register an intent expander."""
    def wrapper(fn):
        EXPANDERS[action] = fn
        return fn
    return wrapper


# ── Intent expanders (deterministic, no LLM) ─────────────────────────────────

@expander("open")
def _expand_open(intent: dict) -> list:
    """Open or focus an app.

    Strategy: try to focus the app first.
    - focus_window succeeds  → app was already running, now brought to front. Done.
    - focus_window fails     → app is not running, launch it, wait for it to load,
                               then focus it.

    This prevents opening duplicate sessions when the app is already running
    but a different window (e.g. the terminal) currently has focus. The old
    approach checked only the active window title, so it would always call
    open_app when the terminal had focus, creating a new instance every time.
    """
    target = intent.get("target", "")

    def _launch_if_not_running(prior):
        """Step 1 was focus_window. If it succeeded, the app was already
        running — return a no-op. If it failed, the app isn't running — launch it."""
        if prior[0].get("success"):
            return {"tool": "wait", "params": {"ms": 0}}
        return {"tool": "open_app", "params": {"name": target}}

    def _wait_for_launch(prior):
        """Only block for 3 seconds if we actually launched the app."""
        launched = prior[1].get("tool") == "open_app" if len(prior) > 1 else False
        if launched:
            return {"tool": "wait", "params": {"ms": 3000}}
        return {"tool": "wait", "params": {"ms": 0}}

    def _focus_after_launch(prior):
        """Re-focus after launch. If we didn't launch (app was already running),
        focus_window already ran as step 0 — this becomes a no-op."""
        launched = prior[1].get("tool") == "open_app" if len(prior) > 1 else False
        if launched:
            return {"tool": "focus_window", "params": {"title": target, "process": target}}
        return {"tool": "wait", "params": {"ms": 0}}

    return [
        {"tool": "focus_window", "params": {"title": target, "process": target}},
        _launch_if_not_running,
        _wait_for_launch,
        _focus_after_launch,
        {"tool": "get_active_window", "params": {}},
    ]


@expander("close")
def _expand_close(intent: dict) -> list:
    """Close an app, defaulting to active window if no target given."""
    target = intent.get("target", "")
    steps = []
    if not target:
        steps.append({"tool": "get_active_window", "params": {}})

        def _close_active(prior):
            result = prior[0].get("result", {})
            t = result.get("title", "")
            return {"tool": "close_app", "params": {"name": t}}
        steps.append(_close_active)
    else:
        steps.append({"tool": "close_app", "params": {"name": target}})
    return steps


@expander("search")
def _expand_search(intent: dict) -> list:
    """Search the web. Opens browser, ensures it has focus, then navigates."""
    query = intent.get("query", intent.get("target", ""))
    engine = intent.get("engine", "google")
    urls = {"google": "https://google.com/search?q=", "youtube": "https://youtube.com/results?search_query="}
    prefix = urls.get(engine, urls["google"])
    return [
        {"tool": "open_app", "params": {"name": "browser"}},
        # BUG WAS: typed immediately after open_app with only an 800ms wait and
        # no focus_window call. The browser may not have focus, or focus may be
        # on the page body rather than the address bar, causing the URL to land
        # in a search box or text field on the current page.
        # FIX: explicitly focus the browser window, then press Ctrl+L to move
        # focus to the address bar before typing.
        {"tool": "wait", "params": {"ms": 1000}},
        {"tool": "focus_window", "params": {"title": "browser", "process": "browser"}},
        {"tool": "wait", "params": {"ms": 300}},
        {"tool": "press_keys", "params": {"keys": "ctrl+l"}},
        {"tool": "wait", "params": {"ms": 200}},
        {"tool": "type_text", "params": {"text": f"{prefix}{query}"}},
        {"tool": "press_keys", "params": {"keys": "enter"}},
    ]


@expander("click")
def _expand_click(intent: dict) -> list:
    """Click on UI element. Can specify text target or coordinates."""
    if "target" in intent:
        return [
            {"tool": "detect_ui_elements", "params": {"text": intent["target"]}},
            _resolve_click,
            {"tool": "get_active_window", "params": {}},
        ]
    x = intent.get("x", 0)
    y = intent.get("y", 0)
    btn = intent.get("button", "left")
    return [
        {"tool": "get_active_window", "params": {}},
        {"tool": "click", "params": {"button": btn, "x": x, "y": y}},
        {"tool": "get_active_window", "params": {}},
    ]


def _resolve_click(prior):
    """Resolve click coordinates from detect_ui_elements result."""
    result = prior[-1] if prior else {}
    data = result.get("result", {}).get("data", {})
    elements = data if isinstance(data, list) else data.get("elements", [data])
    if elements and isinstance(elements, list) and len(elements) > 0:
        el = elements[0]
        cx = el.get("x", 0) + el.get("w", 0) // 2
        cy = el.get("y", 0) + el.get("h", 0) // 2
        return {"tool": "click", "params": {"button": "left", "x": cx, "y": cy}}
    # No elements found — do NOT fall back to clicking (0, 0) which is the
    # top-left corner of the screen and would trigger unintended actions.
    logger.warning("_resolve_click: no UI elements detected, skipping click")
    return {"tool": "wait", "params": {"ms": 0}}


@expander("type")
def _expand_type(intent: dict) -> list:
    """Type text into a specific window (if given) or the active input.

    Accepts an optional 'window' field on the intent so the brain can
    explicitly name which app should receive the text (e.g. when the user
    says 'open Notepad and type hello', the brain should emit:
        INTENT {"action": "type", "text": "hello", "window": "notepad"}
    Without 'window', we verify focus is not on the terminal and type
    into whatever window currently has focus.
    """
    text = intent.get("text", "")
    # Accept either 'window' (preferred) or 'target' as the app to type into
    window = intent.get("window", "") or intent.get("target", "")

    steps = [{"tool": "get_active_window", "params": {}}]

    if window:
        # Explicit target — always focus the named window before typing
        def _focus_target_window(prior):
            return {"tool": "focus_window", "params": {"title": window, "process": window}}
        steps.append(_focus_target_window)
        steps.append({"tool": "wait", "params": {"ms": 300}})
    else:
        # No explicit target — guard against terminal focus stealing
        def _guard_terminal_focus(prior):
            # BUG WAS: looped all prior results, using only the last one.
            # FIX: use prior[0] which is always the get_active_window result.
            active_title = str(prior[0].get("result", {}).get("title", "")).lower()
            term_indicators = ("powershell", "cmd", "command prompt", "terminal", "ps ")
            if any(t in active_title for t in term_indicators):
                # BUG WAS: called focus_window with title="" process="" (undefined behavior).
                # FIX: log a warning and skip — we cannot safely guess the target window.
                logger.warning(
                    "_expand_type: terminal has focus and no target window was specified. "
                    "Include 'window' in the type intent to type into a specific app."
                )
            return {"tool": "wait", "params": {"ms": 100}}
        steps.append(_guard_terminal_focus)
        steps.append({"tool": "wait", "params": {"ms": 300}})

    steps.append({"tool": "type_text", "params": {"text": text}})
    return steps


@expander("scroll")
def _expand_scroll(intent: dict) -> list:
    """Scroll the active window."""
    direction = intent.get("direction", "down")
    amount = int(intent.get("amount", 3))
    clicks = amount if direction == "down" else -amount
    return [
        {"tool": "get_active_window", "params": {}},
        {"tool": "scroll", "params": {"clicks": clicks}},
    ]


@expander("screenshot")
def _expand_screenshot(intent: dict) -> list:
    """Capture and optionally analyze the screen."""
    return [
        {"tool": "screenshot", "params": {}},
    ]


@expander("read_screen")
def _expand_read_screen(intent: dict) -> list:
    """Read text from screen."""
    return [
        {"tool": "read_screen", "params": {}},
    ]


@expander("wait")
def _expand_wait(intent: dict) -> list:
    """Wait for a condition or time."""
    return [
        {"tool": "wait", "params": intent.get("params", {})},
    ]


@expander("shutdown")
def _expand_shutdown(intent: dict) -> list:
    """Shutdown the system."""
    return [
        {"tool": "shutdown", "params": {}},
    ]


@expander("restart")
def _expand_restart(intent: dict) -> list:
    """Restart the system."""
    return [
        {"tool": "restart", "params": {}},
    ]


@expander("get_info")
def _expand_get_info(intent: dict) -> list:
    """Get system or app information."""
    info_type = intent.get("target", "system").lower()
    tool_map = {
        "battery": ("get_battery", {}),
        "time": ("time_calendar", {"action": "get_time"}),
        "system": ("get_system_stats", {}),
        "apps": ("list_installed_apps", {}),
    }
    tool, params = tool_map.get(info_type, ("get_system_stats", {}))
    return [
        {"tool": tool, "params": params},
    ]


# ── Additional expanders ─────────────────────────────────────────────────────

@expander("press_keys")
def _expand_press_keys(intent: dict) -> list:
    """Press keyboard keys (hotkey or sequence)."""
    keys = intent.get("keys", "")
    return [
        {"tool": "get_active_window", "params": {}},
        {"tool": "press_keys", "params": {"keys": keys}},
    ]


@expander("move_mouse")
def _expand_move_mouse(intent: dict) -> list:
    """Move mouse to coordinates."""
    x = intent.get("x", 0)
    y = intent.get("y", 0)
    return [
        {"tool": "get_active_window", "params": {}},
        {"tool": "move_mouse", "params": {"x": x, "y": y}},
    ]


@expander("list_apps")
def _expand_list_apps(intent: dict) -> list:
    """List installed or running apps."""
    scope = intent.get("target", "installed")
    if scope == "running":
        return [{"tool": "list_running_apps", "params": {}}]
    return [{"tool": "list_installed_apps", "params": {}}]


@expander("open_url")
def _expand_open_url(intent: dict) -> list:
    """Open a URL in the browser."""
    url = intent.get("url", "")
    return [
        {"tool": "open_app", "params": {"name": "browser"}},
        {"tool": "open_url", "params": {"url": url}},
    ]


@expander("manage_window")
def _expand_manage_window(intent: dict) -> list:
    """Manage window state: minimize, maximize, focus, close."""
    action = intent.get("action", "focus")
    target = intent.get("target", "")
    tool_map = {
        "minimize": ("minimize_window", {"title": target}),
        "maximize": ("maximize_window", {"title": target}),
        "focus": ("focus_window", {"title": target}),
        "close": ("close_app", {"name": target}),
    }
    tool, params = tool_map.get(action, ("focus_window", {"title": target}))
    return [
        {"tool": "get_active_window", "params": {}},
        {"tool": tool, "params": params},
    ]


# ── Execution Agent ──────────────────────────────────────────────────────────

class ExecutionAgent:
    """Tactical agent — expands intents into tool sequences and executes them.

    Known actions are handled by deterministic expanders (no LLM).
    Unknown actions fall back to the executor LLM for tool-call planning.
    """

    def __init__(self, execute_fn, verify_fn):
        self._execute = execute_fn
        self._verify = verify_fn
        self._fail_counts: dict[str, int] = {}
        self._executor_prompt: str | None = None

    def _get_executor_prompt(self) -> str:
        """Lazily build and cache the executor system prompt."""
        if self._executor_prompt is None:
            self._executor_prompt = build_executor_prompt()
        return self._executor_prompt

    def execute_intent(self, intent: dict) -> str:
        """
        Expand an intent into tool calls and execute them.

        Known actions use deterministic expanders (fast, no LLM).
        Unknown actions fall back to the executor LLM for planning.

        Returns a consolidated result string that gets fed back to Jarvis.
        """
        # Reset tool failure streaks at the start of each intent execution.
        # This prevents a transient failure (e.g. focus_window before app is
        # fully launched) from poisoning subsequent intent rounds within the
        # same user command.
        try:
            orch = self._execute.__self__
            if hasattr(orch, '_tool_failure_streak'):
                orch._tool_failure_streak.clear()
        except Exception:
            pass
        action = intent.get("action", "")
        expander_fn = EXPANDERS.get(action)

        if not expander_fn:
            return self._llm_fallback(intent)

        try:
            steps = expander_fn(intent)
        except Exception as e:
            logger.error(f"Expander '{action}' failed: {e}")
            return f"Failed to plan action '{action}': {e}"

        if not steps:
            return f"Action '{action}' produced no steps."

        results = []
        for step in steps:
            result = self._run_step(step, results)
            results.append(result)
            if not result.get("success") and intent.get("abort_on_fail", True):
                logger.info(f"Aborting '{action}' after failed step: {result.get('tool')}")
                break

        return self._format_response(action, results)

    def _run_step(self, step, prior_results: list) -> dict:
        """Execute one step — either a dict or a callable."""
        if callable(step):
            try:
                resolved = step(prior_results)
            except Exception as e:
                return {"tool": "<callable>", "success": False, "error": str(e), "result": {}}
            if not isinstance(resolved, dict):
                return {"tool": "<callable>", "success": False,
                        "error": f"resolved to {type(resolved).__name__}", "result": {}}
            step = resolved

        tool_name = step.get("tool", "?")
        args = step.get("params", {})

        result = self._execute(tool_name, args)
        verification = self._verify(tool_name, result, "")

        return {
            "tool": tool_name,
            "args": args,
            "success": result.get("success", False),
            "error": result.get("error"),
            "result": result,
            "verification": verification.get("status", ""),
            "message": result.get("message") or result.get("output") or "",
        }

    def _llm_fallback(self, intent: dict) -> str:
        """Use the executor LLM to plan and execute an unknown action.

        Sends the intent to the executor model with the executor prompt,
        then executes any tool calls it returns.
        """
        action = intent.get("action", "")
        logger.info(f"No expander for '{action}' — falling back to executor LLM")

        prompt = self._get_executor_prompt()
        user_msg = (
            f"Execute this intent: {json.dumps(intent)}\n"
            f"Plan the tool calls needed and execute them."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg},
        ]

        try:
            llm_result = ollama_client.chat(
                messages=messages,
                model=EXECUTOR_MODEL,
                temperature=0.1,
                max_retries=2,
            )
        except Exception as e:
            logger.error(f"Executor LLM call failed: {e}")
            return f"Failed to plan action '{action}': LLM unavailable ({e})"

        content = (llm_result.get("content") or "").strip()
        tool_calls = llm_result.get("tool_calls")

        # If the LLM returned tool calls, execute them
        if tool_calls:
            results = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                args = fn.get("arguments", {})
                if not tool_name:
                    continue
                result = self._execute(tool_name, args)
                verification = self._verify(tool_name, result, "")
                results.append({
                    "tool": tool_name,
                    "args": args,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                    "result": result,
                    "verification": verification.get("status", ""),
                    "message": result.get("message") or result.get("output") or "",
                })
                if not result.get("success") and intent.get("abort_on_fail", True):
                    logger.info(f"Aborting '{action}' after failed step: {tool_name}")
                    break
            if results:
                return self._format_response(action, results)

        # No tool calls — return the LLM's text response
        if content:
            return f"Action '{action}': {content}"

        return f"Unknown action: '{action}'. No expander and executor LLM returned no plan."

    def _format_response(self, action: str, results: list) -> str:
        """Build a readable result string for Jarvis."""
        ok = sum(1 for r in results if r.get("success"))
        total = len(results)
        status = "ok" if ok == total else "partial" if ok > 0 else "failed"

        summary = f"Action '{action}': {ok}/{total} steps succeeded."
        details = []
        for r in results:
            icon = "+" if r.get("success") else "-"
            msg = r.get("message") or r.get("error") or "done"
            details.append(f"  {icon} {r.get('tool')}: {msg[:200]}")

        return f"{summary}\n" + "\n".join(details) + f"\nOverall: {status}"
