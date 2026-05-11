"""
brain/intent_classifier.py — Local semantic intent classifier for JARVIS.

Design philosophy
-----------------
Humans say the same thing in dozens of ways:
  "close notepad", "kill notepad", "shut notepad", "yo shut down notepad",
  "can you get rid of notepad", "terminate the notepad window", etc.

Regex patterns and prefix matching collapse under this variation.  An LLM
call handles it correctly but costs 1–12 seconds and can time out.

This module sits between the two extremes:
  - Embeds a **prototype bank** of 15–25 diverse phrasings per tool at startup.
  - On classify(), embeds the user input once and computes max cosine similarity
    against every prototype — no LLM call, ~1ms latency.
  - Returns (tool_list, confidence).  High confidence → skip the LLM entirely.
  - **Adaptive**: record_route() in intent_learner calls reinforce() so every
    successful user command adds its exact phrasing to the live prototype bank.
    The system literally gets smarter with every command it handles.

Thresholds
----------
HIGH_CONF = 0.70   Classify immediately, no LLM call.
MED_CONF  = 0.52   Return result but still run LLM as sanity check.
LOW_CONF  < 0.52   Novel/ambiguous — hand off to LLM unconditionally.

Social disambiguation
---------------------
If social_chat scores highest but the margin over the next tool is < 0.08,
the input might be a command phrased politely ("can you please open chrome").
In that case we fall through to the LLM rather than silencing the action.

Layer boundary
--------------
This module may be imported by brain/ and core/ modules.
It must NOT import from tools/, core/orchestrator, or core/intent_router at
module level (to avoid circular imports).
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ── Confidence thresholds ─────────────────────────────────────────────────────

HIGH_CONF: float = 0.70   # route without LLM call
MED_CONF: float = 0.52    # route, but LLM confirms
SOCIAL_MARGIN: float = 0.08  # social must win by this margin to be returned as []

# ── Prototype bank ────────────────────────────────────────────────────────────
# Each entry covers: direct commands, indirect ("can you..."), casual/slang,
# multi-word variants, and partial/typo-ish phrasings real users produce.
# Goal: semantic spread within the cluster, discrimination between clusters.

_PROTOTYPES: dict[str, list[str]] = {

    "execute_code": [
        # Launch apps — verb diversity
        "open notepad",
        "launch calculator",
        "start chrome",
        "run spotify",
        "fire up vs code",
        "boot up the browser",
        "can you open notepad for me",
        "please start the calculator",
        "yo open notepad",
        "open notepad and calculator",
        "launch both notepad and chrome",
        "start notepad and open calculator at the same time",
        # Close / kill apps
        "close notepad",
        "kill firefox",
        "terminate chrome",
        "quit the app",
        "shut down notepad",
        "exit notepad",
        "get rid of notepad",
        "close that window",
        "can you close notepad please",
        "yo shut notepad",
        "kill all browser windows",
        "terminate the running process",
        "close everything",
        # Scripts / code
        "run a python script",
        "execute this code",
        "run the script",
        "write a script to move these files",
        "arrange windows in a grid",
        "tile the open windows side by side",
        "restart the app",
        "reboot the process",
    ],

    "system_settings": [
        # Volume
        "mute the volume",
        "unmute audio",
        "turn off the sound",
        "silence my computer",
        "set volume to 50",
        "increase the volume",
        "lower the volume",
        "turn it down",
        "make it louder",
        "can you increase the volume please",
        "volume up",
        "volume down",
        "reduce the audio",
        # Brightness
        "set brightness to 70",
        "dim the screen",
        "brighten the display",
        "make the screen brighter",
        "lower screen brightness",
        "turn up the brightness",
        "adjust the display brightness",
        "screen is too bright",
        # Network / connectivity
        "enable wifi",
        "disable wifi",
        "turn on bluetooth",
        "turn off bluetooth",
        "connect to wifi",
        "disconnect from network",
        "toggle airplane mode",
        # Power / misc
        "turn on do not disturb",
        "enable night mode",
        "turn on dark mode",
        "change the system theme",
        "enable battery saver",
    ],

    "control_window": [
        "minimize that window",
        "minimize notepad",
        "maximize chrome",
        "make the window full screen",
        "restore the window",
        "resize notepad to half the screen",
        "move window to the left",
        "snap window to the right side",
        "show desktop",
        "bring this window to the front",
        "focus on the chrome window",
        "put windows side by side",
        "make it smaller",
        "make the window bigger",
        "rearrange my windows",
        "move the window to my second monitor",
    ],

    "capture_screen": [
        "take a screenshot",
        "capture the screen",
        "screenshot please",
        "take a picture of my screen",
        "snap the screen",
        "capture what is on screen right now",
        "grab a screenshot",
        "screen capture",
        "save a screenshot",
        "take a screenshot of the current window",
    ],

    "search_web": [
        "search for python tutorials",
        "look up the weather in nairobi",
        "google best restaurants near me",
        "find information about quantum computing",
        "search the web for AI news",
        "look up the stock price of apple",
        "what is the latest news",
        "browse for recipes",
        "find me articles about machine learning",
        "who won the match yesterday",
        "look up how to cook rice",
        "search online for laptop reviews",
    ],

    "read_pc_state": [
        "list open applications",
        "what apps are running right now",
        "show running processes",
        "what is open on my computer",
        "list all open windows",
        "check what is currently running",
        "show me active processes",
        "what programs are open",
        "how much memory am I using",
        "show system resource usage",
        "show cpu usage",
        "what is my ram usage",
    ],

    "read_file": [
        "read this file",
        "open and show me the document",
        "what does the file say",
        "show me the contents of the text file",
        "read the log file",
        "display the file contents",
        "load the document and show me",
        "open the readme file",
        "can you read my notes file",
        "show me what is in the file",
    ],

    "write_file": [
        "write this to a file",
        "save this text to a new file",
        "create a new document",
        "write a note and save it",
        "save the output to a file",
        "create a text file with this content",
        "write to the config file",
        "append this to the log file",
        "make a new file and write in it",
        "save my notes to a file",
    ],

    "memory_tool": [
        "remember that my name is alex",
        "save this for later",
        "remember I prefer dark mode",
        "what did I ask you before",
        "recall what I told you about the project",
        "store this information",
        "what do you remember about me",
        "forget what I said about passwords",
        "keep track of my preferences",
        "note that I like classical music",
    ],

    "social_chat": [
        "hello",
        "hi there",
        "hey",
        "good morning",
        "good evening",
        "good afternoon",
        "how are you",
        "what is up",
        "thanks",
        "thank you so much",
        "that is great",
        "nice work",
        "you are amazing",
        "bye",
        "goodbye",
        "see you later",
        "tell me a joke",
        "what can you do",
        "who are you",
        "are you an ai",
    ],
}


# ── Classifier ────────────────────────────────────────────────────────────────


class SemanticIntentClassifier:
    """
    Classify user intent by semantic similarity to a prototype bank.

    Thread-safe.  Lazy-initialised on first call to classify() so startup
    time is unaffected.  Falls back gracefully if the embedder is unavailable.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False
        # {tool_name: [[float, ...], ...]}  — embedded prototype vectors
        self._vectors: dict[str, list[list[float]]] = {}
        # dynamic phrases learned from user commands at runtime
        # {tool_name: [phrase, ...]}
        self._dynamic: dict[str, list[str]] = {}

    # ── Initialisation ────────────────────────────────────────────────────────

    def _ensure_ready(self) -> bool:
        """Embed all prototypes on first call.  Returns True if ready."""
        if self._ready:
            return True
        with self._lock:
            if self._ready:  # double-check after acquiring lock
                return True
            try:
                from skills import skill_embedder  # noqa: PLC0415

                all_tools = list(_PROTOTYPES.keys())
                for tool in all_tools:
                    phrases = _PROTOTYPES[tool]
                    vecs: list[list[float]] = []
                    for phrase in phrases:
                        try:
                            v = skill_embedder.embed_text(phrase)
                            if v:
                                vecs.append(v)
                        except Exception:
                            pass
                    if vecs:
                        self._vectors[tool] = vecs
                        logger.debug(
                            "intent_classifier: embedded %d prototypes for %s",
                            len(vecs),
                            tool,
                        )

                if self._vectors:
                    self._ready = True
                    logger.info(
                        "intent_classifier: ready — %d tools, %d total prototypes",
                        len(self._vectors),
                        sum(len(v) for v in self._vectors.values()),
                    )
                    return True
                else:
                    logger.warning("intent_classifier: no vectors built (embedder may be loading)")
                    return False

            except Exception as exc:
                logger.debug("intent_classifier._ensure_ready failed: %s", exc)
                return False

    # ── Core similarity ───────────────────────────────────────────────────────

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        """Fast pure-Python cosine similarity."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)

    def _score_tool(self, query_vec: list[float], tool: str) -> float:
        """Return the max cosine similarity between query and any prototype for tool."""
        vecs = self._vectors.get(tool, [])
        if not vecs:
            return 0.0
        return max(self._cosine(query_vec, v) for v in vecs)

    # ── Public API ────────────────────────────────────────────────────────────

    def classify(self, text: str) -> tuple[list[str], float]:
        """
        Classify *text* into a tool list.

        Returns
        -------
        (tool_list, confidence)
            tool_list : e.g. ["execute_code"] or [] for social/unknown.
            confidence: 0.0–1.0.  < MED_CONF means the LLM should decide.
        """
        if not self._ensure_ready():
            return [], 0.0

        try:
            from skills import skill_embedder  # noqa: PLC0415

            query_vec = skill_embedder.embed_text(text)
        except Exception as exc:
            logger.debug("intent_classifier.classify embed failed: %s", exc)
            return [], 0.0

        if not query_vec:
            return [], 0.0

        # Score every tool
        scores: dict[str, float] = {}
        for tool in self._vectors:
            scores[tool] = self._score_tool(query_vec, tool)

        if not scores:
            return [], 0.0

        # Find top-2 scores for margin calculation
        sorted_tools = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_tool, best_score = sorted_tools[0]
        second_score = sorted_tools[1][1] if len(sorted_tools) > 1 else 0.0
        margin = best_score - second_score

        logger.debug(
            "intent_classifier: %r → best=%s(%.3f) 2nd=%.3f margin=%.3f",
            text[:60],
            best_tool,
            best_score,
            second_score,
            margin,
        )

        # Social disambiguation: if social wins but margin is thin, fall through.
        # "can you please open chrome" should not be silenced as chit-chat.
        if best_tool == "social_chat" and margin < SOCIAL_MARGIN:
            logger.debug(
                "intent_classifier: social margin too thin (%.3f) — deferring", margin
            )
            return [], 0.0

        if best_score < MED_CONF:
            return [], best_score  # too uncertain — let LLM handle it

        if best_tool == "social_chat":
            return [], best_score  # signal: no tool needed

        return [best_tool], best_score

    def reinforce(self, phrase: str, tool: str, success: bool) -> None:
        """
        Add a user phrase to the live prototype bank (or remove influence on failure).

        Called by intent_learner.record_route() after every command execution so
        the classifier adapts to *this* user's vocabulary over time.

        Parameters
        ----------
        phrase  : The raw user utterance.
        tool    : The tool that was used.
        success : Whether the tool call succeeded.
        """
        if not tool or not phrase:
            return

        # Only reinforce tools we know about
        if tool not in _PROTOTYPES and tool not in self._dynamic:
            return

        with self._lock:
            if success:
                # Avoid duplicating phrases already in static prototypes
                static = _PROTOTYPES.get(tool, [])
                dynamic = self._dynamic.get(tool, [])
                if phrase not in static and phrase not in dynamic:
                    # Embed and add to live vectors
                    try:
                        from skills import skill_embedder  # noqa: PLC0415

                        vec = skill_embedder.embed_text(phrase)
                        if vec:
                            if tool not in self._vectors:
                                self._vectors[tool] = []
                            self._vectors[tool].append(vec)
                            if tool not in self._dynamic:
                                self._dynamic[tool] = []
                            self._dynamic[tool].append(phrase)
                            logger.debug(
                                "intent_classifier: reinforced %s ← %r",
                                tool,
                                phrase[:60],
                            )
                    except Exception as exc:
                        logger.debug("intent_classifier.reinforce embed failed: %s", exc)
            else:
                # On failure: remove any dynamic phrase that matches this text
                # (don't touch static prototypes — they are ground truth)
                dynamic = self._dynamic.get(tool, [])
                if phrase in dynamic:
                    try:
                        idx = dynamic.index(phrase)
                        dynamic.pop(idx)
                        vecs = self._vectors.get(tool, [])
                        # Dynamic vecs start after static ones
                        static_count = len(_PROTOTYPES.get(tool, []))
                        dyn_idx = static_count + idx
                        if dyn_idx < len(vecs):
                            vecs.pop(dyn_idx)
                        logger.debug(
                            "intent_classifier: de-reinforced %s ← %r",
                            tool,
                            phrase[:60],
                        )
                    except Exception as exc:
                        logger.debug("intent_classifier.reinforce removal failed: %s", exc)

    @property
    def is_ready(self) -> bool:
        return self._ready

    def stats(self) -> dict:
        """Return diagnostic stats."""
        return {
            "ready": self._ready,
            "tools": list(self._vectors.keys()),
            "total_prototypes": sum(len(v) for v in self._vectors.values()),
            "dynamic_learned": sum(len(p) for p in self._dynamic.values()),
        }


# ── Module singleton ──────────────────────────────────────────────────────────

_classifier = SemanticIntentClassifier()
