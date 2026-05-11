"""
LLM-based intent router for keyword-cache-miss classification.

Makes a cheap LLM call (compact routing prompt, short tool-name reply) to pick
which tools should handle a user request. Intended to be called from
core/intent_router.py when keyword matching produces no confident result.

Design contract
---------------
cheap         : temperature=0.0, no tool schemas passed (plain text only)
fast          : single call, no chain-of-thought, no explanation requested
deterministic : same input → same output (temperature=0.0)
layer-safe    : only imports from brain.ollama_client at module level;
                tools.TOOL_REGISTRY is imported lazily inside the function
                to break the tools → brain circular-import chain
safe          : returns [] on ANY failure (LLM down, timeout, parse error)
"""

import concurrent.futures
import logging
import re

from brain.ollama_client import chat

logger = logging.getLogger(__name__)

# Small talk only (no OS action) — returning [] lets pruning use default tool order
# without falsely steering the main model toward ``notify_user``.
_SOCIAL_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "howdy",
        "greetings",
        "thanks",
        "thank",
        "you",
        "thx",
        "ty",
        "good",
        "morning",
        "afternoon",
        "evening",
        "there",
    }
)

# ---------------------------------------------------------------------------
# Keyword pre-router — catches obvious action commands without an LLM call.
# BUG FIX: previously "close notepad", "kill chrome", etc. would time out or
# be misclassified as social_chat by the LLM router.  A fast keyword pass
# short-circuits the LLM entirely for unambiguous action verbs.
# ---------------------------------------------------------------------------




def _is_social_only_message(text: str) -> bool:
    words = [w for w in re.findall(r"[a-zA-Z']+", text.lower()) if w.isalpha()]
    return bool(words) and len(words) <= 5 and all(w in _SOCIAL_WORDS for w in words)


# ---------------------------------------------------------------------------
# Dynamic tool name helper
# ---------------------------------------------------------------------------


def _get_tool_names_str() -> str:
    """Dynamically get tool names so the prompt stays in sync with the registry."""
    try:
        from tools import TOOL_REGISTRY  # noqa: PLC0415

        return ", ".join(sorted(TOOL_REGISTRY.keys()))
    except Exception:
        # Fallback to a hardcoded list if import fails
        return (
            "execute_code, capture_screen, read_pc_state, control_window, "
            "control_input, query_pc_index, read_file, write_file, notify_user"
        )


# ---------------------------------------------------------------------------
# Routing system prompt — one line per schema from TOOL_SCHEMAS (includes custom tools).
# ---------------------------------------------------------------------------


def _build_tool_reference_lines() -> str:
    """Compact descriptions aligned with the main agent's tool schemas."""
    try:
        from tools import TOOL_SCHEMAS  # noqa: PLC0415

        rows = []
        for spec in TOOL_SCHEMAS:
            fn = spec["function"]
            name = fn["name"]
            desc = (fn.get("description") or "").replace("\n", " ").strip()
            if len(desc) > 170:
                desc = desc[:167] + "..."
            rows.append(f"  {name:18} — {desc}")
        return "\n".join(rows)
    except Exception:
        return "  (tool list unavailable)"


def _build_system_prompt() -> str:
    """Build the routing system prompt with the live tool registry."""
    tool_lines = _build_tool_reference_lines()
    names_csv = _get_tool_names_str()
    return (
        "You are a tool-routing classifier for a Windows desktop AI agent.\n"
        "Reply with ONLY the tool name(s). No explanation. No punctuation except commas.\n"
        "Default to EXACTLY ONE tool. Use 2 tools only when the task genuinely requires both.\n"
        "NEVER add capture_screen, read_pc_state, or query_pc_index as verification steps — "
        "the agent handles errors itself.\n"
        "Pure greetings or thanks with no action → reply exactly: none\n"
        "\n"
        "Tools:\n"
        f"{tool_lines}\n"
        f"\nValid names: {names_csv}\n"
        "\nExamples (reply is ONLY what follows the →):\n"
        "show desktop → control_input\n"
        "mute volume → system_settings\n"
        "set brightness to 50 → system_settings\n"
        "close chrome → execute_code\n"
        "close notepad → execute_code\n"
        "kill firefox → execute_code\n"
        "terminate an app → execute_code\n"
        "quit calculator → execute_code\n"
        "open spotify → execute_code\n"
        "open notepad and calculator → execute_code\n"
        "launch notepad → execute_code\n"
        "list open windows → read_pc_state\n"
        "arrange open windows → execute_code\n"
        "search for python tutorials → search_web\n"
        "check wifi → system_settings\n"
        "take a screenshot → capture_screen\n"
        "hello → none\n"
        "good morning → none\n"
        "thanks → none\n"
    )


# Delimiter pattern: comma, semicolon, or newline (with optional surrounding whitespace)
_SPLIT_RE = re.compile(r"[,;\n]+")


def ask_llm_routing(intent: str) -> list[str]:
    """
    Ask the LLM which tool(s) best handle this intent.

    The call is deliberately minimal:
    - No tool schemas attached (``tools=[]``) → plain text response only.
    - ``temperature=0.0`` → fully deterministic output.
    - Single user message appended to the compact system prompt.

    Parsing is permissive to handle varied LLM output styles:
    - ``"execute_code"``                   — single tool
    - ``"execute_code, query_pc_index"``   — comma-separated
    - ``"execute_code; capture_screen"``   — semicolons
    - ``"execute_code\\nquery_pc_index"``   — newlines
    - ``"I recommend execute_code"``       — preamble (stripped via filter)

    Parameters
    ----------
    intent : str
        The raw user request text.

    Returns
    -------
    list[str]
        One to three valid tool name strings (keys of ``TOOL_REGISTRY``),
        or ``[]`` on any failure — LLM unavailable, timeout, parse error, or
        response containing no recognisable tool names.
    """
    try:
        # Lazy import: tools/__init__.py pulls in all tool modules, some of
        # which may import from brain/ or core/.  Deferring the import here
        # prevents a circular-import error at module load time.
        from tools import TOOL_REGISTRY  # noqa: PLC0415

        if _is_social_only_message(intent):
            logger.info(
                "router_llm: social-only message -> [] (no routing tools) %r",
                intent[:60],
            )
            return []

        # ── Semantic classifier: understand intent from meaning, not keywords ──
        # Uses the already-loaded embedding model to compare this input against
        # a broad prototype bank (15-25 diverse phrasings per tool).
        # Handles casual/slang/indirect phrasings without any pattern hardcoding.
        # Adapts over time via reinforce() called from intent_learner.record_route().
        try:
            from brain.intent_classifier import _classifier, HIGH_CONF, MED_CONF  # noqa: PLC0415

            sem_tools, sem_conf = _classifier.classify(intent)
            if sem_conf >= HIGH_CONF:
                # High confidence — skip the LLM entirely
                logger.info(
                    "router_llm: semantic [%.2f] %r -> %s",
                    sem_conf, intent[:60], sem_tools,
                )
                return sem_tools  # may be [] for social, or [tool] for action
            elif sem_conf >= MED_CONF and sem_tools:
                # Medium confidence — still call LLM but seed with semantic hint
                logger.debug(
                    "router_llm: semantic hint [%.2f] %r -> %s (LLM confirms)",
                    sem_conf, intent[:60], sem_tools,
                )
                # Fall through to LLM with sem_tools as candidate (logged above)
        except Exception as _sem_exc:
            logger.debug("router_llm: semantic classifier unavailable (%s)", _sem_exc)

        messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": intent},
        ]

        # tools=[] → falsy in ollama_client.chat(), so no "tools" key is added
        # to the payload; the LLM returns a plain text "content" field only.
        # Wrap in a 12-second timeout — cloud models can be slow; 5s caused
        # false timeouts on slightly longer intents.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                chat,
                messages=messages,
                tools=[],
                temperature=0.0,
            )
            try:
                response = future.result(timeout=12.0)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "router_llm: routing timed out (12s) — returning empty list"
                )
                return []
            except Exception as e:
                logger.warning(f"router_llm: routing error — {e}")
                return []

        raw: str = (response.get("content") or "").strip()

        # ── Parse response ────────────────────────────────────────────────
        # Two-pass strategy so every stated output style is handled:
        #
        # Pass 1 — coarse split on delimiters (,  ;  \n), then normalise the
        #           whole token.  Catches clean responses and "execute code"
        #           (spaces → underscores) style variants.
        #
        # Pass 2 — word-level scan inside tokens that didn't match in pass 1.
        #           Catches preamble responses like "I recommend execute_code"
        #           where there are no delimiters at all.
        normalized = raw.strip().lower().strip(".'\"")
        if normalized in ("none", "n/a", "nothing", "noop", "_"):
            logger.info("router_llm: %r -> [] (explicit no-tools)", intent[:60])
            return []

        tokens = _SPLIT_RE.split(raw)
        valid: list[str] = []
        for tok in tokens:
            # Pass 1: normalise the whole token
            name = tok.strip().lower().replace(" ", "_")
            if name in TOOL_REGISTRY and name not in valid:
                valid.append(name)
            else:
                # Pass 2: scan individual words within the token
                for word in tok.strip().lower().split():
                    if word in TOOL_REGISTRY and word not in valid:
                        valid.append(word)
                    if len(valid) == 3:
                        break
            if len(valid) == 3:
                break

        logger.info("router_llm: %r -> %s", intent[:60], valid)
        return valid

    except Exception as exc:  # noqa: BLE001  (broad catch is intentional)
        # Routing failures are expected when the LLM is offline or slow.
        # Log at DEBUG only so production logs stay clean; callers receive [].
        logger.debug("router_llm: routing call failed (%s), returning []", exc)
        return []
