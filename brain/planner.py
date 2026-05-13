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
You are the planning system for JARVIS. Before planning, review the live system state below and consider: is the app already running? Is the window already open? Plan accordingly.

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

=== AVAILABLE TOOLS (use exact names below) ===
Tool names are plain. NEVER prefix with "functions." or "tools.".

1. screen(action, ...)
   Perception. Actions: capture (screenshot; use grid=true for coordinate grid overlay), find (locate UI element by text via UIA — falls back to vision+grid for web content), tree (UI tree), elements (list ALL interactive elements with coordinates — merges UIA + vision), query (ask vision model), ocr (read text).

2. input(action, ...)
   Mouse+keyboard. Actions: click, type, hotkey, scroll, drag.

3. window(action, ...)
   App/window + desktop. Actions: open (launch app — checks if running first, focuses if so), close, focus, list, minimize, maximize, state (live desktop snapshot of windows/processes).

4. browser(action, url, selector, text)
   Web browser via Playwright. Supports Brave, Opera, Firefox, Chrome. Auto-connects to running browser via CDP, or launches preferred (set BROWSER_PREFERRED). Actions: navigate, click, type, read_page, screenshot, scroll.

5. exec(action, ...)
   Code + files (escape hatch). Actions: run (Python/PowerShell), read (file), write (file).

6. memory(action, key, value)
   Persistent facts. Actions: store, recall, search.

=== GUIDELINES ===
1. Check window(state) first if you need to know what's running before planning.
2. For "open <app>": window(open) handles everything — checks running, focuses, or launches.
3. For finding UI elements: screen(find) uses UIA — deterministic, no OCR. Falls back to vision+grid for web content.
4. For clicking: use screen(find, click=true) or input(click). Use screen(elements) first if you don't know the element name.
4b. For apps where UIA doesn't work (Chrome web content, Electron apps): use screen(elements) to discover elements, then input(click, x=..., y=...) with the coordinates.
5. For web: prefer browser() over exec(run).
6. For file read/write: use exec(read/write).
7. MAX 8 steps.
8. NEVER type AND paste same text. Pick one.
9. NEVER call screen(query) just to verify — tool results already say success/fail.

=== COMMON FAILURES TO AVOID ===
1. window(open) already handles "is it running? focus it" — do NOT add separate check steps.
2. exec(run) is a last resort — prefer dedicated tools (window, screen, browser, input).
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