# jarvis.py — Main JARVIS loop (orchestration ONLY)
# Replaces assistant.py. Run: python jarvis.py

import json
import os
import re
import time

import config
import control_plane
import pc_control
import stt
import tts
import user_profile
import wake_word
from ambient import AmbientMonitor
from brain import run_agent, stream_reply
from confirmation_gate import build_confirmation_prompt
from intent_classifier import classify_intents
from jarvis_prompt import build_jarvis_prompt
from logger import get_logger
from scoring_gate import apply_execution_gate, score_agent_round
from tools import get_tools

log = get_logger("jarvis")

MAX_HISTORY = config.MAX_HISTORY
MAX_AGENT_ROUNDS = 8
TOOL_RELIABILITY_FILE = os.path.join(os.path.dirname(__file__), "tool_reliability.json")

# Intent priority: lower number = higher priority
INTENT_PRIORITY = {
    "screenshot": 1,
    "time": 2,
    "volume": 3,
    "brightness": 4,
    "open": 5,
    "search": 6,
}


def _load_tool_reliability() -> dict:
    """Load tool reliability data from JSON store."""
    try:
        if os.path.exists(TOOL_RELIABILITY_FILE):
            with open(TOOL_RELIABILITY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log.debug(f"Error loading tool reliability: {e}")
    return {}


def _save_tool_reliability(data: dict) -> None:
    """Save tool reliability data to JSON store."""
    try:
        with open(TOOL_RELIABILITY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Error saving tool reliability: {e}")


def _update_tool_reliability(tool_name: str, success: bool, error_msg: str = "") -> None:
    """Update tool reliability stats after execution. Applies decay to prevent stale data."""
    data = _load_tool_reliability()

    # Apply decay to all entries (prevent stale data)
    # FIX: Use list() to avoid modification during iteration and .get() for missing keys
    for name in list(data.keys()):
        entry = data[name]
        entry["successes"] = max(0, int(entry.get("successes", 0) * 0.9))
        entry["failures"] = max(0, int(entry.get("failures", 0) * 0.9))

    if tool_name not in data:
        data[tool_name] = {
            "successes": 0,
            "failures": 0,
            "last_failure_reason": "",
            "last_success_time": "",
            "retry_successes": 0,
            "retry_attempts": 0,
        }

    entry = data[tool_name]

    if success:
        entry["successes"] += 1
        entry["last_success_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        entry["last_failure_reason"] = ""  # Clear last failure on success
    else:
        entry["failures"] += 1
        if error_msg:
            entry["last_failure_reason"] = error_msg[:100]

    # Cap stored tools to MAX 20 (remove lowest activity)
    if len(data) > 20:
        # Sort by total activity (successes + failures)
        sorted_tools = sorted(data.items(), key=lambda x: x[1]["successes"] + x[1]["failures"])
        # Remove lowest activity tools until at 20
        while len(data) > 20 and sorted_tools:
            oldest_name = sorted_tools[0][0]
            del data[oldest_name]
            sorted_tools = sorted_tools[1:]

    _save_tool_reliability(data)
    log.debug(
        f"[RELIABILITY] {tool_name}: {entry['successes']} successes, {entry['failures']} failures"
    )


def _get_reliability_context() -> str:
    """Get formatted reliability context for LLM."""
    data = _load_tool_reliability()
    if not data:
        return ""

    # Build summary of least reliable tools
    tools_with_failures = [(name, info) for name, info in data.items() if info["failures"] > 0]

    if not tools_with_failures:
        return ""

    # Sort by failure rate
    tools_with_failures.sort(key=lambda x: x[1]["failures"], reverse=True)

    lines = ["Tool Reliability (for reference):"]
    for name, info in tools_with_failures[:5]:  # Top 5 failing tools
        total = info["successes"] + info["failures"]
        if total > 0:
            fail_rate = (info["failures"] / total) * 100
            lines.append(
                f"  - {name}: {fail_rate:.1f}% failure rate ({info['failures']}/{total} attempts)"
            )
            if info["last_failure_reason"]:
                lines.append(f"    Last failure: {info['last_failure_reason'][:50]}")

    return "\n".join(lines)


def _resolve_final_intents(user_text: str) -> list[str]:
    """
    Extract ordered list of intents from user input.
    Uses semantic classification instead of keyword matching.
    """
    try:
        classified = classify_intents(user_text)
        return [i["intent"] for i in classified if i["confidence"] > 0.5]
    except Exception as e:
        log.error(f"[JARVIS] Intent classification failed: {e}")
        return []  # Fallback to empty list, caller should handle this


# FIX 1: intent_map now maps each intent to a LIST of valid tools
# DYNAMIC SCRIPTING: execute_dynamic_script is allowed for ALL intents (primary execution method)
_INTENT_TO_TOOLS: dict[str, list[str]] = {
    "screenshot": ["screen_capture", "execute_dynamic_script"],
    "time": ["get_time", "get_date", "execute_dynamic_script"],
    "open": ["open_app", "open_file", "create_file", "run_powershell", "search_web", "execute_dynamic_script"],
    "close": ["close_app", "run_powershell", "execute_dynamic_script"],
    "volume": ["set_volume", "volume_up", "volume_down", "mute_volume", "get_volume", "execute_dynamic_script"],
    "brightness": ["set_brightness", "execute_dynamic_script"],
    "search": ["search_web", "run_powershell", "execute_dynamic_script"],
    "shutdown": ["shutdown_pc", "execute_dynamic_script"],
    "lock": ["lock_pc", "execute_dynamic_script"],
    "file": ["read_file", "create_file", "open_file", "execute_dynamic_script"],
    "organize": ["execute_dynamic_script"],
    "analyze": ["execute_dynamic_script"],
    "process": ["execute_dynamic_script"],
}


def _aligns_with_intent(tool_call: dict, intent: str) -> bool:
    """
    Check whether a tool_call is consistent with a classified intent.

    FIX 1: _INTENT_TO_TOOLS now uses lists so volume_up/mute_volume/get_volume
           are all accepted when intent == "volume".
    FIX 2: Safe read-only tools always pass through regardless of intent.
    """
    if not intent:
        return False

    fn = tool_call.get("function", {})
    name = fn.get("name", "").lower()

    if name in _SAFE_PASSTHROUGH_TOOLS:
        log.info(f"[JARVIS][FILTER] Passthrough (safe tool): {name}")
        return True

    allowed = _INTENT_TO_TOOLS.get(intent, [])
    if name in allowed:
        log.info(f"[JARVIS][DEBUG] Matched: intent={intent}, name={name}")
        return True

    log.info(f"[JARVIS][DEBUG] No match: intent={intent}, name={name}")
    return False


# Read-only tools that always pass through without blocking
# BUG 2: Added create_file, calculate, add_note, read_notes, etc. for multi-step chains
# DYNAMIC SCRIPTING: execute_dynamic_script is NOT in passthrough (requires intent matching + confirmation)
_SAFE_PASSTHROUGH_TOOLS = frozenset(
    [
        "battery_status",
        "system_health",
        "system_info",
        "get_top_processes",
        "get_uptime",
        "get_wifi",
        "get_ip",
        "get_time",
        "get_date",
        "get_volume",
        "list_running_apps",
        "ping",
        "paste_from_clipboard",
        # BUG 2 additions:
        "create_file",  # needed for write-then-open chains
        "calculate",  # read-only math, no side effects
        "run_powershell_capture",  # safety-gated by control_plane
        "run_terminal_capture",  # safety-gated by control_plane
        "add_note",  # write-only, safe
        "read_notes",  # read-only, safe
        "copy_to_clipboard",  # safe
        "set_timer",  # safe
        "get_uptime",  # already listed but explicit
    ]
)

# Correction patterns for detecting user corrections
_CORRECTION_PATTERNS = (
    "actually",
    "wait no",
    "make it",
    "change it to",
    "change that to",
    "no wait",
    "scratch that",
    "instead",
    "no make it",
    "correction",
    "cancel that",
)

# Value patterns for detecting parameter adjustments
_VALUE_PATTERNS = (
    "volume",
    "brightness",
    "level",
    "percent",
    "%",
    "louder",
    "quieter",
    "higher",
    "lower",
    "up",
    "down",
    "bigger",
    "smaller",
    "more",
    "less",
)


def _select_tools_for_execution(
    tool_calls: list[dict],
    classified_intents: list[dict],
) -> list[dict]:
    """
    Return the tool_calls that should actually run this round.

    Rules (in priority order):
    1. Safe passthrough tools are always kept.
    2. Tools that match a classified intent are kept.
    3. If multiple tools have equal confidence AND serve different purposes,
       keep all of them — they form a sequential chain.
    4. If two tools do the same thing (duplicates), keep only one.
    5. Tie-break: prefer screen_capture > get_time > first-in-list.
    """
    if not tool_calls:
        return []

    # Score each tool
    def _score(tc: dict) -> float:
        name = tc.get("function", {}).get("name", "").lower()
        best = 0.0
        for ci in classified_intents:
            if _aligns_with_intent(tc, ci["intent"]):
                best = max(best, ci["confidence"])

        if classified_intents:
            if best > 0:
                return best
            # Safe passthrough tools are allowed but should not override aligned tools.
            if name in _SAFE_PASSTHROUGH_TOOLS:
                return 0.1
            return 0.0

        # When no classified intents are available, preserve safe tools and let
        # the rest of the selection logic decide based on original tool calls.
        if name in _SAFE_PASSTHROUGH_TOOLS:
            return 1.0
        return 0.5

    scored = [(tc, _score(tc)) for tc in tool_calls]

    if not classified_intents:
        # With no semantic intents, preserve tool_calls and avoid safe tools dominating.
        top = [tc for tc, _ in scored]
    else:
        max_score = max(s for _, s in scored) if scored else 0.0
        # Keep all tools that hit the top score
        top = [tc for tc, s in scored if s == max_score]

    # Deduplicate by tool name (keep first occurrence)
    seen_names: set[str] = set()
    deduped = []
    for tc in top:
        name = tc.get("function", {}).get("name", "")
        if name not in seen_names:
            seen_names.add(name)
            deduped.append(tc)

    if len(deduped) == 1:
        log.info(f"[JARVIS][SELECT] Single tool: {deduped[0].get('function', {}).get('name')}")
        return deduped

    # Conflict check: open_app + close_app for the SAME app_name
    open_apps = {
        tc.get("function", {}).get("arguments", {}).get("app_name")
        for tc in deduped
        if tc.get("function", {}).get("name") == "open_app"
    }
    close_apps = {
        tc.get("function", {}).get("arguments", {}).get("app_name")
        for tc in deduped
        if tc.get("function", {}).get("name") == "close_app"
    }
    conflicts = open_apps & close_apps
    if conflicts:
        log.warning(
            f"[JARVIS][SELECT] Conflict: open+close same app — dropping conflicting close calls: {conflicts}"
        )
        deduped = [
            tc
            for tc in deduped
            if not (
                tc.get("function", {}).get("name") == "close_app"
                and tc.get("function", {}).get("arguments", {}).get("app_name") in conflicts
            )
        ]

    # Conflict: lock + shutdown in same round
    names = [tc.get("function", {}).get("name", "") for tc in deduped]
    if "lock_pc" in names and "shutdown_pc" in names:
        log.warning(
            "[JARVIS][SELECT] Conflict: lock+shutdown — dropping shutdown (lock takes priority)"
        )
        deduped = [tc for tc in deduped if tc.get("function", {}).get("name") != "shutdown_pc"]

    log.info(f"[JARVIS][SELECT] Chain: {[tc.get('function', {}).get('name') for tc in deduped]}")
    return deduped


# Global for storing classified intents
_last_classified_intents = []


# FIX 5: raw JSON output guard
_RAW_TOOL_CALL_RE = re.compile(r'^\s*\[?\s*\{.*?"type"\s*:\s*"function".*?\}', re.DOTALL)


def _is_raw_tool_json(text: str) -> bool:
    """Return True when the LLM accidentally emitted a raw tool_call JSON blob."""
    return bool(_RAW_TOOL_CALL_RE.match(text.strip()))


def _parse_raw_tool_json(text: str) -> list:
    """Parse raw tool JSON text into proper tool_calls format."""
    import json

    try:
        # Try to extract JSON from text (LLM may wrap it in markdown or add extra text)
        cleaned = text.strip()

        # Try direct parse first
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON array or object in the text
            # Look for pattern starting with [ or {
            import re

            json_match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                log.warning(f"[JARVIS] No valid JSON found in text: {cleaned[:100]}")
                return []

        # Ensure it's a list
        if not isinstance(data, list):
            data = [data]

        # Convert to proper tool_calls format
        tool_calls = []
        for item in data:
            if isinstance(item, dict):
                # Handle both formats: {"type": "function", "function": {...}} and direct function objects
                if "function" in item:
                    tool_calls.append(item)
                elif "name" in item:
                    # Direct function object - wrap it
                    tool_calls.append(
                        {
                            "type": "function",
                            "function": {
                                "name": item.get("name", ""),
                                "arguments": item.get("arguments", {}),
                            },
                        }
                    )

        if tool_calls:
            log.info(f"[JARVIS] Parsed {len(tool_calls)} tool calls from raw JSON")

        return tool_calls
    except Exception as e:
        log.warning(f"[JARVIS] Failed to parse raw tool JSON: {e}")
        return []


# ── System prompt (built once at startup) ────────────────────────────────────


def _make_system_prompt() -> str:
    return build_jarvis_prompt(
        system_context=config._SYSTEM_CONTEXT,
        user_home=config._USER_HOME,
        profile_summary=user_profile.get_profile_summary(),
    )


# ── Conversation history ──────────────────────────────────────────────────────


def _trim_history(history: list) -> list:
    return history[-(MAX_HISTORY * 2) :]


# ── TTS helpers ───────────────────────────────────────────────────────────────


class _Speaker:
    """Thread-safe TTS queue wrapper."""

    def __init__(self):
        self._q = tts.TTSQueue()
        self._q.start()

    def say(self, text: str):
        if text and text.strip():
            self._q.put(text.strip())

    def wait(self):
        self._q.join()

    def stop(self):
        self._q.stop()


# ── Main JARVIS loop ──────────────────────────────────────────────────────────


def main():
    log.info("=" * 60)
    log.info("J.A.R.V.I.S.  —  Autonomous AI System")
    log.info("=" * 60)

    speaker = _Speaker()
    history: list[dict] = []
    system_prompt = _make_system_prompt()
    tools = get_tools()

    # ── Ambient monitoring ────────────────────────────────────────────────
    monitor = AmbientMonitor(
        alert_cb=lambda msg: (speaker.say(msg), speaker.wait()),
        suggest_cb=lambda msg: (speaker.say(msg), speaker.wait()),
    )
    monitor.start()

    # ── Startup greeting ──────────────────────────────────────────────────
    speaker.say("J.A.R.V.I.S. online. All systems nominal.")
    speaker.wait()

    # ── Main conversation loop ────────────────────────────────────────────
    while True:
        try:
            # Listen (wake word or continuous depending on config)
            if config.CONTINUOUS_MODE:
                user_text = stt.listen(use_whisper=True)
            else:
                log.info("[JARVIS] Waiting for wake word...")
                wake_word.listen_for_wake_word()
                tts.play_chime()
                user_text = stt.listen(use_whisper=True)

            if not user_text or not user_text.strip():
                continue

            log.info(f"[USER] {user_text}")
            monitor.ping()  # Reset idle timer

            # Exit commands
            if any(
                w in user_text.lower()
                for w in ["shut down jarvis", "goodbye jarvis", "exit jarvis"]
            ):
                speaker.say("Shutting down. Goodbye.")
                speaker.wait()
                break

            # Record to history
            user_profile.save_conversation("user", user_text)

            # Decide: simple chat or agentic tool use
            needs_tools = _likely_needs_tools(user_text)

            if needs_tools:
                # ── Agentic mode: LLM + tool_use via orchestration ───────
                tts.play_think_chime()

                abort_event, abort_thread = wake_word.start_abort_listener()
                try:
                    final_text, history = _run_agentic_loop(
                        user_text=user_text,
                        history=history,
                        tools=tools,
                        system=system_prompt,
                        speaker=speaker,
                        abort_event=abort_event,
                    )
                    history = _trim_history(history)
                    speaker.wait()

                    if final_text:
                        user_profile.save_conversation("assistant", final_text)

                finally:
                    wake_word.stop_abort_listener(abort_event, abort_thread)
                    wake_word.extend_cooldown(4.0)

            else:
                # ── Conversational mode: streaming reply ──────────────────
                history.append({"role": "user", "content": user_text})
                full_reply = ""

                for sentence in stream_reply(history, system_prompt):
                    speaker.say(sentence)
                    full_reply += sentence + " "

                speaker.wait()
                full_reply = full_reply.strip()

                if full_reply:
                    history.append({"role": "assistant", "content": full_reply})
                    history = _trim_history(history)
                    user_profile.save_conversation("assistant", full_reply)

        except KeyboardInterrupt:
            speaker.say("Shutting down.")
            speaker.wait()
            break
        except Exception as e:
            log.error(f"[JARVIS] Unhandled error: {e}", exc_info=True)
            speaker.say("I encountered an unexpected error. Standing by.")
            speaker.wait()

    monitor.stop()
    speaker.stop()


# ── Tool execution bridge ─────────────────────────────────────────────────────


def _remap_params(action: str, params: dict) -> dict:
    """Normalize param names between LLM tool schemas and pc_control expectations."""
    p = dict(params)

    # LLM may use "app" or "app_name" — pc_control expects "app_name"
    if action in ("open_app", "close_app") and "app" in p and "app_name" not in p:
        p["app_name"] = p.pop("app")

    # Ensure volume level is int
    if action == "set_volume" and "level" in p:
        p["level"] = int(p["level"])

    return p


def _get_any_high_failure_rate() -> bool:
    """Check if any tool has > 50% failure rate."""
    try:
        if os.path.exists(TOOL_RELIABILITY_FILE):
            with open(TOOL_RELIABILITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, info in data.items():
                successes = info.get("successes", 0)
                failures = info.get("failures", 0)
                total = successes + failures
                if total >= 3 and failures > 0:
                    fail_rate = (failures / total) * 100
                    if fail_rate > 50:  # > 50%
                        return True
    except Exception:
        pass
    return False


def _run_agentic_loop(
    user_text: str, history: list, tools: list, system: str, speaker, abort_event
) -> tuple[str, list]:
    """
    Orchestrate: LLM → validate → execute → feed results back → repeat.
    jarvis.py coordinates; brain.py only does LLM inference.

    Improvements:
    - Better feedback to LLM on tool failures
    - Smarter retry decisions
    - Clearer task flow
    """
    messages = (
        [{"role": "system", "content": system}]
        + list(history)
        + [{"role": "user", "content": user_text}]
    )
    final_text = ""
    consecutive_failures = 0

    # FIX 4: Limit rounds for search/summarize tasks to prevent loops
    t_lower = user_text.lower()
    if "search" in t_lower and ("summarize" in t_lower or "explain" in t_lower):
        max_rounds = 3
        log.info("[JARVIS] Search+summarize task — limiting to 3 rounds")
    else:
        max_rounds = MAX_AGENT_ROUNDS

    for round_num in range(max_rounds):
        if abort_event and abort_event.is_set():
            log.info("[JARVIS] Aborted by user")
            break

        log.info(f"[JARVIS] Agentic round {round_num + 1}")

        # Determine if we should inject reliability context
        # ONLY inject when: previous round had failure OR tool failure rate > 50%
        should_inject_context = (consecutive_failures > 0) or _get_any_high_failure_rate()

        # Step 1: brain.py — LLM inference ONLY (tool_calls generation)
        text, messages, tool_calls = run_agent(
            messages, tools, speaker.say, abort_event, inject_context=should_inject_context
        )

        if text:
            final_text = text

        # FIX 5: if the LLM emitted a raw tool_call JSON blob as plain text,
        # parse it and use as tool_calls instead of speaking it.
        if text and _is_raw_tool_json(text):
            log.warning("[JARVIS] LLM emitted raw tool JSON as text — parsing")
            parsed_calls = _parse_raw_tool_json(text)
            if parsed_calls:
                tool_calls = parsed_calls
                log.info(f"[JARVIS] Successfully parsed {len(tool_calls)} tool calls from text")
            text = ""
            final_text = ""

        # BUG 4: Deduplicate repeated sentences (model sometimes echoes result twice)
        if text:
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            seen = []
            for s in sentences:
                if s not in seen:
                    seen.append(s)
            text = ". ".join(seen)
            if seen:
                text += "."
            final_text = text

        if not tool_calls:
            break  # LLM done, no more tool calls

        # FINAL INTENT RESOLVER: Filter tool_calls based on final user intent
        log.info(f"[JARVIS][INTENT] Raw: {user_text}")

        # Get classified intents with confidence
        global _last_classified_intents
        _last_classified_intents = classify_intents(user_text)
        log.info(f"[JARVIS][INTENT] Classified: {_last_classified_intents}")

        original_count = len(tool_calls)
        log.info(
            f"[JARVIS][FILTER] Before: {[t.get('function', {}).get('name', '') for t in tool_calls]}"
        )

        # Filter: keep tools that align with ANY classified intent OR are safe passthrough
        # FIX 2: Also trust the LLM when classifier returns nothing
        tool_calls = [
            t
            for t in tool_calls
            if (
                t.get("function", {}).get("name", "") in _SAFE_PASSTHROUGH_TOOLS
                or any(_aligns_with_intent(t, ci["intent"]) for ci in _last_classified_intents)
                or not _last_classified_intents
            )
        ]

        # FIX 3: allow chains, not just single-tool selection
        tool_calls = _select_tools_for_execution(tool_calls, _last_classified_intents)

        log.info(
            f"[JARVIS][FILTER] After: {[t.get('function', {}).get('name', '') for t in tool_calls]}"
        )

        # Scoring gate: evaluate tool calls for safety
        score = score_agent_round(tool_calls)
        decision, filtered_calls = apply_execution_gate(tool_calls, score)

        if decision == "BLOCK":
            log.warning(
                f"[JARVIS][GATE] Tool calls blocked (severity={score['severity']}): {score['issues']}"
            )
            messages.append(
                {
                    "role": "tool",
                    "content": f"BLOCKED: Tool calls rejected for safety. Issues: {', '.join(score['issues'])}. Try a different approach.",
                }
            )
            continue

        if decision == "DEGRADE":
            log.warning(
                f"[JARVIS][GATE] Tool calls degraded (severity={score['severity']}): keeping {len(filtered_calls)}/{len(tool_calls)} safe tools"
            )
            tool_calls = filtered_calls

        if not tool_calls:
            log.info("[JARVIS] No valid tool_calls after filtering, stopping")
            # FIX 2: Inform user when requested tool doesn't exist
            if original_count > 0:
                speaker.say("I don't have a tool for that. Let me try a different approach.")
            # BUG 1 Part B: Remove the last assistant message if it contains tool_calls
            # that were filtered out — prevents history pollution
            if messages and messages[-1].get("role") == "assistant":
                last = messages[-1]
                if last.get("tool_calls"):
                    messages[-1] = {"role": "assistant", "content": last.get("content", "") or ""}
                    log.info("[JARVIS] Stripped filtered tool_calls from assistant history message")
            # FIX 12: Clear final_text when all tool_calls are filtered
            final_text = ""
            break

        # NEW: Confirmation gate for dangerous actions
        confirmation_prompt = build_confirmation_prompt(tool_calls)
        if confirmation_prompt:
            log.warning("[JARVIS] Dangerous actions detected. Requesting user confirmation.")
            print(f"\n{confirmation_prompt}\n")
            speaker.say(
                "I need your approval before proceeding. The system is prompting you for confirmation."
            )
            user_response = input("Your response: ").strip().lower()

            if user_response not in ["yes", "y", "approve", "ok", "proceed"]:
                log.warning("[JARVIS] User denied dangerous actions. Stopping.")
                messages.append(
                    {
                        "role": "tool",
                        "content": "BLOCKED BY USER: User declined to approve dangerous actions.",
                    }
                )
                speaker.say("Operation cancelled. Please provide a different request.")
                final_text = "I was about to perform dangerous actions, but you declined approval."
                break
            else:
                log.info("[JARVIS] User approved dangerous actions. Proceeding.")
                speaker.say("Proceeding with your approval.")

        # Step 2: Validate + Execute each tool_call
        tool_messages = []
        round_failures = 0

        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            tc_id = tc.get("id", "")  # Capture tool_call_id for OpenAI API

            # Remap params (orchestration responsibility)
            remapped = _remap_params(name, args)

            # Validate via control_plane.py (validation ONLY)
            is_valid, error_msg = control_plane.validate_tool_call(name, remapped)

            if not is_valid:
                log.warning(f"[JARVIS] Tool {name} validation failed: {error_msg}")
                # Improve: Provide clearer feedback to LLM
                tool_messages.append(
                    {
                        "id": tc_id,
                        "result": f"FAILED: {error_msg}. Please check parameters and try again.",
                    }
                )
                round_failures += 1
                # Track failure (validation failure)
                _update_tool_reliability(name, success=False, error_msg=error_msg)
            else:
                # Step 3: Execute via pc_control.py (execution ONLY)
                log.info(f"[JARVIS] Executing validated tool: {name}")
                result = pc_control.execute_structured(name, remapped)

                # Track reliability after execution
                if isinstance(result, dict):
                    output = result.get("output") or result.get("verify_msg") or ""
                    if not result.get("success") and result.get("error"):
                        output = f"FAILED: {result['error']}"
                        round_failures += 1
                        _update_tool_reliability(
                            name, success=False, error_msg=result.get("error", "")
                        )
                    elif result.get("success"):
                        _update_tool_reliability(name, success=True)
                else:
                    output = str(result)

                tool_messages.append({"id": tc_id, "result": output or "(no output)"})

        # Improve: Track consecutive failures for smarter retry
        if round_failures > 0:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                log.warning("[JARVIS] Too many consecutive failures, stopping agentic loop")
                final_text = f"I encountered multiple failures and cannot complete the task. Last error: {tool_messages[-1]['result'][:100]}"
                break
        else:
            consecutive_failures = 0

        # Step 4: Feed results back to LLM (brain.py processes in next iteration)
        for tm in tool_messages:
            messages.append({"role": "tool", "content": tm["result"], "tool_call_id": tm["id"]})

    # Return updated history (exclude system message)
    updated = [m for m in messages if m.get("role") != "system"]
    updated = updated[-(config.MAX_HISTORY * 2) :]
    return final_text, updated


# ── Heuristic: does this query need tool use? ─────────────────────────────────

_CHAT_ONLY_PATTERNS = (
    "what do you think",
    "tell me about",
    "explain",
    "how does",
    "who is",
    "why is",
    "what are",
    "can you help me",
    "thank you",
    "thanks",
    "hello",
    "hi jarvis",
    "good morning",
    "good evening",
    "how are you",
    "what's up",
)

_TOOL_PATTERNS = (
    "open",
    "close",
    "launch",
    "start",
    "stop",
    "kill",
    "volume",
    "mute",
    "unmute",
    "louder",
    "quieter",
    "screenshot",
    "screen",
    "battery",
    "charge",
    "time",
    "date",
    "clock",
    "cpu",
    "ram",
    "memory",
    "disk",
    "drive",
    "wifi",
    "network",
    "ip address",
    "internet",
    "ip",
    "brightness",
    "dark mode",
    "night",
    "lock",
    "sleep",
    "restart",
    "shutdown",
    "note",
    "remind",
    "timer",
    "alarm",
    "file",
    "folder",
    "create",
    "delete",
    "read",
    "search",
    "google",
    "clipboard",
    "copy",
    "paste",
    "calculate",
    "compute",
    "run",
    "execute",
    "script",
    "powershell",
    "install",
    "update",
    "health",
    "status",
    "process",
    "task",
    "system",
    "computer",
    "pc",
    "apps",
    "running",
    # FIX 1: Add indexing/listing patterns for commands like "index software shortcuts"
    "index",
    "list",
    "show",
    "display",
    "find",
)


def _likely_needs_tools(text: str) -> bool:
    """Smarter heuristic: does this query need tool use?"""
    t = text.lower()

    # Improve: Check for negation patterns that indicate NO tool needed
    negation_patterns = ["don't", "do not", "not", "never", "stop", "cancel"]
    has_negation = any(neg in t for neg in negation_patterns)

    # BUG 1 Part A: Correction patterns that reference a previous action should re-execute agentically
    if any(p in t for p in _CORRECTION_PATTERNS) and any(p in t for p in _VALUE_PATTERNS):
        return True

    # If explicitly chat-only AND no negation, skip tools
    if any(p in t for p in _CHAT_ONLY_PATTERNS) and not has_negation:
        return False

    # Improve: Better detection of tool needs with context
    # Check for action verbs + object patterns
    action_object_patterns = [
        "open the",
        "close the",
        "launch the",
        "start the",
        "stop the",
        "set the",
        "get the",
        "show me",
        "tell me the",
        "find the",
        "what is the",
        "what's the",
        "how is the",
        "check the",
        "what is my",
        "what's my",  # FIX 6: "what is my ip/name/battery"
    ]
    if any(p in t for p in action_object_patterns):
        return True

    # Standard tool pattern check
    if any(p in t for p in _TOOL_PATTERNS):
        return True

    # Improve: Default to chat for short, simple queries
    if len(t.split()) <= 4 and "?" in t:
        return False

    return False  # Default to chat for safety


if __name__ == "__main__":
    main()
