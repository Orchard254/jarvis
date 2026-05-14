"""
Planner — pre-execution planning phase for the tool loop.

When the user gives a complex request, the planner calls the LLM once to
generate a structured multi-step plan BEFORE any tool executes. This avoids
the expensive 1-tool-call-per-iteration pattern and enables parallel execution
of independent steps.

Two modes:
  1. Native tool-calling: if the LLM returns tool_calls, they become the plan.
  2. JSON text: if no tool_calls, tries to extract JSON from the response.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

def _valid_tool_names(tool_schemas: list[dict]) -> set[str]:
    return {s["function"]["name"] for s in tool_schemas}

_PLANNER_PROMPT = """\
You are the planning system for JARVIS. Review live system state below. Plan accordingly.

Output ONLY valid JSON. No other text.
{
  "steps": [
    {
      "tool": "tool_name",
      "args": { "param": "value" },
      "description": "what this does"
    }
  ],
  "reasoning": "why this plan"
}

=== TOOLS (exact names — NEVER prefix with "functions." or "tools.") ===
1. window(action, ...)  — App lifecycle. open(launch OR focus if running), close, focus, list, minimize, maximize, state.
2. screen(action, ...)  — Perception. capture, find(UIA element by text, click=true to click it), elements(list all clickable), tree, query, ocr.
3. input(action, ...)   — Mouse+keyboard. click(x,y), type(text), hotkey(keys), scroll, drag.
4. browser(action, ...) — Web. navigate(url), click(selector), type(selector,text), read_page, screenshot, scroll.
5. exec(action, ...)    — Code+files (last resort). run(code), read(path), write(path,content).
6. memory(action, ...)  — Persistent facts. store(key,value), recall(key), search(query).

=== DECISION TREE (follow top to bottom) ===
Open/close/focus app? → window(open|close|focus). ONE step. Done.
Go to URL/web page?   → browser(navigate). ONE step.
Click UI element?     → screen(find, text="...", click=true). ONE step.
Type text/hotkey?     → input(type|hotkey). ONE step.
Read/write file?      → exec(read|write). ONE step.
Remember something?   → memory(store). ONE step.
System info?          → window(state). ONE step.
Volume/brightness?    → exec(run) with stdlib import. ONE step.

=== EXAMPLES (correct plans) ===
"open notepad" → 1 step:
  [{"tool":"window","args":{"action":"open","app_name":"notepad"},"description":"launch notepad"}]

"open notepad and type hello" → 2 steps:
  [{"tool":"window","args":{"action":"open","app_name":"notepad"},"description":"launch notepad"},
   {"tool":"input","args":{"action":"type","text":"hello"},"description":"type hello"}]

"go to google.com and search for cats" → 1 step:
  [{"tool":"browser","args":{"action":"navigate","url":"https://www.google.com/search?q=cats"},"description":"search google for cats"}]

"click the Save button" → 1 step:
  [{"tool":"screen","args":{"action":"find","text":"Save","click":true},"description":"click Save button"}]

"set volume to 50" → 1 step:
  [{"tool":"exec","args":{"action":"run","code":"from skills.stdlib.system import volume_mute_then_set; print(volume_mute_then_set(50))"},"description":"set volume to 50%"}]

=== RULES ===
1. MINIMUM steps. Most tasks need 1-2 steps, not 5-8.
2. window(open) does everything (check running → focus → launch → wait → focus). NEVER add extra check/focus steps.
3. screen(find, click=true) finds AND clicks in ONE call. Don't split into find + click.
4. tool results already say success/fail. NEVER add a "verify" step with screen(query) or screen(capture).
5. exec(run) is last resort — prefer window, screen, browser, input.
6. For web tasks: use browser(), not exec(run) with requests.
7. MAX 6 steps. If you need more, the plan is too complex — simplify.
8. NEVER type AND paste the same text. Pick one.

=== COMMON MISTAKES (avoid these) ===
BAD: window(state) → window(open, "notepad")    ← state check is unnecessary, open handles it
BAD: screen(find, "Save") → input(click, x, y)  ← use screen(find, click=true) instead
BAD: window(open, "chrome") → browser(navigate)  ← just use browser(navigate), it auto-launches
BAD: Adding screen(capture) at the end to verify ← tool results already confirm success
"""


def _build_system_context(state_context: str = "") -> str:
    """Build a compact system context block.

    State context is optionally passed in from the orchestrator
    (which has tool access). The planner never imports the tools layer.
    """
    try:
        import datetime, platform, socket, sys
        from pathlib import Path

        lines = [
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Host: {socket.gethostname()} | OS: {platform.system()} {platform.version()[:20]}",
        ]
        if state_context:
            lines.append(state_context)
        lines.append(f"Desktop: {Path.home() / 'Desktop'}")
        return "\n".join(lines)
    except Exception:
        return ""


def build_plan(
    user_input: str,
    history: list[dict],
    memory_context: str,
    tool_schemas: list[dict],
    live_state: str = "",
) -> dict:
    """Generate a structured execution plan from user input.

    Returns:
        {"success": True, "steps": [...], "reasoning": "..."}
        or {"success": False, "error": "..."}
    """
    system_context = _build_system_context(live_state)
    full_prompt = _PLANNER_PROMPT
    if system_context:
        full_prompt += f"\n=== SYSTEM CONTEXT ===\n{system_context}\n"
    if memory_context:
        full_prompt += f"\n=== MEMORY ===\n{memory_context}\n"

    messages = [
        {"role": "system", "content": full_prompt},
    ]

    # Include recent history — more context helps the planner
    recent = history[-6:] if history else []
    for m in recent:
        if m.get("role") in ("user", "assistant"):
            messages.append(m)

    messages.append({"role": "user", "content": f"Plan this: {user_input}"})

    try:
        from brain import ollama_client
        from settings import REASONING_EFFORT

        valid_names = _valid_tool_names(tool_schemas)

        result = ollama_client.chat(
            messages=messages,
            tools=tool_schemas,
            temperature=0.1,
            reasoning_effort=REASONING_EFFORT,
        )

        content = (result.get("content") or "").strip()
        tool_calls = result.get("tool_calls") or []

        # ── Mode 1: Native tool_calls from LLM ───────────────────────────────
        if tool_calls:
            steps = []
            for tc in tool_calls:
                name = tc.get("function", {}).get("name", "")
                # Strip invalid prefixes like "functions." or "tools."
                name = _clean_tool_name(name)
                if name not in valid_names:
                    logger.warning(f"Planner: invalid tool '{name}' — skipping")
                    continue
                try:
                    args_raw = tc.get("function", {}).get("arguments", {})
                    if isinstance(args_raw, str):
                        args = json.loads(args_raw)
                    else:
                        args = args_raw
                except (json.JSONDecodeError, TypeError):
                    args = {}
                steps.append({
                    "tool": name,
                    "args": args,
                    "batch_with": [],
                    "description": name,
                })

            if steps:
                logger.info(f"Planner (native calls): {len(steps)} steps")
                return {
                    "success": True,
                    "steps": steps,
                    "reasoning": "native tool calls",
                }

        # ── Mode 2: Try to extract JSON from text response ──────────────────
        if content:
            plan = _extract_json(content)
            if plan:
                steps = plan.get("steps", [])
                if steps:
                    cleaned = []
                    for step in steps:
                        if "tool" not in step:
                            continue
                        step["tool"] = _clean_tool_name(step["tool"])
                        if step["tool"] not in valid_names:
                            logger.warning(f"Planner: invalid tool '{step['tool']}' — skipping step")
                            continue
                        if "args" not in step:
                            step["args"] = {}
                        if "batch_with" not in step:
                            step["batch_with"] = []
                        cleaned.append(step)

                    if cleaned:
                        logger.info(f"Planner (JSON): {len(cleaned)} steps")
                        return {
                            "success": True,
                            "steps": cleaned,
                            "reasoning": plan.get("reasoning", ""),
                        }

            logger.warning(f"Planner: could not extract valid plan from LLM response")
            logger.debug(f"Planner raw: {content[:300]}")
            return {"success": False, "error": "No valid plan in LLM response"}

        return {"success": False, "error": "Empty LLM response"}

    except Exception as e:
        logger.warning(f"Planner failed: {e}")
        return {"success": False, "error": str(e)}


def _clean_tool_name(name: str) -> str:
    """Strip invalid prefixes from tool names and return the canonical name."""
    if not name:
        return ""
    # Remove common invalid prefixes
    for prefix in ("functions.", "tools.", "fn_", "tool_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.strip()


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from text, trying multiple strategies."""
    if not text:
        return None

    # Strategy 1: Try parsing the whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown fences
    cleaned = re.sub(r"^```[a-z]*\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    if cleaned != text:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find JSON object in text (between { and })
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidate = text[brace_start : brace_end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 4: Fix common JSON issues — trailing commas
    fixed = text.strip()
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*\]", "]", fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Strategy 5: Try to fix unquoted keys (Python dict style)
    try:
        import ast
        fixed2 = re.sub(r"(['\"])?(\w+)(['\"])?\s*:", r'"\2":', text.strip())
        fixed2 = re.sub(r",\s*}", "}", fixed2)
        fixed2 = re.sub(r",\s*\]", "]", fixed2)
        return json.loads(fixed2)
    except (json.JSONDecodeError, Exception):
        pass

    return None