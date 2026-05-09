"""
Result reporter — formats tool execution results into human-readable responses.
Called by the orchestrator after the tool loop completes.
"""

import logging

logger = logging.getLogger(__name__)


def report(intent: dict, results: list[dict], verification: dict) -> str:
    """
    Format tool execution results into a human-readable response.

    Args:
        intent:       Intent dict (has 'goal' or 'raw_input' key)
        results:      List of {"tool", "args", "result"} dicts from tool_loop
        verification: {"status": "CONFIRMED"/"FAILED"/"INCONCLUSIVE", "summary": str}

    Returns:
        Formatted string response for the user. Empty string if nothing to add.
    """
    if not results:
        return ""

    ui_tools_ok = any(
        e.get("tool") in ("control_window", "control_input", "execute_code")
        and (e.get("result") or {}).get("success", True)
        for e in results
    )

    v_status = verification.get("status", "INCONCLUSIVE")
    v_summary = verification.get("summary", "")

    def _rows(suppress_rs: bool, success_only: bool = False):
        return [
            s
            for s in (
                _summarize_tool_result(
                    e,
                    suppress_read_pc_state=suppress_rs,
                    success_only=success_only,
                )
                for e in results
            )
            if s
        ]

    summaries = _rows(False)

    if v_status == "CONFIRMED":
        # When the overall outcome succeeded, only surface results from tool
        # calls that themselves succeeded.  Failed intermediate attempts (e.g.
        # a control_input that crashed, a code snippet with a syntax error that
        # the LLM self-corrected on the next iteration) are internal recovery
        # steps — they are not meaningful to the user and should not appear
        # in the final response.
        success_summaries = _rows(ui_tools_ok, success_only=True)
        body = " ".join(success_summaries) if success_summaries else (v_summary or "Done.")
        return f"✅ {body}".strip()
    elif v_status == "FAILED":
        # On failure, show the last error to help the user understand what went wrong.
        error_detail = v_summary or (summaries[-1] if summaries else "unknown error")
        return f"❌ {error_detail[:200]}"
    else:
        # INCONCLUSIVE — return tool summaries if we have them
        alt = _rows(ui_tools_ok)
        return " ".join(alt if alt else summaries) if (alt or summaries) else ""


def _summarize_tool_result(
    entry: dict, suppress_read_pc_state: bool = False, success_only: bool = False
) -> str:
    """Concise human-readable summary for one tool call entry."""
    tool = entry.get("tool", "unknown")
    result = entry.get("result") or {}

    if suppress_read_pc_state and tool == "read_pc_state":
        return ""

    # When success_only=True (used for CONFIRMED responses), skip failed
    # intermediate tool calls entirely — they are recovery internals.
    if success_only and result.get("success") is False:
        return ""

    if result.get("success") is False:
        err = (result.get("error") or "failed")[:80]
        return f"[{tool}: {err}]"

    if tool == "execute_code":
        stdout = (result.get("stdout") or "").strip()
        return stdout[:300] + ("…" if len(stdout) > 300 else "") if stdout else ""

    if tool == "search_web":
        items = result.get("results") or []
        if not items:
            return "Web search returned no results."
        lines = [f"Found {len(items)} result(s):"]
        for r in items[:3]:
            lines.append(f"• {r.get('title', '')} — {r.get('url', '')}")
            if r.get("snippet"):
                lines.append(f"  {r['snippet'][:100]}")
        return "\n".join(lines)

    if tool == "fetch_url":
        title = result.get("title", "")
        text = (result.get("text") or "")[:400]
        return f"📄 {title}\n{text}" if title else text

    if tool == "read_file":
        content = (result.get("content") or "")[:400]
        return f"📄 {content}" if content else ""

    if tool == "write_file":
        path = result.get("path", "")
        return f"📝 Written to {path}" if path else "File written."

    if tool == "file_ops":
        action = result.get("action", "")
        if action == "list":
            return f"📁 {len(result.get('items', []))} items"
        if action in ("delete", "move", "copy"):
            return f"✓ {action.capitalize()}d successfully"
        if action == "search_content":
            matches = result.get("matches") or []
            return f"🔍 {len(matches)} match(es) found"
        return ""

    if tool == "read_pc_state":
        focused = result.get("focused_app", "")
        proc = result.get("focused_process", "")
        # Prefer new fields, fall back to counting windows list for backward compat
        app_count = result.get("app_count") or len(result.get("processes") or [])
        window_count = result.get("window_count") or len(result.get("windows") or [])
        focus_str = f"{focused} ({proc})" if proc and proc != "unknown" else focused
        return f"Focus: {focus_str} | {app_count} app(s), {window_count} window(s)" if focused else ""

    if tool == "query_pc_index":
        items = result if isinstance(result, list) else (result.get("results") or [])
        names = [i.get("name") or i.get("filename") or "" for i in items[:3]]
        names = [n for n in names if n]
        return f"Found: {', '.join(names)}" if names else "Nothing found."

    if tool == "process_manager":
        action = result.get("action", "")
        if action == "list":
            return f"🔄 {len(result.get('processes', []))} processes"
        if action in ("kill", "kill_by_name"):
            return f"⛔ Killed {len(result.get('killed', []))} process(es)"
        return ""

    if tool == "clipboard":
        action = result.get("action", "read")
        if action == "read":
            text = result.get("text", "")
            return f"📋 {text[:80]}" if text else "Clipboard empty."
        return "📋 Clipboard updated."

    if tool == "system_settings":
        s = result.get("setting", "")
        v = result.get("value")
        return f"⚙️ {s}: {v}" if v is not None else f"⚙️ {s} updated"

    if tool == "browser":
        action = result.get("action", "")
        url = result.get("url", "")
        title = result.get("title", "")
        if action == "read_page":
            return f"🌐 {title or url}"
        if action == "navigate":
            return f"🌐 → {url}"
        return ""

    if tool == "vision_query":
        answer = (result.get("answer") or "").strip()
        return f"👁 {answer[:400]}" if answer else ""

    if tool in (
        "capture_screen",
        "notify_user",
        "control_input",
        "control_window",
        "find_on_screen",
    ):
        return ""  # silent success for these tools

    return ""
