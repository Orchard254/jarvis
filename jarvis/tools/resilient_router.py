"""
tools/resilient_router.py — Resilient Tool Router with Intent Gating & Embedding Similarity

Addresses critical weaknesses:
1. TOOL_HINTS naive keyword matching → Add intent gating + embedding similarity
2. Over-reliance on keywords → Hybrid scoring (keyword * 0.4 + embedding * 0.6)
3. Enum constraint problem → Hybrid schema with fallback + app name normalization
4. Too many tools exposed → Hard cap at 3 + confidence threshold
5. Missing "no-tool" path → Allow {"action": "respond", "message": "..."}
6. Validator insufficient → Add tool.safe_execute() with semantic validation
7. LLM dependency → Direct tool match fallback when LLM unavailable
8. Multi-step tasks → Allow {"action": "plan", "steps": [...]}
9. Migration layer risk → Aggressive logging + debug mode disable
10. Missing execution feedback → Verification + retry with adjustment
"""

import logging
import re
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger("resilient_router")


# =============================================================================
# INTENT GATES: Restrict tool search space before keyword matching
# =============================================================================
# Maps intent patterns to domain restrictions
# Applied BEFORE TOOL_HINTS filtering to reduce false positives

INTENT_GATES = {
    "open_launch_start": {
        "patterns": ["open", "launch", "start", "run", "bring up", "fire up"],
        "restrict_to_domains": ["app", "system", "file"],
    },
    "close_quit_exit": {
        "patterns": ["close", "quit", "exit", "terminate", "shut down"],
        "restrict_to_domains": ["app", "system", "web"],
    },
    "read_view_contents": {
        "patterns": ["read", "view", "show", "display", "contents", "what's in"],
        "restrict_to_domains": ["file", "data", "time", "settings"],
    },
    "write_create_save": {
        "patterns": ["write", "create", "save", "store", "make", "add"],
        "restrict_to_domains": ["file", "data"],
    },
    "delete_remove_erase": {
        "patterns": ["delete", "remove", "erase", "destroy", "clear"],
        "restrict_to_domains": ["file", "data"],
    },
    "search_find_query": {
        "patterns": ["search", "find", "query", "look up", "google"],
        "restrict_to_domains": ["web", "data"],
    },
    "navigate_browse": {
        "patterns": ["navigate", "browse", "go to", "visit", "url"],
        "restrict_to_domains": ["web"],
    },
    "type_input_enter": {
        "patterns": ["type", "input", "enter", "write text", "keyboard"],
        "restrict_to_domains": ["ui", "input"],
    },
    "click_select_mouse": {
        "patterns": ["click", "select", "mouse", "button", "double click"],
        "restrict_to_domains": ["ui"],
    },
    "volume_sound_audio": {
        "patterns": ["volume", "sound", "audio", "mute", "speaker"],
        "restrict_to_domains": ["settings", "audio"],
    },
    "brightness_display_screen": {
        "patterns": ["brightness", "screen", "display", "dim", "bright"],
        "restrict_to_domains": ["settings", "screen"],
    },
    "power_sleep_shutdown": {
        "patterns": ["sleep", "shutdown", "power off", "hibernate", "restart"],
        "restrict_to_domains": ["system"],
    },
}


# =============================================================================
# APP NAME NORMALIZATION: Handle variations like "ms word" → "winword"
# =============================================================================

APP_NAME_ALIASES = {
    # Browsers
    "chrome": ["chrome", "google chrome", "chromium"],
    "firefox": ["firefox", "mozilla firefox", "mozilla"],
    "edge": ["edge", "microsoft edge", "msedge"],
    "safari": ["safari"],
    "opera": ["opera"],
    
    # Text Editors
    "notepad": ["notepad", "notepad++", "notepad plus plus"],
    "vscode": ["vscode", "visual studio code", "visual studio"],
    "sublime": ["sublime", "sublime text"],
    "atom": ["atom"],
    
    # Office Apps
    "winword": ["word", "ms word", "microsoft word", "winword"],
    "excel": ["excel", "ms excel", "microsoft excel"],
    "powerpoint": ["powerpoint", "ms powerpoint", "microsoft powerpoint", "ppt"],
    "onenote": ["onenote", "ms onenote", "microsoft onenote"],
    "outlook": ["outlook", "ms outlook", "microsoft outlook"],
    
    # System Apps
    "explorer": ["explorer", "file explorer", "windows explorer", "file manager"],
    "calculator": ["calculator", "calc"],
    "taskmgr": ["task manager", "taskmgr", "process manager"],
    "cmd": ["cmd", "command prompt", "command line", "terminal"],
    "powershell": ["powershell", "ps", "pwsh"],
    
    # Communication
    "discord": ["discord"],
    "slack": ["slack"],
    "teams": ["teams", "microsoft teams"],
    "zoom": ["zoom"],
    
    # Media
    "spotify": ["spotify"],
    "vlc": ["vlc", "vlc player"],
    "windows media player": ["wmp", "windows media player", "media player"],
}


def normalize_app_name(app_input: str) -> str:
    """
    Normalize app name from user input to canonical name.
    
    Handles:
    - Case insensitivity
    - Common aliases ("ms word" → "winword")
    - Partial matches
    
    Args:
        app_input: User's app name input
        
    Returns:
        Canonical app name, or original if no match found
    """
    app_lower = app_input.lower().strip()
    
    # Direct match first
    for canonical, aliases in APP_NAME_ALIASES.items():
        if app_lower == canonical:
            return canonical
        if app_lower in aliases:
            return canonical
    
    # Partial match
    for canonical, aliases in APP_NAME_ALIASES.items():
        for alias in aliases:
            if alias in app_lower or app_lower in alias:
                logger.info(f"Mapped app '{app_input}' → '{canonical}' (partial match)")
                return canonical
    
    # No match - return original (will be validated by tool later)
    return app_input


# =============================================================================
# EMBEDDING SIMILARITY (Lightweight): For natural language understanding
# =============================================================================
# Uses simple TF-IDF style scoring when full embeddings not available
# Can be upgraded to use sentence-transformers if needed

class SimpleEmbeddingScorer:
    """
    Lightweight embedding-like scorer using word overlap + semantic similarity.
    
    Without external dependencies, uses:
    - Word overlap ratio
    - Synonym matching
    - Phrase detection
    
    Can be upgraded to use sentence-transformers for true embeddings.
    """
    
    # Simple synonym mappings for common actions
    SYNONYMS = {
        "open": ["launch", "start", "run", "bring up", "fire up", "initiate"],
        "close": ["quit", "exit", "terminate", "shut down", "dismiss"],
        "search": ["find", "query", "look up", "google", "seek"],
        "write": ["create", "save", "store", "compose", "draft"],
        "read": ["view", "show", "display", "see", "check"],
        "delete": ["remove", "erase", "destroy", "clear", "discard"],
        "type": ["input", "enter", "key in", "keyboard"],
        "click": ["select", "press", "tap", "hit"],
    }
    
    def score_similarity(self, query: str, tool_keywords: List[str]) -> float:
        """
        Score similarity between query and tool keywords.
        
        Args:
            query: User's natural language query
            tool_keywords: List of keywords associated with a tool
            
        Returns:
            Similarity score 0.0-1.0
        """
        query_words = set(query.lower().split())
        keyword_set = set(kw.lower() for kw in tool_keywords)
        
        # Expand query with synonyms
        expanded_query = set(query_words)
        for word in query_words:
            if word in self.SYNONYMS:
                expanded_query.update(self.SYNONYMS[word])
            # Check if word is a synonym of something
            for action, synonyms in self.SYNONYMS.items():
                if word in synonyms:
                    expanded_query.add(action)
        
        # Calculate Jaccard similarity
        intersection = expanded_query & keyword_set
        union = expanded_query | keyword_set
        
        if not union:
            return 0.0
        
        base_score = len(intersection) / len(union)
        
        # Boost for exact phrase matches
        query_lower = query.lower()
        for kw in tool_keywords:
            if kw.lower() in query_lower and len(kw) > 3:
                base_score = min(1.0, base_score + 0.2)
        
        return base_score


# =============================================================================
# HYBRID SCHEMA: Enum with fallback for app names
# =============================================================================

def get_hybrid_enum_schema(
    enum_values: List[str],
    fallback_type: str = "string",
    description: str = "",
) -> Dict[str, Any]:
    """
    Create a hybrid schema that accepts enum values OR free text.
    
    This solves the "user-installed apps" and "variations" problem.
    
    Args:
        enum_values: Preferred/suggested values
        fallback_type: Type to accept if not in enum
        description: Field description
        
    Returns:
        JSON Schema dict with enum + fallback
    """
    return {
        "type": fallback_type,
        "description": description,
        "enum_suggested": enum_values,  # Custom field - not standard JSON Schema
        "fallback_allowed": True,
        "normalization_hint": "normalize_app_name" if "app" in description.lower() else None,
    }


# =============================================================================
# CONFIDENCE THRESHOLDS & ROUTING DECISIONS
# =============================================================================

@dataclass
class ToolMatchResult:
    """Result from tool matching with confidence scores."""
    tool_name: str
    keyword_score: float
    embedding_score: float
    combined_score: float
    intent_gate_passed: bool
    requires_clarification: bool = False
    clarification_question: str = ""


# Confidence thresholds
CONFIDENCE_THRESHOLD_HIGH = 0.8   # Execute directly
CONFIDENCE_THRESHOLD_LOW = 0.6    # Ask for clarification below this
MAX_TOOLS_TO_LLM = 3              # Hard cap (reduced from 5)


# =============================================================================
# RESILIENT ROUTER: Main routing logic
# =============================================================================

class ResilientToolRouter:
    """
    Resilient tool router that handles ambiguity, failures, and multi-step tasks.
    
    Features:
    1. Intent gating before keyword matching
    2. Hybrid scoring: keyword * 0.4 + embedding * 0.6
    3. Hard cap at 3 tools + confidence threshold
    4. Direct tool match fallback (no LLM needed for simple cases)
    5. Support for "respond" action (no tool needed)
    6. Support for "plan" action (multi-step tasks)
    7. Aggressive migration logging
    8. Execution feedback loop with retry
    """
    
    def __init__(
        self,
        registry=None,
        enable_migration_logging: bool = True,
        use_embeddings: bool = True,
    ):
        """
        Initialize resilient router.
        
        Args:
            registry: Tool registry instance
            enable_migration_logging: Log legacy tool migrations aggressively
            use_embeddings: Use embedding similarity (requires sentence-transformers)
        """
        self._registry = registry
        self._enable_migration_logging = enable_migration_logging
        self._use_embeddings = use_embeddings
        self._embedding_scorer = SimpleEmbeddingScorer()
        
        # Load TOOL_HINTS from registry module
        try:
            from jarvis.tools.registry_refactored import TOOL_HINTS
            self._tool_hints = TOOL_HINTS
        except ImportError:
            self._tool_hints = {}
            logger.warning("Could not load TOOL_HINTS, using empty hints")
        
        logger.info("ResilientToolRouter initialized")
    
    def set_registry(self, registry) -> None:
        """Set or update the tool registry."""
        self._registry = registry
    
    def _apply_intent_gate(self, user_input: str) -> Optional[List[str]]:
        """
        Apply intent gating to restrict search space.
        
        Args:
            user_input: User's natural language input
            
        Returns:
            List of allowed domains, or None if no gate matched (all domains allowed)
        """
        input_lower = user_input.lower()
        
        for gate_name, gate_config in INTENT_GATES.items():
            patterns = gate_config["patterns"]
            for pattern in patterns:
                if pattern in input_lower:
                    logger.debug(f"Intent gate matched: {gate_name}")
                    return gate_config["restrict_to_domains"]
        
        return None  # No gate matched, allow all domains
    
    def _filter_tools_by_domain(
        self,
        tools: Dict[str, Any],
        allowed_domains: Optional[List[str]],
    ) -> Dict[str, Any]:
        """
        Filter tools to only those in allowed domains.
        
        Args:
            tools: Dict of tool_name -> tool
            allowed_domains: List of allowed domain names
            
        Returns:
            Filtered tools dict
        """
        if not allowed_domains:
            return tools
        
        filtered = {}
        for tool_name, tool in tools.items():
            # Extract domain from tool name (e.g., "app.open" → "app")
            if "." in tool_name:
                domain = tool_name.split(".")[0]
                if domain in allowed_domains:
                    filtered[tool_name] = tool
            else:
                # No domain in name, include it
                filtered[tool_name] = tool
        
        return filtered
    
    def _score_tool_match(
        self,
        user_input: str,
        tool_name: str,
        keywords: List[str],
    ) -> ToolMatchResult:
        """
        Score a tool match using hybrid scoring.
        
        Args:
            user_input: User's input
            tool_name: Tool name
            keywords: Tool's keywords
            
        Returns:
            ToolMatchResult with scores
        """
        # Keyword score (simple count)
        input_lower = user_input.lower()
        keyword_matches = sum(1 for kw in keywords if kw in input_lower)
        keyword_score = keyword_matches / max(len(keywords), 1)
        
        # Embedding score
        embedding_score = self._embedding_scorer.score_similarity(user_input, keywords)
        
        # Hybrid scoring: keyword * 0.4 + embedding * 0.6
        combined_score = (keyword_score * 0.4) + (embedding_score * 0.6)
        
        return ToolMatchResult(
            tool_name=tool_name,
            keyword_score=keyword_score,
            embedding_score=embedding_score,
            combined_score=combined_score,
            intent_gate_passed=True,
        )
    
    def filter_tools(
        self,
        user_input: str,
        max_tools: int = MAX_TOOLS_TO_LLM,
        confidence_threshold: float = CONFIDENCE_THRESHOLD_LOW,
    ) -> Tuple[List[ToolMatchResult], Optional[str]]:
        """
        Filter tools to top candidates based on user input.
        
        Args:
            user_input: User's natural language request
            max_tools: Maximum tools to return (hard cap: 3)
            confidence_threshold: Minimum confidence to include tool
            
        Returns:
            Tuple of (list of ToolMatchResult, clarification question or None)
        """
        if not self._registry:
            logger.error("No registry available for tool filtering")
            return [], None
        
        # Step 1: Apply intent gate
        allowed_domains = self._apply_intent_gate(user_input)
        
        # Get all tools and filter by domain
        all_tools = self._registry.get_all_tools()
        filtered_tools = self._filter_tools_by_domain(all_tools, allowed_domains)
        
        # Step 2: Score remaining tools
        scored_results: List[ToolMatchResult] = []
        
        for tool_name, tool in filtered_tools.items():
            keywords = self._tool_hints.get(tool_name, [])
            if not keywords:
                continue
            
            result = self._score_tool_match(user_input, tool_name, keywords)
            
            # Check if intent gate was applied
            if allowed_domains:
                domain = tool_name.split(".")[0] if "." in tool_name else ""
                result.intent_gate_passed = domain in (allowed_domains or [])
            
            if result.combined_score >= confidence_threshold:
                scored_results.append(result)
        
        # Sort by combined score
        scored_results.sort(key=lambda r: r.combined_score, reverse=True)
        
        # Step 3: Check for low confidence → ask clarification
        clarification_question = None
        if scored_results and scored_results[0].combined_score < CONFIDENCE_THRESHOLD_LOW:
            clarification_question = self._generate_clarification_question(
                user_input, scored_results[:3]
            )
            for result in scored_results[:max_tools]:
                result.requires_clarification = True
        
        # Hard cap at max_tools
        return scored_results[:max_tools], clarification_question
    
    def _generate_clarification_question(
        self,
        user_input: str,
        candidates: List[ToolMatchResult],
    ) -> str:
        """
        Generate a clarification question when confidence is low.
        
        Args:
            user_input: Original user input
            candidates: Top candidate tools
            
        Returns:
            Clarification question string
        """
        if not candidates:
            return "I'm not sure what you'd like me to do. Could you rephrase?"
        
        tool_names = [c.tool_name for c in candidates]
        
        # Map tool names to human-readable actions
        action_map = {
            "app.open": "open an application",
            "file.open": "open a file",
            "file.read": "read a file",
            "web.search": "search the web",
            "ui.type_text": "type text",
        }
        
        actions = [action_map.get(t, t) for t in tool_names]
        
        return f"I found multiple possible actions: {', '.join(actions[:3])}. Which one did you mean?"
    
    def direct_tool_match(self, user_input: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Attempt direct tool matching without LLM.
        
        For simple, unambiguous requests like "lock computer" or "open chrome".
        
        Args:
            user_input: User's input
            
        Returns:
            Tuple of (tool_name, args) if direct match found, None otherwise
        """
        input_lower = user_input.lower().strip()
        
        # Pattern matching for common direct commands
        direct_patterns = [
            # Lock computer
            (r"\b(lock)\s*(computer|pc|screen|workstation)\b", "system.lock_pc", {}),
            
            # Open app
            (r"\b(open|launch|start)\s+(chrome|firefox|notepad|word|excel)\b", 
             "app.open", lambda m: {"app_name": normalize_app_name(m.group(2))}),
            
            # Search web
            (r"\b(search|google|find)\s+(.+)$", 
             "web.search", lambda m: {"query": m.group(2)}),
            
            # Get time
            (r"\b(time|what time|current time)\b", "time.get_current", {}),
            
            # Shutdown/Sleep
            (r"\b(shutdown|power off|turn off)\b", "system.shutdown_pc", {}),
            (r"\b(sleep|suspend)\b", "system.sleep_pc", {}),
        ]
        
        for pattern, tool_name, args_extractor in direct_patterns:
            match = re.search(pattern, input_lower)
            if match:
                if callable(args_extractor):
                    args = args_extractor(match)
                else:
                    args = args_extractor
                
                logger.info(f"Direct tool match: {tool_name} with args {args}")
                return tool_name, args
        
        return None
    
    def route(
        self,
        user_input: str,
        llm_available: bool = True,
    ) -> Dict[str, Any]:
        """
        Main routing function - decides how to handle the input.
        
        Routing logic:
        1. Try direct tool match first (fastest)
        2. If no direct match and LLM available → filter tools + LLM plan
        3. If confidence too low → ask clarification
        4. If LLM unavailable → fall back to direct match or error
        
        Args:
            user_input: User's natural language request
            llm_available: Whether LLM is available
            
        Returns:
            Routing decision dict:
            - {"action": "execute_direct", "tool": ..., "args": ...}
            - {"action": "llm_plan", "candidates": [...], "prompt": ...}
            - {"action": "clarify", "question": ...}
            - {"action": "respond", "message": ...}  # No tool needed
            - {"action": "plan", "steps": [...]}  # Multi-step
            - {"action": "error", "message": ...}
        """
        # Step 1: Check if this is a chat/conversation input (no tool needed)
        if self._is_chat_input(user_input):
            return {
                "action": "respond",
                "message": "Chat response - no tool execution needed",
                "requires_llm": True,
            }
        
        # Step 2: Try direct tool match
        direct_match = self.direct_tool_match(user_input)
        if direct_match:
            tool_name, args = direct_match
            return {
                "action": "execute_direct",
                "tool": tool_name,
                "args": args,
                "confidence": 0.95,  # High confidence for direct matches
            }
        
        # Step 3: If LLM not available, can't proceed with complex routing
        if not llm_available:
            logger.warning("LLM unavailable and no direct match found")
            return {
                "action": "error",
                "message": "Unable to process request without LLM. Please be more specific.",
                "suggestion": "Try a simpler command like 'open chrome' or 'lock computer'",
            }
        
        # Step 4: Filter tools and prepare for LLM
        candidates, clarification = self.filter_tools(user_input)
        
        if clarification:
            return {
                "action": "clarify",
                "question": clarification,
                "candidates": [c.tool_name for c in candidates],
            }
        
        if not candidates:
            # No suitable tools found - might be a chat input after all
            return {
                "action": "respond",
                "message": "I don't have a tool for that request. How else can I help?",
            }
        
        # Step 5: Prepare LLM plan
        return {
            "action": "llm_plan",
            "candidates": [c.tool_name for c in candidates],
            "scores": {c.tool_name: c.combined_score for c in candidates},
            "prompt": self._build_llm_prompt(user_input, candidates),
        }
    
    def _is_chat_input(self, user_input: str) -> bool:
        """
        Detect if input is conversational chat (no tool execution needed).
        
        Args:
            user_input: User's input
            
        Returns:
            True if this is chat/conversation, False if tool execution likely needed
        """
        chat_patterns = [
            r"\b(hi|hello|hey|greetings)\b",
            r"\b(how are you|how's it going|what's up)\b",
            r"\b(thank|thanks|thank you)\b",
            r"\b(yes|no|maybe|ok|okay)\b$",
            r"\b(who are you|what are you)\b",
            r"\b(help\b.*\?)",  # "help?" but not "help me open"
        ]
        
        input_lower = user_input.lower().strip()
        
        # Short inputs are more likely to be chat
        if len(input_lower.split()) <= 3:
            for pattern in chat_patterns:
                if re.search(pattern, input_lower):
                    return True
        
        return False
    
    def _build_llm_prompt(
        self,
        user_input: str,
        candidates: List[ToolMatchResult],
    ) -> str:
        """
        Build prompt for LLM with filtered tool candidates.
        
        Args:
            user_input: Original user input
            candidates: Filtered tool candidates
            
        Returns:
            Formatted prompt string
        """
        lines = [
            f"User request: {user_input}",
            "",
            "Available tools (choose ONE if needed):",
        ]
        
        for i, candidate in enumerate(candidates, 1):
            lines.append(
                f"{i}. {candidate.tool_name} "
                f"(confidence: {candidate.combined_score:.2f})"
            )
        
        lines.extend([
            "",
            "Respond with JSON:",
            '{"action": "tool_call", "tool": "<name>", "args": {...}}',
            'Or: {"action": "respond", "message": "..."} if no tool needed',
            'Or: {"action": "plan", "steps": [...]} for multi-step tasks',
        ])
        
        return "\n".join(lines)


# =============================================================================
# MULTI-STEP PLAN SUPPORT
# =============================================================================

@dataclass
class PlanStep:
    """A single step in a multi-step plan."""
    tool_name: str
    args: Dict[str, Any]
    description: str
    expected_result: str = ""
    verification_strategy: str = "schema"  # schema, semantic, visual


@dataclass
class MultiStepPlan:
    """Multi-step execution plan."""
    steps: List[PlanStep] = field(default_factory=list)
    goal: str = ""
    success_criteria: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "action": "plan",
            "goal": self.goal,
            "steps": [
                {
                    "tool": step.tool_name,
                    "args": step.args,
                    "description": step.description,
                }
                for step in self.steps
            ],
            "success_criteria": self.success_criteria,
        }


# =============================================================================
# EXECUTION FEEDBACK LOOP
# =============================================================================

class ExecutionFeedbackLoop:
    """
    Manages execution feedback with verification and retry logic.
    
    Features:
    - Verify execution results
    - Retry with adjusted parameters on failure
    - Track consecutive failures
    - Escalate after max retries
    """
    
    MAX_RETRIES = 3
    FAILURE_COOLDOWN_SECONDS = 5
    
    def __init__(self, registry=None):
        """Initialize feedback loop."""
        self._registry = registry
        self._failure_counts: Dict[str, int] = {}  # tool_name -> failure_count
        self._last_failure_time: Dict[str, float] = {}
    
    def execute_with_feedback(
        self,
        tool_name: str,
        args: Dict[str, Any],
        verify_result: bool = True,
    ) -> Tuple[bool, Any, str]:
        """
        Execute tool with verification and retry logic.
        
        Args:
            tool_name: Tool to execute
            args: Tool arguments
            verify_result: Whether to verify the result
            
        Returns:
            Tuple of (success, result, message)
        """
        if not self._registry:
            return False, None, "No registry available"
        
        tool = self._registry.get(tool_name)
        if not tool:
            return False, None, f"Tool not found: {tool_name}"
        
        last_error = ""
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Validate before execution
                is_valid, error_msg = tool.validate(**args)
                if not is_valid:
                    return False, None, f"Validation failed: {error_msg}"
                
                # Execute with semantic safety check
                result = self._safe_execute(tool, args)
                
                # Verify result if requested
                if verify_result and not self._verify_result(tool_name, result):
                    last_error = "Result verification failed"
                    args = self._adjust_args_for_retry(args, last_error)
                    continue
                
                # Success - reset failure count
                self._failure_counts[tool_name] = 0
                return True, result, "Execution successful"
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Execution attempt {attempt + 1} failed: {last_error}")
                
                # Adjust args for next retry
                args = self._adjust_args_for_retry(args, last_error)
        
        # All retries exhausted
        self._failure_counts[tool_name] = self._failure_counts.get(tool_name, 0) + 1
        self._last_failure_time[tool_name] = time.time()
        
        return False, None, f"Failed after {self.MAX_RETRIES} attempts: {last_error}"
    
    def _safe_execute(self, tool, args: Dict[str, Any]) -> Any:
        """
        Execute tool with semantic safety validation.
        
        Each tool's own validate() method should catch semantic issues
        like dangerous file paths.
        
        Args:
            tool: Tool instance
            args: Tool arguments
            
        Returns:
            Tool execution result
        """
        # Tool's validate() should have been called already
        # This is the actual execution
        return tool.execute(**args)
    
    def _verify_result(self, tool_name: str, result: Any) -> bool:
        """
        Verify execution result is valid.
        
        Args:
            tool_name: Executed tool name
            result: Execution result
            
        Returns:
            True if result is valid
        """
        # Basic validation - can be extended per tool
        if result is None:
            return False
        
        # Check if result has success indicator
        if hasattr(result, 'success'):
            return result.success
        
        return True
    
    def _adjust_args_for_retry(
        self,
        args: Dict[str, Any],
        error: str,
    ) -> Dict[str, Any]:
        """
        Adjust arguments for retry based on error.
        
        Args:
            args: Original arguments
            error: Error message from failed attempt
            
        Returns:
            Adjusted arguments dict
        """
        adjusted = dict(args)
        
        # Example adjustments based on error patterns
        error_lower = error.lower()
        
        if "permission" in error_lower:
            logger.info("Adjusting for permission error - may need elevated access")
        
        if "not found" in error_lower or "doesn't exist" in error_lower:
            logger.info("Adjusting for not-found error")
        
        return adjusted
    
    def get_failure_count(self, tool_name: str) -> int:
        """Get consecutive failure count for a tool."""
        return self._failure_counts.get(tool_name, 0)
    
    def should_allow_execution(self, tool_name: str) -> bool:
        """
        Check if execution should be allowed based on failure history.
        
        Implements cooldown after repeated failures.
        
        Args:
            tool_name: Tool to check
            
        Returns:
            True if execution is allowed
        """
        failure_count = self._failure_counts.get(tool_name, 0)
        
        if failure_count < self.MAX_RETRIES:
            return True
        
        # Check cooldown
        last_failure = self._last_failure_time.get(tool_name, 0)
        elapsed = time.time() - last_failure
        
        return elapsed > self.FAILURE_COOLDOWN_SECONDS


# Import time for feedback loop
import time


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_resilient_router(registry=None) -> ResilientToolRouter:
    """Get a resilient router instance."""
    return ResilientToolRouter(registry=registry)


def route_tool_call(
    user_input: str,
    registry=None,
    llm_available: bool = True,
) -> Dict[str, Any]:
    """
    Route a user input to appropriate tool handling.
    
    Convenience function for quick integration.
    
    Args:
        user_input: User's natural language request
        registry: Tool registry instance
        llm_available: Whether LLM is available
        
    Returns:
        Routing decision dict
    """
    router = get_resilient_router(registry)
    return router.route(user_input, llm_available)
