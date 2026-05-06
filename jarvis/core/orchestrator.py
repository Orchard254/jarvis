"""
Main Orchestrator Module

The central coordinator for JARVIS that:
- Manages the main event loop
- Coordinates perception, reasoning, and execution
- Handles voice input/output
- Manages system state and modes
- Implements full pipeline: listen → transcribe → classify → retrieve → 
  select strategy → plan if complex → critic review → execute → reflect → store → respond

ARCHITECTURAL NOTES (from abandoned patches):
=============================================
The following concepts were explored in prototype patches but not integrated:

1. DETERMINISTIC TOOL SELECTION FLOW (orchestrator_patch.py):
   Proposed flow: Input → Tool Hint Filter → LLM (with 3-5 tools) → Structured JSON Parse → 
                  Validation → Execution
   This would replace: Input → All Tools → LLM → TOOL: pattern parse → Execute
   
   Key ideas:
   - Filter tools BEFORE sending to LLM based on intent hints (reduce context, improve determinism)
   - Use strict JSON output format instead of TOOL: pattern matching
   - Validate tool calls with schema + semantic validation before execution
   - Defense-in-depth: double-check validation right before execution
   
   Why not integrated: Current ReAct agent and tool parser already handle dynamic tool selection
   effectively. The existing tool_registry.filter_tools() provides similar hint-based filtering.

2. RESILIENT TOOL ROUTING (orchestrator_resilient_patch.py):
   Proposed flow: Input → Intent Detection → Direct Match? → Yes → Execute
                                              ↓ No
                                        LLM Available? → No → Error/Retry
                                              ↓ Yes
                                        Filter Tools (Intent Gate + Embedding)
                                              ↓
                                        Confidence Check → Low → Ask Clarification
                                              ↓ High
                                        LLM Plan with 3 tools max
                                              ↓
                                        Parse JSON (tool_call/respond/plan)
                                              ↓
                                        Validate (schema + semantic)
                                              ↓
                                        Execute with Feedback Loop
                                              ↓
                                        Verify Result → Fail → Retry (max 3)
                                              ↓ Success
                                        Respond
   
   Key ideas:
   - Fast path for direct tool matches without LLM invocation
   - Confidence-based clarification requests when intent is unclear
   - Multi-step plan execution with verification at each step
   - Retry logic with feedback loops for failed executions
   - Graceful degradation when LLM is unavailable
   
   Why not integrated: Current architecture handles these concerns through:
   - IntentClassifier for intent detection
   - StrategySelector for complexity-based routing
   - TaskExecutor with built-in verification strategies
   - ReActAgent with MAX_AGENT_ROUNDS for retry/failure handling
"""

import logging
import threading
import hashlib
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import queue
import textwrap
import sys
import re

# Fix UTF-8 logging on Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 workaround
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

from jarvis.core.memory import CoreMemory
from jarvis.core.context import ContextAssembler
from jarvis.core.brain import Brain
from jarvis.core.react_agent import ReActAgent
from jarvis.core.predictive_planner import PredictivePlanner
from jarvis.core.intent_scorer import AdaptiveIntentScorer
from jarvis.core.tool_parser import is_tool_call, parse_tool_call, validate_tool_call_schema
from jarvis.execution.task_executor import TaskExecutor, TaskStep, VerificationStrategy
from jarvis.tools.registry import ToolRegistry
from jarvis.skills.registry import SkillsRegistry as SkillRegistry
from jarvis.safety import InputFilter, PlanValidator, ToolGuard, AuditLog
from jarvis.perception.intent_classifier import IntentClassifier
from jarvis.perception.vision import VisionAnalyzer
from jarvis.reasoning.planner import TaskPlanner
from jarvis.reasoning.critic import PlanCritic, CriticDecision
from jarvis.reasoning.reflector import Reflector as OutcomeReflector
from jarvis.reasoning.strategy_selector import StrategySelector, TaskComplexity
from jarvis.reasoning.evaluator import PathEvaluator, get_evaluator
from jarvis.core.tot_engine import TreeOfThoughtsEngine
from jarvis.monitoring.ambient import get_ambient_monitor, start_monitoring
from jarvis.config.config import get_config
from jarvis.memory.persistent import PersistentMemory
from jarvis.security.vault import CredentialVault

# Constants
MAX_AGENT_ROUNDS = 8
MAX_CONSECUTIVE_FAILURES = 3
CACHE_TTL_SECONDS = 5

logger = logging.getLogger(__name__)


# Intent threshold constant - minimum score to execute actions
INTENT_THRESHOLD = 60  # Max-based scoring is more reliable than averaged scoring


def _safe_log(message: str, max_length: int = 500) -> str:
    """
    Sanitize a string for safe logging on Windows console.
    
    Replaces non-ASCII characters that cause UnicodeEncodeError with
    ASCII-safe equivalents or removes them entirely.
    
    Args:
        message: The message to sanitize
        max_length: Maximum length to truncate to
        
    Returns:
        Safe string for logging
    """
    if not message:
        return ''
    
    # Truncate if too long
    if len(message) > max_length:
        message = message[:max_length] + '...'
    
    # Replace common problematic Unicode characters with ASCII equivalents
    replacements = {
        '\u202f': ' ',      # Narrow no-break space
        '\u2011': '-',      # Non-breaking hyphen
        '\u2013': '-',      # En dash
        '\u2014': '--',     # Em dash
        '\u2018': "'",      # Left single quotation mark
        '\u2019': "'",      # Right single quotation mark
        '\u201c': '"',      # Left double quotation mark
        '\u201d': '"',      # Right double quotation mark
        '\u2026': '...',    # Horizontal ellipsis
        '\u00a0': ' ',      # No-break space
        '\u00ad': '',       # Soft hyphen (remove)
    }
    
    for unicode_char, ascii_replacement in replacements.items():
        message = message.replace(unicode_char, ascii_replacement)
    
    # Encode to ASCII, replace any remaining non-ASCII chars, then decode back
    try:
        message = message.encode('ascii', errors='replace').decode('ascii')
    except Exception:
        # Fallback: just remove all non-ASCII
        message = ''.join(char if ord(char) < 128 else '?' for char in message)
    
    return message


class TTSManager:
    """Simple TTS wrapper that delegates to the existing tts module."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize TTS manager."""
        self.config = config
        # Default to False to avoid warnings when voice is not explicitly enabled
        self.enabled = config.get('tts_enabled', False) or config.get('voice_enabled', False)
        
    def speak(self, text: str) -> None:
        """
        Speak text using TTS.
        
        Args:
            text: Text to speak
        """
        # Skip empty or whitespace-only text to avoid blank output
        if not text or not text.strip():
            return
            
        if not self.enabled:
            return
            
        try:
            # Import here to avoid circular imports
            from jarvis.output.tts import speak as tts_speak
            tts_speak(text)
        except (ImportError, Exception) as e:
            logger.debug(f"TTS not available: {e}")


def get_system_prompt(mode: str = 'agent', **kwargs) -> str:
    """Get the system prompt for JARVIS."""
    from jarvis.config.prompts.jarvis_prompt import get_system_prompt as build_prompt
    return build_prompt(mode, **kwargs)


class Orchestrator:
    """
    Main orchestrator for JARVIS.
    
    Coordinates all subsystems to provide a cohesive AI assistant experience.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the orchestrator.
        
        Args:
            config: Configuration dict
        """
        self.config = config
        self.running = False
        self.mode = 'unified'  # Unified mode - LLM decides everything
        self.current_task = None
        
        # Initialize core components
        logger.info("Initializing JARVIS orchestrator...")
        
        # Tool registry (singleton, doesn't take config)
        self.tool_registry = ToolRegistry.get_instance()
        self.tool_registry.load_all_tools()
        
        # Skill registry
        self.skill_registry = SkillRegistry()
        self.skill_registry.initialize()
        
        # Safety systems - Phase 3 Integration
        self.input_filter = InputFilter()
        self.plan_validator = PlanValidator()
        self.plan_validator.tool_registry = self.tool_registry
        self.tool_guard = ToolGuard(registry=self.tool_registry)  # FIX #1: Pass registry reference
        self.audit_log = AuditLog()
        
        # Memory system
        self.memory = CoreMemory(config)
        
        # Persistent memory with RAG (new)
        self.persistent_memory = PersistentMemory()
        
        # Credential vault (new)
        self.vault = CredentialVault()
        
        # Context assembler
        self.context_assembler = ContextAssembler(
            config=config,
            memory_system=self.memory,
            tool_registry=self.tool_registry,
            skill_registry=self.skill_registry,
            get_app_context=self.get_app_context  # Pass callback for app context
        )
        
        # Brain (LLM coordinator)
        self.brain = Brain(config, self.tool_registry)
        self.brain.set_callbacks(
            on_tool_call=self._on_tool_call,
            on_thinking=self._on_thinking
        )
        
        # ReAct Agent for autonomous multi-step tasks with vault access
        self.react_agent = ReActAgent(
            brain=self.brain,
            tool_registry=self.tool_registry,
            max_iterations=50,  # Increased for complex web browsing tasks
            vault=self.vault
        )
        
        # Predictive Planner - uses LLM's internal knowledge for fast execution
        self.predictive_planner = PredictivePlanner(self.brain)
        
        # Adaptive Intent Scorer - learns and scores intents for chat/agent routing
        self.intent_scorer = AdaptiveIntentScorer()
        
        # Perception
        self.intent_classifier = IntentClassifier(self.brain.client)
        self.vision_analyzer = VisionAnalyzer(self.brain.client)
        
        # Initialize vision analyzer for screen analysis tools
        from jarvis.perception.vision import get_vision_analyzer
        get_vision_analyzer(self.brain.client)
        
        # Reasoning - Tree of Thoughts Integration
        # Initialize ToT engine for multi-path strategic planning
        self.tot_engine = TreeOfThoughtsEngine(
            llm_interface=self.brain.client,
            max_depth=5,
            beam_width=3,
            max_branches=4
        )
        
        # Initialize Path Evaluator for scoring reasoning paths
        self.path_evaluator = PathEvaluator(llm_interface=self.brain.client)
        
        # Initialize Planner with ToT support
        self.planner = TaskPlanner(
            ollama_client=self.brain.client,
            tool_registry=self.tool_registry,
            tot_engine=self.tot_engine,
            path_evaluator=self.path_evaluator
        )
        
        self.critic = PlanCritic(ollama_client=self.brain.client)
        self.reflector = OutcomeReflector(ollama_client=self.brain.client, memory_manager=self.memory)
        self.strategy_selector = StrategySelector()
        
        # Output
        self.tts = TTSManager(config)
        
        # Task Executor for Plan-Execute-Verify loop (with visual verification disabled by default)
        # use_separate_process=False to allow web tools to share browser state
        self.task_executor = TaskExecutor(enable_visual_verification=False, use_separate_process=False)
        
        # Action Memory for loop prevention (tracks last 50 actions within 60 seconds)
        self._action_memory: Dict[str, float] = {}  # action_hash -> timestamp
        
        # State
        self.state = {
            'initialized_at': datetime.now().isoformat(),
            'total_interactions': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'current_activity': 'idle'
        }
        
        # Failure tracking for consecutive failures
        self._consecutive_failures = 0
        self._failure_cache: Dict[str, int] = {}  # task_hash -> failure_count
        
        # Context awareness - track recent results and failed actions
        self._recent_results: List[Dict[str, Any]] = []  # Last 20 successful results
        self._failed_actions: List[Dict[str, Any]] = []  # Last 10 failed actions
        self._max_recent_results = 20
        self._max_failed_actions = 10
        
        # User activity tracking for idle monitor (FIX #S)
        self._last_user_activity = time.time()

        # App context tracking - track which apps are active for context-aware operations
        self._last_active_app: Optional[str] = None
        self._app_switch_history: List[Dict[str, Any]] = []  # Last 10 app switches
        self._max_app_history = 10
        self._last_app_check_time: float = 0
        self._app_check_interval: float = 2.0  # Check active app every 2 seconds
        self._last_activity_time: float = time.time()  # FIX #9: Track real idle time
        
        # Abort mechanism
        self._abort_flag = threading.Event()
        self._abort_queue = queue.Queue()
        
        # Threads
        self.input_thread = None
        self.monitoring_thread = None
        self.ambient_monitors: List[threading.Thread] = []
        
        logger.info("JARVIS orchestrator initialized successfully")
    
    def start(self) -> None:
        """Start the orchestrator main loop."""
        if self.running:
            logger.warning("Orchestrator already running")
            return
        
        self.running = True
        self._abort_flag.clear()
        logger.info("Starting JARVIS orchestrator...")
        
        # Start ambient monitoring daemons (all 4 monitors)
        self._start_ambient_monitors()
        
        # Speak startup message
        self._speak("JARVIS online. Ready to assist.")
        
        # Start main interaction loop
        self._interaction_loop()
    
    def _start_ambient_monitors(self) -> None:
        """Start all 4 ambient monitor daemon threads: battery, resource, idle, timer."""
        # Start the main ambient monitor
        start_monitoring()
        
        # Battery monitor thread
        battery_thread = threading.Thread(target=self._battery_monitor_loop, daemon=True)
        battery_thread.start()
        self.ambient_monitors.append(battery_thread)
        
        # Resource monitor thread  
        resource_thread = threading.Thread(target=self._resource_monitor_loop, daemon=True)
        resource_thread.start()
        self.ambient_monitors.append(resource_thread)
        
        # Idle monitor thread
        idle_thread = threading.Thread(target=self._idle_monitor_loop, daemon=True)
        idle_thread.start()
        self.ambient_monitors.append(idle_thread)
        
        # FIX #10: Timer monitor removed — was a no-op burning a thread.
        # Re-add when actual timer/scheduler logic is implemented.
        
        # App context monitor thread (NEW)
        app_monitor_thread = threading.Thread(target=self._app_context_monitor_loop, daemon=True)
        app_monitor_thread.start()
        self.ambient_monitors.append(app_monitor_thread)
        
        logger.info(f"Started {len(self.ambient_monitors)} ambient monitor threads")
    
    def _battery_monitor_loop(self) -> None:
        """Monitor battery status in background."""
        import psutil
        while self.running:
            try:
                battery = psutil.sensors_battery()
                if battery:
                    percent = battery.percent
                    charging = battery.power_plugged
                    if percent < 20 and not charging:
                        logger.warning(f"Battery low: {percent}%")
                    elif percent < 5:
                        logger.critical(f"Battery critical: {percent}%")
            except Exception as e:
                logger.debug(f"Battery monitor error: {e}")
            time.sleep(30)  # Check every 30 seconds
    
    def _resource_monitor_loop(self) -> None:
        """Monitor CPU/memory resources in background."""
        import psutil
        while self.running:
            try:
                cpu = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory().percent
                if cpu > 90:
                    logger.warning(f"CPU critical: {cpu}%")
                elif cpu > 80:
                    logger.info(f"CPU high: {cpu}%")
                if memory > 90:
                    logger.warning(f"Memory critical: {memory}%")
            except Exception as e:
                logger.debug(f"Resource monitor error: {e}")
            time.sleep(10)  # Check every 10 seconds
    
    def _idle_monitor_loop(self) -> None:
        """Monitor user idle time in background. FIX #9: track real activity from process_command."""
        while self.running:
            try:
                idle_time = time.time() - self._last_user_activity
                if idle_time > 300:  # 5 minutes
                    logger.debug(f"User idle for {idle_time:.0f} seconds")
            except Exception as e:
                logger.debug(f"Idle monitor error: {e}")
            time.sleep(60)  # Check every minute
    
    def _timer_monitor_loop(self) -> None:
        """Monitor timers and scheduled tasks in background. FIX #T: Check jarvis_data/timers/ for expired timers."""
        import json
        from pathlib import Path
        timer_dir = Path('jarvis_data/timers')
        timer_dir.mkdir(parents=True, exist_ok=True)
        while self.running:
            try:
                now = time.time()
                for timer_file in timer_dir.glob('*.json'):
                    try:
                        data = json.loads(timer_file.read_text())
                        if now >= data.get('trigger_at', float('inf')):
                            msg = data.get('message', 'Timer complete')
                            self._speak(msg)
                            timer_file.unlink()
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Timer monitor error: {e}")
            time.sleep(5)  # Check every 5 seconds
    
    def _app_context_monitor_loop(self) -> None:
        """Monitor and update app context in background."""
        while self.running:
            try:
                self._update_app_context()
            except Exception as e:
                logger.debug(f"App context monitor error: {e}")
            time.sleep(2)  # Check every 2 seconds
    
    def check_abort(self) -> bool:
        """Check if abort was requested (wake word spoken during execution)."""
        if not self._abort_queue.empty():
            self._abort_flag.set()
            logger.info("Abort requested by user")
            return True
        return self._abort_flag.is_set()
    
    def request_abort(self) -> None:
        """Request abortion of current task (called when wake word detected)."""
        self._abort_queue.put(True)
        logger.info("Abort request queued")
    
    def clear_abort(self) -> None:
        """Clear abort flag for next task."""
        self._abort_flag.clear()
        # Drain the queue
        while not self._abort_queue.empty():
            try:
                self._abort_queue.get_nowait()
            except queue.Empty:
                break
    
    def stop(self) -> None:
        """Stop the orchestrator."""
        self.running = False
        logger.info("Stopping JARVIS orchestrator...")
        
        # Speak shutdown message
        self._speak("Shutting down. Goodbye.")
        
        # End current session
        self.memory.end_current_session(summary="User initiated shutdown")
        
        # Log final stats
        logger.info(f"Final stats: {self.state}")
    
    def process_command(self, command: str, voice: bool = False) -> Dict[str, Any]:
        """
        Process a user command.
        
        Args:
            command: The user's command text
            voice: Whether this came from voice input
            
        Returns:
            Result dict with success status and response
        """
        if not self.running:
            return {
                'success': False,
                'error': 'Orchestrator not running',
                'response': None
            }
        
        start_time = time.time()
        self.state['current_activity'] = 'processing_command'
        self._last_activity_time = time.time()  # FIX #9: Record activity
        self._last_user_activity = time.time()  # FIX #S: Update user activity timestamp
        
        try:
            # Update app context tracking
            self._update_app_context()
            
            # Phase 3 Safety: Input filtering (first safety layer)
            filter_result = self.input_filter.check(command)
            if not filter_result.is_safe:
                logger.warning(f"Input blocked by filter: {filter_result.reason}")
                self.audit_log.log_security_event(
                    event_type='input_blocked',
                    details={
                        'reason': filter_result.reason,
                        'blocked_patterns': filter_result.blocked_patterns,
                        'original_input_length': len(command)
                    }
                )
                return {
                    'success': False,
                    'error': 'Input blocked by safety filter',
                    'response': f"I cannot process that request: {filter_result.reason}",
                    'safety_blocked': True
                }
            
            # Use sanitized input
            command = filter_result.sanitized_input
            
            # Classify intent using adaptive scoring system
            # Get context for scoring
            app_ctx = self.get_app_context()
            context = {
                'active_app': app_ctx.get('current_app') or app_ctx.get('last_active_app'),
                'last_active_app': app_ctx.get('last_active_app'),
                'recent_commands': self.intent_scorer.context_window[-5:] if hasattr(self, 'intent_scorer') else [],
                'current_mode': self.mode
            }
            
            # Use adaptive intent scorer for continuous scoring
            intent_analysis = self.intent_scorer.analyze_and_score(command, context)
            intent_score = intent_analysis['score']
            recommended_mode = intent_analysis['mode']
            
            logger.info(f"Intent score: {intent_score}/100 - {intent_analysis['reasoning']}")
            
            # Intent threshold gate - below this score, only allow chat responses
            if intent_score < INTENT_THRESHOLD:
                logger.info(f"Intent score ({intent_score}) below threshold ({INTENT_THRESHOLD}), treating as chat")
                # Force chat mode - no tool execution allowed
                result = self._handle_chat_only(command)
            else:
                # Detect multi-step commands and route appropriately
                is_multi_step = self._is_multi_step_command(command)
                if is_multi_step:
                    logger.info(f"Multi-step command detected, routing to predictive planner: {command[:50]}...")
                    result = self._handle_agent_mode(command)
                else:
                    # Single-step command, use unified loop
                    result = self._handle_unified_mode(command, intent_analysis)
            
            # Update state
            self.state['total_interactions'] += 1
            if result.get('success'):
                self.state['successful_tasks'] += 1
            else:
                self.state['failed_tasks'] += 1
            
            # Store experience only for significant tasks (not simple chat)
            if result.get('mode') in ['unified', 'agent'] and result.get('actions'):
                self.memory.store_experience(
                    goal=command,
                    actions=result.get('actions', []),
                    outcome=result.get('response', ''),
                    success=result.get('success', False)
                )
                
                # Also store in persistent memory with RAG
                try:
                    self.persistent_memory.add_experience(
                        user_input=command,
                        assistant_response=result.get('response', ''),
                        context={
                            'success': result.get('success', False),
                            'actions_count': len(result.get('actions', [])),
                            'mode': result.get('mode', 'unified')
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to store in persistent memory: {e}")
            
            # Audit log
            self.audit_log.log_action(
                action_type='user_command',
                details={
                    'command': command,
                    'mode': result.get('mode', 'unified'),
                    'intent': intent_analysis,
                    'result': result.get('success', False),
                    'duration_ms': int((time.time() - start_time) * 1000)
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing command: {e}", exc_info=True)
            error_response = "I encountered an error processing your request."
            self._speak(error_response)
            
            return {
                'success': False,
                'error': str(e),
                'response': error_response
            }
        finally:
            self.state['current_activity'] = 'idle'
    
    def _handle_chat_only(self, command: str) -> Dict[str, Any]:
        """
        Handle low-intent commands as chat-only (no tool execution).
        
        This is called when intent score falls below INTENT_THRESHOLD.
        Prevents accidental tool execution on ambiguous inputs.
        
        Args:
            command: User command
            
        Returns:
            Result dict with chat response only
        """
        from jarvis.core.brain import Brain
        from jarvis.profile.user_profile import get_profile_manager
        
        # FIX: Extract user information from chat (name, preferences, etc.)
        self._extract_user_info_from_chat(command)
        
        # Simple LLM call for chat response - no tool execution allowed
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant. Respond naturally to the user. Do NOT use any tools - this is a chat-only conversation."},
                {"role": "user", "content": command}
            ]
            
            response = self.brain.chat(messages, temperature=0.7)
            
            if isinstance(response, dict):
                final_response = response.get('content', str(response))
            else:
                final_response = str(response)
            
            # FIX: Ensure response is not JSON structured data leaking into chat
            # If response looks like a structured plan/JSON, extract just the natural language part
            if final_response and isinstance(final_response, str) and final_response.strip().startswith('{'):
                try:
                    import json as json_module
                    parsed = json_module.loads(final_response.strip())
                    # If it's a structured response, extract the goal or provide a generic response
                    if isinstance(parsed, dict):
                        # Check if this is a clarification request that leaked through
                        if parsed.get('needs_clarification', False):
                            goal = parsed.get('goal', 'your request')
                            corrections = parsed.get('corrections', [])
                            final_response = f"I need more information about: {goal}"
                            if corrections:
                                final_response += f" ({', '.join(corrections)})"
                            final_response += " Could you clarify?"
                        elif parsed.get('goal'):
                            final_response = parsed.get('goal', final_response)
                        else:
                            # Fallback to generic response
                            final_response = "I understand. How can I help you further?"
                except (json_module.JSONDecodeError, Exception):
                    # If parsing fails, keep original response
                    pass
            
            # Speak response
            self._speak(final_response)
            
            return {
                'success': True,
                'response': final_response,
                'mode': 'chat',
                'actions': [],
                'iterations': 1
            }
            
        except Exception as e:
            logger.error(f"Chat handling error: {e}", exc_info=True)
            return {
                'success': False,
                'response': "I'm not sure I understand. Could you rephrase that?",
                'mode': 'chat',
                'actions': []
            }
    
    def _extract_user_info_from_chat(self, command: str) -> None:
        """
        Extract user information from chat messages and store in profile.
        
        Handles patterns like:
        - "my name is X"
        - "I am X"
        - "call me X"
        - "my email is X"
        - etc.
        
        Args:
            command: User chat message
        """
        import re
        from jarvis.profile.user_profile import get_profile_manager
        
        command_lower = command.lower().strip()
        
        # Patterns to extract user information
        patterns = {
            'name': [
                r'\bmy\s+name\s+is\s+(\w+)\b',
                r'\bi\s+am\s+(\w+)\b',
                r'\bcall\s+me\s+(\w+)\b',
                r"\bi'?m\s+(\w+)\b",
            ],
            'email': [
                r'\bmy\s+email\s+is\s+([^\s]+@[^\s]+)\b',
                r'\bmy\s+e-mail\s+is\s+([^\s]+@[^\s]+)\b',
            ],
            'location': [
                r'\bi\s+live\s+in\s+([^\.,]+)',
                r'\bi\s+am\s+from\s+([^\.,]+)',
                r'\bmy\s+location\s+is\s+([^\.,]+)',
            ],
        }
        
        profile_manager = get_profile_manager()
        updates_made = {}
        
        # Check each pattern type
        for info_type, regex_list in patterns.items():
            for pattern in regex_list:
                match = re.search(pattern, command_lower)
                if match:
                    value = match.group(1).strip()
                    # Capitalize names properly
                    if info_type == 'name':
                        value = value.capitalize()
                    
                    # Store in profile
                    if info_type == 'name':
                        profile_manager.update_context(name=value)
                        updates_made['name'] = value
                        logger.info(f"Extracted user name from chat: {value}")
                    elif info_type == 'email':
                        # Store in notes for now (could add dedicated field)
                        profile_manager.add_note(f"Email: {value}")
                        updates_made['email'] = value
                        logger.info(f"Extracted user email from chat: {value}")
                    elif info_type == 'location':
                        profile_manager.update_context(location=value.title())
                        updates_made['location'] = value
                        logger.info(f"Extracted user location from chat: {value}")
                    break
        
        # If we extracted information, acknowledge it
        if updates_made:
            logger.info(f"Updated user profile with: {updates_made}")
    
    def _handle_unified_mode(self, command: str, intent_analysis: Dict) -> Dict[str, Any]:
        """
        Single-loop LLM system with strict JSON output (FINAL or TOOL).
        
        Every LLM response must be valid JSON with either:
        - {"type": "TOOL", "tool": "...", "params": {...}, "thought": "..."}
        - {"type": "FINAL", "response": "...", "thought": "..."}
        
        Tools are executed in-loop immediately after validation.
        Text responses only occur when type=FINAL.
        
        Args:
            command: User command
            intent_analysis: Analysis result from intent scorer (used for learning only)
            
        Returns:
            Response dict
        """
        logger.info(f"Handling in unified loop mode: {command[:50]}...")
        
        # Clear abort flag for new task
        self.clear_abort()
        
        # Build system prompt for strict JSON output
        tools_json = self._build_tools_json()
        system_prompt = self._build_single_loop_prompt(tools_json)
        
        # Initialize conversation state
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": command}
        ]
        
        max_iterations = 15
        iteration = 0
        tool_calls = []
        final_response = None
        
        while iteration < max_iterations:
            iteration += 1
            
            # Check for abort
            if self.check_abort():
                return {
                    'success': False,
                    'response': "Task aborted by user.",
                    'mode': 'unified',
                    'actions': tool_calls
                }
            
            # Get LLM response
            try:
                llm_response = self.brain.chat(
                    messages=messages,
                    temperature=0.1,  # Low temp for consistent JSON
                    stream=False,
                    include_tools=False  # Disable tool calling - we handle JSON parsing manually
                )
                
                assistant_message = llm_response.get('content', '')
                
                # Debug: Log the raw response
                logger.debug(f"LLM raw response: {assistant_message[:200]}...")
                
                # Parse response for tool calls or final answer using new parser
                parsed = self._parse_natural_response(assistant_message)
                if not parsed:
                    logger.warning(f"Could not parse response: '{assistant_message}' (length: {len(assistant_message)})")
                    # Could not parse - ask LLM to clarify and remind about single tool rule
                    messages.append({"role": "user", "content": f"I didn't understand your response: '{assistant_message[:100]}...'. Remember: output ONLY ONE tool call per response using 'TOOL: tool_name(params)' format, or give a final answer. Never multiple tools at once."})
                    continue
                
                action_type = parsed.get('type', '').upper()
                
                if action_type == 'TOOL':
                    # Execute tool immediately using the new _execute_action method
                    tool_call_dict = {
                        "type": "tool",
                        "name": parsed.get('tool'),
                        "args": parsed.get('params', {}),
                        "thought": parsed.get('thought', '')
                    }
                    
                    # Log raw LLM output (sanitized for Windows console)
                    logger.info(f"[LLM] Raw output: {_safe_log(assistant_message[:200])}...")
                    
                    # Use the structured execution pipeline
                    exec_result = self._execute_action(tool_call_dict)
                    
                    tool_name = tool_call_dict['name']
                    params = tool_call_dict['args']
                    tool_result = exec_result['output']
                    thought = tool_call_dict.get('thought', '')
                    
                    # Record tool call
                    tool_calls.append({
                        'tool': tool_name,
                        'params': params,
                        'result': tool_result,
                        'thought': thought
                    })
                    
                    # Add assistant message and tool result to conversation
                    messages.append({"role": "assistant", "content": assistant_message})
                    messages.append({
                        "role": "user", 
                        "content": f"Tool '{tool_name}' returned: {tool_result}. Continue with next step or provide final response."
                    })
                    
                elif action_type == 'FINAL':
                    # Final response - exit loop
                    final_response = parsed.get('response', assistant_message)
                    thought = parsed.get('thought', '')
                    
                    logger.info(f"Final response generated after {iteration} iterations")
                    
                    # Learn from successful execution if tools were used
                    if tool_calls:
                        self.intent_scorer.learn_from_interaction(command, executed=True)
                    
                    # Speak response
                    self._speak(final_response)
                    
                    return {
                        'success': True,
                        'response': final_response,
                        'mode': 'unified',
                        'actions': tool_calls,
                        'iterations': iteration
                    }
                else:
                    # Unknown action type or natural response - treat as final
                    logger.info(f"Treating as final response: {assistant_message[:50]}...")
                    final_response = assistant_message
                    
                    # Learn from successful execution if tools were used
                    if tool_calls:
                        self.intent_scorer.learn_from_interaction(command, executed=True)
                    
                    # Speak response
                    self._speak(final_response)
                    
                    return {
                        'success': True,
                        'response': final_response,
                        'mode': 'unified',
                        'actions': tool_calls,
                        'iterations': iteration
                    }
                    
            except Exception as e:
                logger.error(f"LLM iteration error: {e}", exc_info=True)
                messages.append({"role": "user", "content": f"Error occurred: {str(e)}. Please try again."})
        
        # Max iterations reached
        logger.warning(f"Max iterations ({max_iterations}) reached")
        return {
            'success': False,
            'response': final_response or "I couldn't complete this task within the maximum number of steps.",
            'mode': 'unified',
            'actions': tool_calls
        }
    
    def _build_tools_json(self) -> str:
        """Build JSON schema of available tools for the LLM."""
        tools_list = []
        for name, tool in self.tool_registry.get_all_tools().items():
            tools_list.append({
                'name': name,
                'description': getattr(tool, 'description', ''),
                'parameters': getattr(tool, 'parameters', {})
            })
        import json
        return json.dumps(tools_list)  # FIX #18: Send all tools, not just first 50
    
    def _build_single_loop_prompt(self, tools_json: str) -> str:
        """Build system prompt for single-loop execution with natural language parsing."""
        # Get current app context
        app_ctx = self.get_app_context()
        app_context_str = ""
        
        if app_ctx.get('current_app'):
            app_context_str += f"\nCurrent active app: {app_ctx['current_app']}"
        if app_ctx.get('last_active_app') and app_ctx['last_active_app'] != app_ctx.get('current_app'):
            app_context_str += f"\nLast active app: {app_ctx['last_active_app']}"
        if app_ctx.get('recent_app_switches'):
            switches = ' → '.join([s['to_app'] for s in app_ctx['recent_app_switches'][-3:]])
            app_context_str += f"\nRecent app switches: {switches}"
        
        return f"""You are JARVIS, an AI assistant that can use tools to help users.
{app_context_str}

CRITICAL: You must ONLY output ONE tool call at a time. Never plan multiple steps.

OUTPUT FORMAT RULES:
- When you need to use a tool, respond with EXACTLY: "TOOL: tool_name(parameters)"
- Example: "TOOL: open_app(app='notepad')"
- NEVER output explanatory text before or after the tool call
- NEVER output multiple tool calls in one response
- After each tool execution, you'll receive the result and can decide the next single action
- When the task is complete, give your final answer naturally

Available tools:
{tools_json}

Examples:
User: hello
Assistant: Hello! How can I help you today?

User: open notepad
Assistant: TOOL: open_app(app='notepad')
[Tool result: Opening notepad]
Assistant: Notepad is now open.

User: what's the current time
Assistant: TOOL: get_time()
[Tool result: 3:45 PM]
Assistant: The current time is 3:45 PM.

RULES:
- ONE tool call per response - this is mandatory
- Wait for tool result before deciding next action
- Use FINAL when task is complete
- Never output multiple TOOL calls in one response
- Never mix tool calls with explanatory text
- When user refers to "it", "that", or "the app", use the app context above"""
    
    def _validate_and_parse_json(self, text: str) -> Optional[Dict]:
        """Validate and parse JSON from LLM response."""
        import json
        import re
        
        if not text:
            return None
        
        # Try to extract JSON from text (handle markdown code blocks)
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()
        
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and 'type' in parsed:
                return parsed
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _parse_natural_response(self, text: str) -> Optional[Dict]:
        """
        Parse natural language response for tool calls or final answers.
        
        CRITICAL: Only allows SINGLE tool calls. Multiple tools in one response are rejected.
        CRITICAL: Strictly separates tool calls from text - no mixing allowed.
        
        Uses the tool_parser module for deterministic parsing with schema validation.
        
        Looks for patterns like:
        - "TOOL: tool_name(params)"
        - JSON format (fallback)
        - Natural text (treated as final)
        """
        import re
        import json
        
        if not text or not text.strip():
            return None
        
        text = text.strip()
        
        # CRITICAL FIX: Detect and auto-execute leaked plan JSON BEFORE any other parsing
        # This prevents mode confusion from causing JSON leaks to the user
        if text.startswith('{'):
            try:
                parsed_json = json.loads(text)
                if isinstance(parsed_json, dict):
                    # Check for plan structure (goal + steps)
                    if 'steps' in parsed_json and isinstance(parsed_json.get('steps'), list):
                        steps = parsed_json['steps']
                        if len(steps) > 0:
                            # Auto-execute first step immediately
                            first_step = steps[0]
                            tool_name = first_step.get('tool')
                            params = first_step.get('params', {})
                            if tool_name:
                                logger.warning(f"Plan JSON leaked - auto-executing: {tool_name}")
                                return {
                                    'type': 'TOOL',
                                    'tool': tool_name,
                                    'params': params,
                                    'thought': f"Auto-extracted from plan: {first_step.get('reason', 'Step 1')}"
                                }
                        # No valid steps - return error message with more context
                        goal = parsed_json.get('goal', 'the task')
                        return {
                            'type': 'FINAL',
                            'response': f"I had trouble completing: {goal}. Could you provide more details or try a different approach?",
                            'thought': 'Empty plan detected'
                        }
                    # Check for direct tool call in JSON format
                    elif parsed_json.get('type') == 'TOOL':
                        return parsed_json
            except Exception as e:
                logger.debug(f"Not a valid JSON plan: {e}")
                pass  # Continue with normal parsing
        
        # STRICT SEPARATION: If TOOL: pattern found, extract ONLY the tool call
        # Remove any trailing text after the tool call to prevent mixed output
        tool_pattern_match = re.search(
            r'(TOOL:\s*\w+\s*\([^)]*(?:\([^)]*\))*[^)]*\))',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if tool_pattern_match:
            # Extract only the tool call portion
            tool_call_only = tool_pattern_match.group(1)
            # Check for multiple tool calls (reject if found)
            all_tool_matches = re.findall(
                r'TOOL:\s*\w+\s*\([^)]*(?:\([^)]*\))*[^)]*\)',
                text,
                re.IGNORECASE
            )
            if len(all_tool_matches) > 1:
                logger.warning(f"Multiple tool calls detected in response: {all_tool_matches}")
                return None  # Reject multiple tool calls
            
            # Parse only the clean tool call
            parsed = parse_tool_call(tool_call_only)
            if parsed and parsed.get('type') == 'tool':
                # Convert to the internal format expected by _handle_unified_mode
                return {
                    'type': 'TOOL',
                    'tool': parsed['name'],
                    'params': parsed['args'],
                    'thought': parsed.get('thought', 'Parsed by tool_parser module')
                }
        else:
            # No TOOL: pattern - use normal parsing
            # Delegate to the dedicated parser module
            parsed = parse_tool_call(text)
            if parsed and parsed.get('type') == 'tool':
                # Convert to the internal format expected by _handle_unified_mode
                return {
                    'type': 'TOOL',
                    'tool': parsed['name'],
                    'params': parsed['args'],
                    'thought': parsed.get('thought', 'Parsed by tool_parser module')
                }
        
        # Fallback: Check for simpler tool patterns like "use tool_name" or "call tool_name"
        simple_tool_matches = re.findall(r'(?:use|call|run)\s+(\w+)', text, re.IGNORECASE)
        if len(simple_tool_matches) == 1:  # Only allow exactly one
            tool_name = simple_tool_matches[0]
            if tool_name.lower() not in ['this', 'that', 'it', 'the', 'a', 'an']:
                return {
                    'type': 'TOOL',
                    'tool': tool_name,
                    'params': {},
                    'thought': 'Simple single tool call detected'
                }
        elif len(simple_tool_matches) > 1:
            logger.warning(f"Multiple simple tool calls detected: {simple_tool_matches}")
            return None  # Reject multiple tool calls
        
        # Check for JSON format (backward compatibility)
        json_parsed = self._validate_and_parse_json(text)
        if json_parsed:
            # Also validate JSON doesn't contain multiple tools
            if json_parsed.get('type') == 'TOOL':
                # Single tool in JSON is OK
                return json_parsed
        
        # Default: treat as final response if it's not empty
        if text:
            return {
                'type': 'FINAL',
                'response': text,
                'thought': 'Natural language response'
            }
        
        return None
    
    def _execute_tool_in_loop(self, tool_name: str, params: Dict) -> str:
        """Execute a single tool and return result as string. FIX #15: Add ToolGuard validation."""
        try:
            # FIX #15: Validate tool call through safety layer before execution
            is_valid, error_msg = self.tool_guard.validate_tool_call(tool_name, params)
            if not is_valid:
                return f"Error: Tool call blocked by safety: {error_msg}"
            
            tool = self.tool_registry.get_all_tools().get(tool_name)
            if tool is None:
                return f"Error: Tool '{tool_name}' not found in registry"
            
            # Execute tool
            if hasattr(tool, 'execute'):
                result = tool.execute(**params)
            elif callable(tool):
                result = tool(**params)
            else:
                return f"Error: Tool {tool_name} is not callable"
            
            # Convert result to string
            if isinstance(result, dict):
                if result.get('success'):
                    return result.get('output', str(result))
                else:
                    return f"Error: {result.get('error', 'Unknown error')}"
            elif isinstance(result, str):
                return result
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"
    
    def _normalize_tool_arguments(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize tool arguments to match expected parameter names.
        
        This fixes the mismatch between LLM-generated argument names and tool definitions.
        For example, LLM may output 'app_name' but open_app expects 'app'.
        
        Args:
            tool_name: Name of the tool being called
            args: Original arguments from LLM
            
        Returns:
            Normalized arguments dict
        """
        normalized = args.copy()
        
        # Mapping of tool-specific argument normalizations
        # Format: tool_name -> {external_name: internal_name}
        arg_mappings = {
            'open_app': {'app_name': 'app'},
            'close_app': {'app_name': 'app'},
        }
        
        if tool_name in arg_mappings:
            for external_name, internal_name in arg_mappings[tool_name].items():
                if external_name in normalized and internal_name not in normalized:
                    normalized[internal_name] = normalized.pop(external_name)
        
        return normalized
    
    def _execute_action(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a parsed tool call and return structured result.
        
        This is the main entry point for executing LLM-generated tool calls.
        It validates the schema, checks safety, executes the tool, and logs everything.
        
        Pipeline: Input → LLM → detect tool call → parse → execute → return result
        
        Args:
            tool_call: Parsed tool call dict with schema:
                {
                    "type": "tool",
                    "name": "<tool_name>",
                    "args": {},
                    "thought": "<optional reasoning>"
                }
        
        Returns:
            Result dict with:
                - success: bool
                - output: str (tool output or error message)
                - tool_name: str
                - args: dict
                - duration_ms: int
        """
        import time as time_module
        start_time = time_module.time()
        
        # Log raw input (sanitized)
        logger.info(f"[EXEC] Received tool call: {_safe_log(str(tool_call))}")
        
        # Validate schema
        valid, error_msg = validate_tool_call_schema(tool_call)
        if not valid:
            logger.error(f"[EXEC] Invalid tool call schema: {_safe_log(error_msg)}")
            return {
                'success': False,
                'output': f"Invalid tool call format: {error_msg}",
                'tool_name': tool_call.get('name', 'unknown'),
                'args': tool_call.get('args', {}),
                'duration_ms': int((time_module.time() - start_time) * 1000)
            }
        
        tool_name = tool_call['name']
        args = tool_call.get('args', {})
        thought = tool_call.get('thought', '')
        
        # Log parsed plan (sanitized)
        logger.info(f"[EXEC] Parsed plan: tool={tool_name}, args={args}, thought={_safe_log(thought)}")
        
        # STEP 1: Normalize arguments before validation
        # This fixes the mismatch between LLM output (app_name) and tool expectations (app)
        normalized_args = self._normalize_tool_arguments(tool_name, args)
        if normalized_args != args:
            logger.info(f"[EXEC] Normalized args: {normalized_args}")
        
        # STEP 2: Safety validation with normalized args
        is_valid, error_msg = self.tool_guard.validate_tool_call(tool_name, normalized_args)
        if not is_valid:
            logger.warning(f"[EXEC] Tool call blocked by safety: {_safe_log(error_msg)}")
            self.audit_log.log_security_event(
                event_type='tool_blocked',
                details={
                    'tool_name': tool_name,
                    'args': normalized_args,
                    'reason': error_msg
                }
            )
            return {
                'success': False,
                'output': f"Safety blocked: {error_msg}",
                'tool_name': tool_name,
                'args': normalized_args,
                'duration_ms': int((time_module.time() - start_time) * 1000),
                'retry_allowed': False  # Do not retry on safety failures
            }
        
        # Get tool from registry
        tool = self.tool_registry.get_all_tools().get(tool_name)
        if tool is None:
            logger.error(f"[EXEC] Tool not found: {tool_name}")
            return {
                'success': False,
                'output': f"Tool '{tool_name}' not found in registry",
                'tool_name': tool_name,
                'args': args,
                'duration_ms': int((time_module.time() - start_time) * 1000)
            }
        
        # Execute tool with normalized args
        try:
            logger.info(f"[EXEC] Executing: {tool_name}({normalized_args})")
            
            if hasattr(tool, 'execute'):
                result = tool.execute(**normalized_args)
            elif callable(tool):
                result = tool(**normalized_args)
            else:
                raise TypeError(f"Tool {tool_name} is not callable")
            
            # Process result
            if isinstance(result, dict):
                success = result.get('success', True)
                output = result.get('output', str(result))
                if not success:
                    output = f"Error: {result.get('error', 'Unknown error')}"
            elif isinstance(result, str):
                success = True
                output = result
            else:
                success = True
                output = str(result)
            
            duration_ms = int((time_module.time() - start_time) * 1000)
            
            # Log execution result (sanitized)
            logger.info(f"[EXEC] Result: success={success}, output={_safe_log(output[:100])}..., duration={duration_ms}ms")
            
            # Audit log with normalized args
            self.audit_log.log_action(
                action_type='tool_execution',
                details={
                    'tool_name': tool_name,
                    'args': normalized_args,
                    'thought': thought,
                    'success': success,
                    'output_preview': output[:200],
                    'duration_ms': duration_ms
                }
            )
            
            return {
                'success': success,
                'output': output,
                'tool_name': tool_name,
                'args': normalized_args,
                'thought': thought,
                'duration_ms': duration_ms
            }
            
        except Exception as e:
            logger.error(f"[EXEC] Execution error: {e}", exc_info=True)
            duration_ms = int((time_module.time() - start_time) * 1000)
            
            self.audit_log.log_action(
                action_type='tool_error',
                details={
                    'tool_name': tool_name,
                    'args': normalized_args,
                    'error': str(e),
                    'duration_ms': duration_ms
                }
            )
            
            return {
                'success': False,
                'output': f"Execution error: {str(e)}",
                'tool_name': tool_name,
                'args': args,
                'duration_ms': duration_ms
            }
    
    def _handle_chat_request(self, command: str) -> Dict[str, Any]:
        """Handle simple chat requests that don't require tool execution."""
        try:
            # Use a chat-specific prompt to get natural language response
            chat_prompt = f"Respond naturally to this greeting or chat message. Be friendly and concise:\n\nUser: {command}"
            
            response = self.brain.chat(
                messages=[{"role": "user", "content": chat_prompt}],
                temperature=0.7,
                include_tools=False
            )
            
            # Extract content from response
            if isinstance(response, dict):
                response_text = response.get('content', 'Hello! How can I help you?')
                success = response.get('success', True)
            else:
                response_text = str(response) if response else 'Hello! How can I help you?'
                success = True
            
            # If response is JSON (fallback), try to extract goal or respond with it
            if response_text.strip().startswith('{'):
                try:
                    import json as json_module
                    parsed = json_module.loads(response_text)
                    # If it's a plan-like JSON with no steps, just respond naturally
                    if not parsed.get('steps'):
                        response_text = "Hello! How can I assist you today?"
                    elif parsed.get('goal'):
                        response_text = parsed.get('goal', response_text)
                except:
                    pass  # Keep the original response if parsing fails
            
            # Speak response
            self._speak(response_text)
            
            return {
                'success': success,
                'response': response_text,
                'mode': 'unified',
                'actions': []
            }
        except Exception as e:
            logger.error(f"Chat request failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'response': "I encountered an error processing your request.",
                'mode': 'unified',
                'actions': []
            }
    
    def _execute_plan(self, command: str, plan: Dict) -> Dict[str, Any]:
        """Execute a generated plan and return results."""
        logger.info(f"Generated predictive plan with {len(plan['steps'])} steps (confidence: {plan.get('confidence', 'unknown')})")
        
        # Create task plan
        task_steps = []
        for step in plan['steps']:
            task_step = TaskStep(
                tool_name=step['tool'],
                parameters=step.get('params', {}),
                description=step.get('reason', '')
            )
            task_steps.append(task_step)
        
        # Create plan object
        task_plan = self.task_executor.create_plan(
            task_id=f"task_{hashlib.sha256(command.encode()).hexdigest()[:8]}",
            description=plan.get('goal', command),
            steps=task_steps
        )
        
        # Execute the plan
        result = self.task_executor.execute_plan(
            task_plan,
            stop_on_failure=False
        )
        
        # Learn from successful execution
        if result['success']:
            self.intent_scorer.learn_from_interaction(command, executed=True)
            
            # Store recent result for context
            self._recent_results.append({
                'command': command,
                'result': result['output'],
                'timestamp': time.time()
            })
            if len(self._recent_results) > self._max_recent_results:
                self._recent_results.pop(0)
        
        # Build response
        response_parts = []
        if result.get('step_results'):
            for step_result in result['step_results']:
                if step_result.get('success'):
                    response_parts.append(step_result.get('output', ''))
        
        response_text = '. '.join(filter(None, response_parts)) if response_parts else result.get('output', 'Task completed')
        
        # Speak response
        self._speak(response_text)
        
        return {
            'success': result['success'],
            'response': response_text,
            'mode': 'unified',
            'actions': plan['steps'],
            'confirmed': not plan.get('needs_clarification', False)
        }
    
    def _handle_react_fallback(self, command: str) -> Dict[str, Any]:
        """Fallback to ReAct agent for complex tasks needing iterative reasoning."""
        logger.info(f"Using ReAct agent for complex task: {command[:50]}...")
        
        try:
            result = self.react_agent.execute(command)
            
            # ReAct agent returns string response directly
            if isinstance(result, str):
                response_text = result
                success = not result.startswith("Error:")
            else:
                response_text = result.get('response', 'Task completed')
                success = result.get('success', True)
            
            if success:
                # Learn from successful execution
                self.intent_scorer.learn_from_interaction(command, executed=True)
                
                # Speak response
                self._speak(response_text)
                
                return {
                    'success': True,
                    'response': response_text,
                    'mode': 'unified',
                    'actions': []
                }
            else:
                logger.error(f"ReAct agent failed: {response_text}")
                return {
                    'success': False,
                    'error': response_text,
                    'response': "I wasn't able to complete that task.",
                    'mode': 'unified',
                    'actions': []
                }
                
        except Exception as e:
            logger.error(f"ReAct fallback error: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'response': "I encountered an error processing your request.",
                'mode': 'unified',
                'actions': []
            }
    
    def _handle_chat_mode(self, command: str) -> Dict[str, Any]:
        """
        Handle chat mode - simple conversation without tool use.
        
        Uses streaming reply for low latency.
        Starts speaking before full response is generated.
        Exactly as responsive as the current system.
        
        Args:
            command: User command
            
        Returns:
            Response dict
        """
        logger.info(f"Handling in chat mode: {command[:50]}...")
        
        # Check if this looks like it should be agent mode (safety check)
        # If user says something that sounds like a command, suggest switching to agent mode
        quick_check = self.intent_classifier._heuristic_classify(command)
        if quick_check['mode'] == 'agent' and quick_check['confidence'] > 0.7:
            # This might be a misclassified agent request - add helpful suggestion
            logger.warning(f"Chat mode received but input appears to be agent-mode: {command[:50]}")
        
        system_prompt = get_system_prompt(mode='chat')
        
        # Use streaming for low latency - NO TOOLS in chat mode for clean responses
        response = self.brain.chat(
            messages=[{'role': 'user', 'content': command}],
            system_prompt=system_prompt,
            temperature=0.7,
            stream=True,  # Enable streaming for low latency
            include_tools=False  # Disable tool calling in pure chat mode
        )
        
        if response['success']:
            response_text = response['content']
            thinking_duration = response.get('thinking_duration')
            thinking_sections = response.get('thinking_sections', [])
            
            # Don't store assistant messages in chat mode to reduce memory usage
            
            # Display thinking sections if present (from reasoning models)
            if thinking_sections:
                print("\n\n╔════════════════════════════════════════╗")
                print("║       LLM REASONING PROCESS            ║")
                print("╚════════════════════════════════════════╝")
                for i, section in enumerate(thinking_sections, 1):
                    print(f"\n┌─── Thinking Path {i} ───")
                    # Show full thinking content with word wrapping
                    import textwrap
                    wrapped = textwrap.fill(section, width=80)
                    print(wrapped)
                    print("└─── End Path ───\n")
                if thinking_duration:
                    print(f"\n⏱ Thinking completed in {thinking_duration:.2f}s\n")
            
            # Start speaking immediately for low latency (before full response if streaming)
            self._speak(response_text)
            
            return {
                'success': True,
                'response': response_text,
                'mode': 'chat',
                'actions': [],
                'streamed': True,
                'thinking_duration': thinking_duration,
                'thinking_sections': thinking_sections
            }
        else:
            return {
                'success': False,
                'error': response.get('error', 'Unknown error'),
                'response': "I'm having trouble responding right now.",
                'mode': 'chat',
                'actions': []
            }
    
    def _handle_agent_mode(self, command: str) -> Dict[str, Any]:
        """
        Handle agent mode with predictive execution.
        
        NEW APPROACH:
        1. Use LLM's internal knowledge to PREDICT the exact steps needed
        2. Generate a direct execution plan (no searching for known URLs)
        3. Execute immediately with high confidence
        4. Learn from outcomes to improve future predictions
        
        This eliminates wasteful ReAct loops for common tasks.
        """
        logger.info(f"Handling in agent mode: {command[:50]}...")
        
        # Clear abort flag for new task
        self.clear_abort()
        
        # Retrieve relevant memories
        context = self.memory.retrieve_context(query=command)
        memories = context.get('episodic', []) + context.get('semantic', []) + context.get('procedural', [])
        logger.debug(f"Retrieved {len(memories)} relevant memories")
        
        # Select reasoning strategy
        classification = self.strategy_selector.classify(command)
        strategy = self._map_complexity_to_strategy(classification.complexity)
        logger.info(f"Selected strategy: {strategy} (complexity: {classification.complexity.value})")
        
        system_prompt = get_system_prompt(mode='agent')
        
        # Track consecutive failures — FIX #6: use SHA-256 instead of Python hash()
        task_key = hashlib.sha256(command.encode()).hexdigest()[:8]
        
        # PREDICTIVE EXECUTION: Use LLM's internal knowledge for direct execution with TaskExecutor verification
        # This bypasses ReAct loops for tasks where the LLM already knows the answer
        if strategy in ['direct', 'plan']:
            logger.info(f"[Predictive] Using LLM's internal knowledge for direct execution...")
            
            # Generate predictive plan using LLM's world knowledge (extracted to avoid duplication)
            tools_dict = {name: {'description': getattr(tool, 'description', '')} 
                         for name, tool in self.tool_registry.get_all_tools().items()}
            
            plan = self._generate_predictive_plan(command, tools_dict)
            
            if plan and plan.get('steps'):
                # Bug #5 fix: Check for clarification request BEFORE checking for steps
                needs_clarification = plan.get('needs_clarification', False)
                clarification_question = plan.get('clarification_question', None)
                
                # If LLM requested clarification but provided no executable steps
                if needs_clarification and clarification_question:
                    logger.info(f"LLM requested clarification: {clarification_question}")
                    
                    # Surface the clarification question to the user
                    print(f"\n{'='*60}")
                    print(f"❓ Clarification Needed")
                    print(f"{'='*60}")
                    print(f"Goal: {plan.get('goal', command)}")
                    print(f"\n{clarification_question}")
                    print(f"{'='*60}")
                    
                    response_text = f"I need clarification: {clarification_question}"
                    
                    return {
                        'success': True,
                        'response': response_text,
                        'mode': 'clarification_needed',
                        'needs_clarification': True,
                        'clarification_question': clarification_question,
                        'plan': plan
                    }
                
                logger.info(f"Generated predictive plan with {len(plan['steps'])} steps (confidence: {plan.get('confidence', 'unknown')})")
                
                # Convert predictive plan steps to TaskStep objects for TaskExecutor
                task_steps = []
                for step_dict in plan['steps']:
                    tool_name = step_dict.get('tool') or step_dict.get('tool_or_skill')
                    
                    # Use robust parameter normalization that handles all edge cases
                    from jarvis.core.json_utils import normalize_plan_parameters
                    arguments = normalize_plan_parameters(step_dict, tool_name)
                    
                    description = step_dict.get('description', f"Execute {tool_name}")
                    
                    # Determine verification strategy based on tool type
                    verification_strategy = VerificationStrategy.TOOL_RESULT
                    verification_keyword = None
                    
                    # Enable visual verification for web/UI operations
                    if any(keyword in tool_name.lower() for keyword in ['click', 'fill', 'navigate', 'scroll', 'type']):
                        if self.task_executor.enable_visual_verification:
                            verification_strategy = VerificationStrategy.VISUAL
                            verification_keyword = description.split()[0] if description else tool_name
                    
                    # Use STATE_CHECK for keyboard shortcuts (more reliable verification)
                    if tool_name == 'press_key':
                        verification_strategy = VerificationStrategy.STATE_CHECK
                    
                    task_step = TaskStep(
                        tool_name=tool_name,
                        parameters=arguments,
                        description=description,
                        verification_strategy=verification_strategy,
                        verification_keyword=verification_keyword,
                        timeout=30.0,
                        max_retries=2
                    )
                    task_steps.append(task_step)
                
                # Create TaskPlan for TaskExecutor
                import uuid
                task_plan = self.task_executor.create_plan(
                    task_id=f"task_{uuid.uuid4().hex[:8]}",
                    description=command,
                    steps=task_steps
                )
                
                # Execute the plan using TaskExecutor with verification and loop prevention
                executed_plan = self.task_executor.execute_plan(task_plan, stop_on_failure=False)
                
                # Get task summary for response
                task_summary = self.task_executor.get_task_summary(executed_plan)
                
                # Update context awareness tracking with results
                for step in executed_plan.steps:
                    if step.status.value == 'completed' and step.result:
                        # Store successful result
                        result_entry = {
                            'tool': step.tool_name,
                            'command': command[:100],
                            'result': str(step.result.output if hasattr(step.result, 'output') else step.result),
                            'timestamp': time.time()
                        }
                        self._recent_results.append(result_entry)
                        # Keep only last N results
                        if len(self._recent_results) > self._max_recent_results:
                            self._recent_results.pop(0)
                    elif step.status.value in ['failed', 'error'] and step.error_message:
                        # Store failed action
                        failure_entry = {
                            'tool': step.tool_name,
                            'command': command[:100],
                            'error': step.error_message,
                            'timestamp': time.time()
                        }
                        self._failed_actions.append(failure_entry)
                        # Keep only last N failures
                        if len(self._failed_actions) > self._max_failed_actions:
                            self._failed_actions.pop(0)
                
                # Extract actual outputs from executed steps for display
                output_parts = []
                error_messages = []
                for step in executed_plan.steps:
                    if step.result and hasattr(step.result, 'output') and step.result.output:
                        output_parts.append(step.result.output)
                    elif step.result and isinstance(step.result, dict) and step.result.get('output'):
                        output_parts.append(step.result['output'])
                    
                    # Collect error messages from failed steps
                    if step.status.value in ['failed', 'error'] and step.error_message:
                        error_messages.append(f"{step.tool_name}: {step.error_message}")
                
                # Generate response with actual tool outputs or error details
                if output_parts:
                    response_text = ". ".join(output_parts)
                    if error_messages:
                        response_text += f" (Note: Some steps had issues - {'; '.join(error_messages[:2])})"
                else:
                    successful = task_summary['successful_steps']
                    total = task_summary['total_steps']
                    if successful == 0 and error_messages:
                        # Provide more helpful error message
                        response_text = f"I couldn't complete this task. The main issue was: {error_messages[0]}. You can try again or ask me to do something simpler."
                    else:
                        response_text = f"Task completed: {successful}/{total} steps successful."
                        if error_messages:
                            response_text += f" Failed steps: {'; '.join(error_messages[:2])}"
                
                # Determine error field for response
                error_field = None
                if error_messages:
                    # If there are errors and we don't have a proper response, summarize them
                    if not output_parts and task_summary['successful_steps'] == 0:
                        error_field = "; ".join(error_messages[:2])
                
                return {
                    'success': executed_plan.status.value == 'completed',
                    'response': response_text,
                    'error': error_field,
                    'mode': 'predictive',
                    'strategy': 'predictive',
                    'actions': [
                        {
                            'step': {'tool': step.tool_name, 'parameters': step.parameters, 'description': step.description},
                            'result': step.result,
                            'status': step.status.value,
                            'error': step.error_message,
                            'duration': step.duration
                        }
                        for step in executed_plan.steps
                    ],
                    'task_summary': task_summary,
                    'iterations': len(executed_plan.steps)
                }
            
            # Fallback to ReAct if predictive planning fails
            logger.warning("Predictive planning failed, falling back to ReAct agent...")
        
        # Traditional ReAct agent fallback
        if strategy == 'direct':
            logger.info(f"[ReAct] Using autonomous agent mode for: {command[:50]}...")
            
            # Bug #2 fix: Save history snapshot before ReAct to isolate its JSON exchanges
            self.brain.save_history_snapshot()
            
            react_result = self.react_agent.execute(command, context=memories)
            
            # Bug #2 fix: Restore history after ReAct completes to prevent JSON pollution
            self.brain.restore_history_snapshot()
            
            # Bug #3 fix: Sanitize ReAct result - detect and summarize JSON responses
            sanitized_response = self._sanitize_react_result(react_result)
            
            result = {
                'success': True,
                'response': sanitized_response,
                'mode': 'react'
            }
        # Planning required for complex tasks
        elif strategy == 'plan':
            result = self._execute_with_planning(command, system_prompt)
        # Full cycle with review for strategic tasks
        elif strategy == 'full_cycle':
            result = self._execute_full_cycle(command, system_prompt)
        else:
            result = self._execute_direct(command, system_prompt)
        
        # Track failures
        if not result.get('success'):
            self._consecutive_failures += 1
            self._failure_cache[task_key] = self._failure_cache.get(task_key, 0) + 1
            
            # Stop retrying after MAX_CONSECUTIVE_FAILURES
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(f"Stopped after {MAX_CONSECUTIVE_FAILURES} consecutive failures")
                result['error'] = f"I've encountered multiple issues with this task. Let's try something different."
        else:
            self._consecutive_failures = 0
            if task_key in self._failure_cache:
                del self._failure_cache[task_key]
        
        return result
    
    def _handle_agent_mode_with_confirm(self, command: str, intent_analysis: Dict) -> Dict[str, Any]:
        """
        Handle medium-confidence intents (60-84) by showing plan and asking for confirmation.
        Only asks for confirmation if the LLM indicates clarification is needed.
        
        Args:
            command: User command
            intent_analysis: Analysis result from intent scorer
            
        Returns:
            Response dict with confirmation status
        """
        logger.info(f"Handling with confirmation (score {intent_analysis['score']}): {command[:50]}...")
        
        # Generate the plan first
        context = self.memory.retrieve_context(query=command)
        memories = context.get('episodic', []) + context.get('semantic', []) + context.get('procedural', [])
        
        classification = self.strategy_selector.classify(command)
        strategy = self._map_complexity_to_strategy(classification.complexity)
        system_prompt = get_system_prompt(mode='agent')
        
        # Generate predictive plan (extracted to avoid duplication)
        if strategy in ['direct', 'plan']:
            tools_dict = {name: {'description': getattr(tool, 'description', '')} 
                         for name, tool in self.tool_registry.get_all_tools().items()}
            
            plan = self._generate_predictive_plan(command, tools_dict)
            
            if plan and plan.get('steps'):
                # Check if LLM requested clarification
                needs_clarification = plan.get('needs_clarification', False)
                
                # Only show confirmation if LLM explicitly requested it
                if needs_clarification:
                    # Show plan to user and ask for clarification
                    print(f"\n{'='*60}")
                    print(f"📋 Proposed Plan (Confidence: {intent_analysis['confidence']})")
                    print(f"{'='*60}")
                    print(f"Goal: {plan.get('goal', command)}")
                    print(f"\nSteps:")
                    for i, step in enumerate(plan['steps'], 1):
                        tool_name = step.get('tool', 'unknown')
                        params = step.get('params', {})
                        reason = step.get('reason', '')
                        print(f"  {i}. {tool_name}({', '.join(f'{k}={v}' for k,v in params.items())})")
                        if reason:
                            print(f"     → {reason}")
                    print(f"{'='*60}")
                    
                    # Ask for confirmation
                    response_text = f"Ready to execute {len(plan['steps'])} step(s). Type 'yes' to proceed, or describe changes."
                    print(f"\nJARVIS: {response_text}")
                    
                    # Get user confirmation
                    try:
                        confirm = input("\nYou: ").strip().lower()
                        
                        if confirm in ['yes', 'y', 'ok', 'go', 'proceed', 'do it']:
                            # User confirmed - execute the plan
                            logger.info("User confirmed plan - executing...")
                            result = self._handle_agent_mode(command)
                            result['confirmed'] = True
                            return result
                        elif confirm in ['no', 'n', 'cancel', 'stop']:
                            # User declined
                            logger.info("User declined plan")
                            return {
                                'success': False,
                                'response': "Cancelled as requested.",
                                'confirmed': False,
                                'mode': 'agent_confirm'
                            }
                        else:
                            # User wants modifications - treat as new command
                            logger.info(f"User suggested modification: {confirm}")
                            modified_command = f"{command} but {confirm}"
                            return self._handle_agent_mode(modified_command)
                            
                    except (EOFError, KeyboardInterrupt):
                        logger.warning("User cancelled confirmation")
                        return {
                            'success': False,
                            'response': "Confirmation cancelled.",
                            'confirmed': False,
                            'mode': 'agent_confirm'
                        }
                else:
                    # No clarification needed - execute directly
                    logger.info("LLM did not request clarification - executing plan directly...")
                    result = self._handle_agent_mode(command)
                    result['confirmed'] = True
                    return result
    
    def _generate_predictive_plan(self, command: str, tools_dict: dict) -> dict:
        """Helper method to generate predictive plan, avoiding code duplication."""
        return self.predictive_planner.generate_plan(
            command, 
            tools_dict,
            recent_results=self._recent_results,
            failed_actions=self._failed_actions
        )
        # Note: Dead code removed - the fallback below was unreachable after the return statement
    
    def _sanitize_react_result(self, react_result: str) -> str:
        """
        Bug #3 fix: Sanitize ReAct agent result to prevent raw JSON from being shown to user.
        
        If the result looks like a JSON object/dict (common when LLM returns structured plans),
        extract meaningful information and present it as natural language.
        
        Args:
            react_result: Raw string result from ReAct agent
            
        Returns:
            Sanitized, user-friendly response string
        """
        import json
        
        if not react_result or not isinstance(react_result, str):
            return str(react_result) if react_result else "Task completed."
        
        stripped = react_result.strip()
        
        # Check if result looks like a JSON object
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                # Try to parse as JSON
                data = json.loads(stripped)
                
                # If it's a plan with steps, summarize it
                if isinstance(data, dict):
                    if 'steps' in data and isinstance(data['steps'], list):
                        step_count = len(data['steps'])
                        summary = f"Completed {step_count} step(s)."
                        
                        # Extract any final response or status
                        if 'status' in data:
                            summary += f" Status: {data['status']}."
                        if 'response' in data:
                            summary += f" {data['response']}"
                        
                        return summary
                    
                    # If it has a 'response' or 'result' field, use that
                    for key in ['response', 'result', 'output', 'message']:
                        if key in data and data[key]:
                            return str(data[key])
                    
                    # Otherwise, provide a generic summary
                    keys_present = list(data.keys())[:3]
                    return f"Action completed. Details: {', '.join(keys_present)}."
                
            except json.JSONDecodeError:
                # Not valid JSON, return as-is
                pass
        
        # Check if it's a JSON array
        elif stripped.startswith('[') and stripped.endswith(']'):
            try:
                data = json.loads(stripped)
                if isinstance(data, list) and len(data) > 0:
                    return f"Completed {len(data)} action(s). Last result: {data[-1]}"
            except json.JSONDecodeError:
                pass
        
        # For normal text responses, return as-is
        return react_result
    
    def _get_active_app_name(self) -> Optional[str]:
        """Get the name of the currently active application."""
        try:
            import win32gui
            import win32process
            
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                import psutil
                process = psutil.Process(pid)
                return process.name().replace('.exe', '').lower()
        except Exception as e:
            logger.debug(f"Could not get active app: {e}")
        
        return None

    def _is_multi_step_command(self, command: str) -> bool:
        """
        Detect if a command requires multiple sequential steps.
        
        Bug #4 fix: Improved detection to avoid over-triggering on simple queries
        containing 'and' (e.g., "search for cats and dogs" is NOT multi-step).
        
        Args:
            command: User command string
            
        Returns:
            True if command appears to be multi-step
        """
        import re
        
        command_lower = command.lower().strip()
        
        # Check for conjunctions indicating multiple DISTINCT actions
        # Bug #4 fix: Be more specific - require action verbs on both sides of 'and'
        action_verbs = ['open', 'close', 'type', 'write', 'click', 'press', 'navigate', 
                       'search', 'find', 'create', 'delete', 'move', 'copy', 'paste',
                       'launch', 'start', 'stop', 'minimize', 'maximize', 'switch']
        
        # Pattern: verb ... and/or then/after/before ... verb
        # This ensures we only flag commands with multiple distinct actions
        multi_action_patterns = [
            r'\b(open|close|type|write|click|press|navigate|search|find|create|delete|move|copy|paste|launch|start|stop|minimize|maximize|switch)\b.*\b(and|then|after|before|followed by)\b.*\b(open|close|type|write|click|press|navigate|search|find|create|delete|move|copy|paste|launch|start|stop|minimize|maximize|switch)\b'
        ]
        
        for pattern in multi_action_patterns:
            if re.search(pattern, command_lower):
                return True
        
        # Check for explicit sequencing words that indicate multiple steps
        sequencing_words = [' then ', ' after ', ' before ', ' followed by ']
        for seq in sequencing_words:
            if seq in command_lower:
                # Additional check: ensure there are two distinct action phrases
                parts = command_lower.split(seq)
                if len(parts) >= 2:
                    # Check if both parts contain action verbs
                    has_verb_before = any(verb in parts[0] for verb in action_verbs)
                    has_verb_after = any(verb in parts[1] for verb in action_verbs)
                    if has_verb_before and has_verb_after:
                        return True
        
        # Check for commas separating distinct actions (not just list items)
        if ',' in command:
            parts = command.split(',')
            if len(parts) > 1:
                # Count how many parts have action verbs
                parts_with_verbs = sum(1 for part in parts if any(verb in part for verb in action_verbs))
                if parts_with_verbs >= 2:
                    return True
        
        # Original 'and' check - but now only for clear compound commands
        # Bug #4 fix: Only trigger if 'and' connects two action phrases
        if ' and ' in command_lower:
            parts = command_lower.split(' and ')
            if len(parts) >= 2:
                # Check if both parts contain action verbs
                has_verb_before = any(verb in parts[0] for verb in action_verbs)
                has_verb_after = any(verb in parts[1] for verb in action_verbs)
                if has_verb_before and has_verb_after:
                    return True
        
        return False

    def _update_app_context(self) -> None:
        """
        Update the last active app tracking.
        Called periodically to track which app the user is working in.
        """
        current_time = time.time()
        
        # Rate limit checks to avoid excessive polling
        if current_time - self._last_app_check_time < self._app_check_interval:
            return
        
        self._last_app_check_time = current_time
        current_app = self._get_active_app_name()
        
        if not current_app:
            return
        
        # Check if app changed
        if current_app != self._last_active_app:
            if self._last_active_app:
                # Record the app switch
                self._app_switch_history.append({
                    'from_app': self._last_active_app,
                    'to_app': current_app,
                    'timestamp': current_time,
                    'time': datetime.now().strftime('%H:%M:%S')
                })
                # Keep only last N entries
                if len(self._app_switch_history) > self._max_app_history:
                    self._app_switch_history.pop(0)
                
                logger.debug(f"App switched: {self._last_active_app} -> {current_app}")
            
            self._last_active_app = current_app

    def get_app_context(self) -> Dict[str, Any]:
        """
        Get the current app context for LLM awareness.
        
        Returns:
            Dict with last active app and recent app history
        """
        return {
            'last_active_app': self._last_active_app,
            'recent_app_switches': self._app_switch_history[-5:] if self._app_switch_history else [],
            'current_app': self._get_active_app_name()
        }
    
    def _execute_direct(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """
        Execute command directly with tool calling.
        
        For trivial/simple tasks that don't require planning.
        Uses streaming reply for low latency in chat mode.
        """
        # Check for abort before starting
        if self.check_abort():
            return {
                'success': False,
                'error': 'Task aborted by user',
                'response': "Task cancelled.",
                'mode': 'agent',
                'strategy': 'direct',
                'actions': [],
                'iterations': 0
            }
        
        response = self.brain.chat_with_tools(
            user_message=command,
            system_prompt=system_prompt,
            max_iterations=MAX_AGENT_ROUNDS  # Cap at MAX_AGENT_ROUNDS
        )
        
        if response['success']:
            response_text = response['content']
            thinking_duration = response.get('thinking_duration')
            thinking_sections = response.get('thinking_sections', [])
            
            # Don't store assistant messages to reduce memory usage
            
            # Display thinking sections if present (from reasoning models)
            if thinking_sections:
                print("\n\n╔════════════════════════════════════════╗")
                print("║       LLM REASONING PROCESS            ║")
                print("╚════════════════════════════════════════╝")
                for i, section in enumerate(thinking_sections, 1):
                    print(f"\n┌─── Thinking Path {i} ───")
                    # Show full thinking content with word wrapping
                    import textwrap
                    wrapped = textwrap.fill(section, width=80)
                    print(wrapped)
                    print("└─── End Path ───\n")
                if thinking_duration:
                    print(f"\n⏱ Thinking completed in {thinking_duration:.2f}s\n")
            
            # Start speaking before full response is generated for low latency
            self._speak(response_text)
            
            return {
                'success': True,
                'response': response_text,
                'mode': 'agent',
                'strategy': 'direct',
                'actions': response.get('tool_calls', []),
                'iterations': response.get('iterations', 0),
                'total_thinking_time': thinking_duration,
                'thinking_sections': thinking_sections
            }
        else:
            error_msg = response.get('error', 'Execution failed')
            
            # Handle unknown tool name errors with helpful suggestions
            if 'tool' in error_msg.lower() and 'not found' in error_msg.lower():
                # Extract tool name from error
                import re
                match = re.search(r"tool['\s]+(\w+)", error_msg, re.IGNORECASE)
                if match:
                    unknown_tool = match.group(1)
                    # Find similar tools
                    similar = self.tool_registry.find_similar_tools(unknown_tool, limit=5)
                    error_msg = f"Tool '{unknown_tool}' not found. Available tools that might help: {', '.join(similar) if similar else 'none'}"
            
            return {
                'success': False,
                'error': error_msg,
                'response': "I couldn't complete that task.",
                'mode': 'agent',
                'strategy': 'direct',
                'actions': [],
                'iterations': response.get('iterations', 0)
            }
    
    def _execute_with_planning(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """
        Execute command with planning phase using TaskExecutor for Plan-Execute-Verify loop.
        
        Only called for complex/strategic tasks as determined by strategy_selector.
        Always runs critic before execution.
        """
        # Check for abort before starting
        if self.check_abort():
            return {
                'success': False,
                'error': 'Task aborted by user',
                'response': "Task cancelled.",
                'mode': 'agent',
                'strategy': 'plan',
                'actions': []
            }
        
        # Generate plan using planner
        plan_result = self.planner.create_plan(command)
        
        if not plan_result.get('success'):
            return {
                'success': False,
                'error': plan_result.get('error', 'Planning failed'),
                'response': "I'm having trouble creating a plan for that task.",
                'mode': 'agent',
                'strategy': 'plan',
                'actions': []
            }
        
        # Extract steps from execution_graph
        execution_graph = plan_result.get('execution_graph')
        if not execution_graph:
            return {
                'success': False,
                'error': 'No execution graph in plan result',
                'response': "I'm having trouble creating a plan for that task.",
                'mode': 'agent',
                'strategy': 'plan',
                'actions': []
            }
        
        plan_steps = [step.to_dict() for step in execution_graph.steps]
        
        # Phase 3 Safety: Plan validation (second safety layer)
        plan_validation = self.plan_validator.review(plan_steps)
        
        if not plan_validation.is_valid:
            logger.warning(f"Plan blocked by validator: {plan_validation.warnings}")
            self.audit_log.log_security_event(
                event_type='plan_blocked',
                details={
                    'goal': command,
                    'risk_level': plan_validation.risk_level.value,
                    'warnings': plan_validation.warnings,
                    'blocked_steps': plan_validation.blocked_steps
                }
            )
            
            # Return with explanation
            response_text = f"I cannot execute this plan due to safety concerns: {'; '.join(plan_validation.warnings[:2])}"
            if plan_validation.suggestions:
                response_text += f". Suggestions: {'; '.join(plan_validation.suggestions[:2])}"
            
            return {
                'success': False,
                'error': 'Plan blocked by safety validator',
                'response': response_text,
                'mode': 'agent',
                'strategy': 'plan',
                'actions': [],
                'safety_blocked': True,
                'validation': {
                    'is_valid': False,
                    'risk_level': plan_validation.risk_level.value,
                    'warnings': plan_validation.warnings,
                    'suggestions': plan_validation.suggestions
                }
            }
        
        # Log plan review even if it passes
        if plan_validation.requires_confirmation or plan_validation.warnings:
            logger.info(f"Plan validated with warnings: {plan_validation.warnings}")
            self.audit_log.log_security_event(
                event_type='plan_reviewed',
                details={
                    'goal': command,
                    'risk_level': plan_validation.risk_level.value,
                    'warnings': plan_validation.warnings,
                    'requires_confirmation': plan_validation.requires_confirmation
                }
            )
        
        # ALWAYS run critic before execution (required by spec)
        critique = self.critic.review_plan(plan_steps, command)
        
        # Handle critic results
        if critique.decision == CriticDecision.BLOCKED:
            logger.warning(f"Plan blocked by critic: {critique.blocked_reason}")
            return {
                'success': False,
                'error': 'Plan blocked by critic',
                'response': f"I cannot proceed: {critique.blocked_reason or 'The plan has issues.'}",
                'mode': 'agent',
                'strategy': 'plan',
                'actions': [],
                'critique': critique.to_dict()
            }
        
        elif critique.decision == CriticDecision.NEEDS_REVISION:
            logger.info(f"Plan needs revision: {critique.fixes_needed}")
            # Attempt to fix the plan
            revised_plan = self.planner.revise_plan(command, plan_steps, critique.fixes_needed)
            if revised_plan.get('success'):
                plan_steps = revised_plan.get('plan', plan_steps)
                logger.info("Plan revised successfully")
            else:
                logger.warning("Plan revision failed, proceeding with original plan")
        
        # Check for duplicate action (loop prevention) using action memory — FIX #6: use SHA-256
        action_hash = hashlib.sha256(command.encode()).hexdigest()[:12]
        current_time = time.time()
        if action_hash in self._action_memory:
            last_executed = self._action_memory[action_hash]
            if current_time - last_executed < 30:  # Within 30 seconds
                logger.warning(f"Duplicate command detected within 30s, skipping: {command[:50]}...")
                return {
                    'success': False,
                    'error': 'Duplicate command',
                    'response': "I just executed that command. Please wait or try something different.",
                    'mode': 'agent',
                    'strategy': 'plan',
                    'actions': []
                }
        
        # Record this action for loop prevention
        self._action_memory[action_hash] = current_time
        # Keep only recent actions (cleanup old entries)
        cutoff = current_time - 60
        self._action_memory = {k: v for k, v in self._action_memory.items() if v > cutoff}
        
        # Convert plan steps to TaskStep objects for TaskExecutor
        task_steps = []
        for step_dict in plan_steps:
            tool_name = step_dict.get('tool') or step_dict.get('tool_or_skill')
            arguments = step_dict.get('arguments', {}) or step_dict.get('params', {})
            description = step_dict.get('description', f"Execute {tool_name}")
            
            # Determine verification strategy based on tool type
            verification_strategy = VerificationStrategy.TOOL_RESULT
            verification_keyword = None
            
            # Enable visual verification for web/UI operations
            if any(keyword in tool_name.lower() for keyword in ['click', 'fill', 'navigate', 'scroll', 'type']):
                if self.task_executor.enable_visual_verification:
                    verification_strategy = VerificationStrategy.VISUAL
                    # Extract keyword from description or use tool name
                    verification_keyword = description.split()[0] if description else tool_name
            
            task_step = TaskStep(
                tool_name=tool_name,
                parameters=arguments,
                description=description,
                verification_strategy=verification_strategy,
                verification_keyword=verification_keyword,
                timeout=30.0,
                max_retries=2
            )
            task_steps.append(task_step)
        
        # Create TaskPlan for TaskExecutor
        import uuid
        task_plan = self.task_executor.create_plan(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            description=command,
            steps=task_steps
        )
        
        # Execute plan using TaskExecutor with verification and loop prevention
        logger.info(f"Executing plan with TaskExecutor: {len(task_steps)} steps")
        executed_plan = self.task_executor.execute_plan(task_plan, stop_on_failure=False)
        
        # Get task summary for response
        task_summary = self.task_executor.get_task_summary(executed_plan)
        
        # Extract actual outputs from executed steps for display
        output_parts = []
        for step in executed_plan.steps:
            if step.result and hasattr(step.result, 'output') and step.result.output:
                output_parts.append(step.result.output)
            elif step.result and isinstance(step.result, dict) and step.result.get('output'):
                output_parts.append(step.result['output'])
        
        # Generate response with actual tool outputs
        if output_parts:
            response_text = ". ".join(output_parts)
        else:
            # Fallback to summary
            successful = task_summary['successful_steps']
            total = task_summary['total_steps']
            response_text = f"Task completed: {successful}/{total} steps successful."
        
        # Don't store assistant message to reduce memory usage
        self._speak(response_text)
        
        return {
            'success': executed_plan.status.value == 'completed',
            'response': response_text,
            'mode': 'agent',
            'strategy': 'plan',
            'actions': [
                {
                    'step': {'tool': step.tool_name, 'parameters': step.parameters, 'description': step.description},
                    'result': step.result,
                    'status': step.status.value,
                    'error': step.error_message,
                    'duration': step.duration
                }
                for step in executed_plan.steps
            ],
            'task_summary': task_summary,
            'critique': critique.to_dict(),
            'total_thinking_time': plan_result.get('thinking_duration')
        }
    
    def _rollback_steps(self, executed_steps: List[Dict]) -> None:
        """Rollback executed steps in reverse order."""
        logger.info(f"Rolling back {len(executed_steps)} steps")
        for step_info in reversed(executed_steps):
            step = step_info.get('step', {})
            # Handle both formats: 'tool' or 'tool_or_skill'
            tool_name = step.get('tool') or step.get('tool_or_skill')
            try:
                # Try to call rollback method if available
                if hasattr(self.tool_registry.tools.get(tool_name), 'rollback'):
                    self.tool_registry.tools[tool_name].rollback()
            except Exception as e:
                logger.warning(f"Failed to rollback {tool_name}: {e}")
    
    def _execute_full_cycle(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """
        Execute with full planning, review, and reflection cycle.
        
        For strategic long-running goals requiring:
        - Planning
        - Critic review
        - Goal tracking across sessions
        """
        # Check for abort before starting
        if self.check_abort():
            return {
                'success': False,
                'error': 'Task aborted by user',
                'response': "Task cancelled.",
                'mode': 'agent',
                'strategy': 'full_cycle',
                'actions': []
            }
        
        # Store goal for cross-session tracking
        goal_id = f"goal_{int(time.time())}"
        self.memory.store_goal(goal_id, command)
        
        # Execute with planning (includes critic)
        result = self._execute_with_planning(command, system_prompt)
        result['strategy'] = 'full_cycle'
        
        # Update goal status
        if result.get('success'):
            self.memory.update_goal_status(goal_id, 'completed')
        else:
            self.memory.update_goal_status(goal_id, 'failed')
        
        return result
    
    def _map_complexity_to_strategy(self, complexity: TaskComplexity) -> str:
        """
        Map TaskComplexity enum to execution strategy string.
        
        Args:
            complexity: Task complexity level from strategy selector
            
        Returns:
            Strategy string: 'direct', 'plan', or 'full_cycle'
        """
        if complexity == TaskComplexity.TRIVIAL:
            return 'direct'
        elif complexity == TaskComplexity.SIMPLE:
            return 'direct'
        elif complexity == TaskComplexity.COMPLEX:
            return 'plan'
        elif complexity == TaskComplexity.STRATEGIC:
            return 'full_cycle'
        else:
            return 'direct'  # Default to direct execution
    
    def _on_tool_call(self, tool_calls: list, results: list) -> None:
        """Callback when tools are called."""
        logger.info(f"Tool calls executed: {len(tool_calls)}")
        for tc, res in zip(tool_calls, results):
            logger.debug(f"  {tc.get('name')}: success={res.get('success')}")
    
    def _on_thinking(self, message: str) -> None:
        """Callback when LLM is thinking."""
        logger.debug(f"Brain: {message}")
        # Show thinking indicator in console with timestamp
        if self.brain._thinking_callback_active and self.brain.thinking_start_time:
            elapsed = time.time() - self.brain.thinking_start_time
            print(f"\r[{message} {elapsed:.1f}s]", end="", flush=True)
        else:
            print(f"\r[{message}]", end="", flush=True)
    
    def _speak(self, text: str) -> None:
        """Speak text using TTS."""
        # Skip empty or whitespace-only text to avoid blank output
        if not text or not text.strip():
            return
            
        # Check both tts_enabled and voice_enabled config keys
        if self.config.get('tts_enabled', False) or self.config.get('voice_enabled', False):
            self.tts.speak(text)
    
    def _interaction_loop(self) -> None:
        """Main interaction loop for text/voice commands."""
        logger.info("Interaction loop started - type commands or 'quit' to exit")
        print("\n" + "="*60)
        print("JARVIS Ready! Type commands or 'quit' to exit")
        print("="*60)
        
        while self.running:
            try:
                # Get user input
                command = input("\nYou: ").strip()
                
                if not command:
                    continue
                
                if command.lower() in ['quit', 'exit', 'bye', 'goodbye']:
                    logger.info("User requested shutdown")
                    break
                
                # Handle special commands
                if command.lower() == 'show memory':
                    self._handle_show_memory()
                    continue
                elif command.lower() == 'show app context' or command.lower() == 'app context':
                    self._handle_show_app_context()
                    continue
                elif command.lower() == 'setup keys':
                    self._handle_setup_keys()
                    continue
                elif command.lower().startswith('search memory '):
                    query = command[14:].strip()
                    self._handle_search_memory(query)
                    continue
                
                # Process command
                result = self.process_command(command, voice=False)
                
                # Show result with thinking duration if available
                response = result.get('response', '')
                thinking_duration = result.get('total_thinking_time') or result.get('thinking_duration')
                
                if result.get('success'):
                    # Successful completion - show response
                    if thinking_duration:
                        print(f"\nJARVIS: {response}  [Thought for {thinking_duration:.2f}s]")
                    else:
                        print(f"\nJARVIS: {response}")
                elif response:
                    # Partial success or informative response even with failure
                    # (response text already includes error details)
                    if thinking_duration:
                        print(f"\nJARVIS: {response}  [Thought for {thinking_duration:.2f}s]")
                    else:
                        print(f"\nJARVIS: {response}")
                else:
                    # Complete failure with no response - show error
                    error_msg = result.get('error', 'Unknown error occurred')
                    print(f"\nJARVIS: [Error] {error_msg}")
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                break
            except EOFError:
                logger.info("EOF received")
                break
            except Exception as e:
                logger.error(f"Interaction loop error: {e}", exc_info=True)
                print(f"\nError: {e}")
    
    def _handle_show_memory(self):
        """Display recent conversation history."""
        print("\n=== Recent Memory ===")
        recent = self.persistent_memory.get_recent_conversations(limit=5)
        if not recent:
            print("No conversations stored yet.")
        else:
            for i, record in enumerate(recent, 1):
                print(f"\n{i}. [{record['timestamp'][:16]}]")
                print(f"   You: {record['user'][:80]}...")
                print(f"   JARVIS: {record['assistant'][:80]}...")
        print()
    
    def _handle_show_app_context(self):
        """Display current app context tracking info."""
        app_ctx = self.get_app_context()
        print("\n=== App Context Tracking ===")
        print(f"Current App: {app_ctx.get('current_app', 'unknown')}")
        print(f"Last Active App: {app_ctx.get('last_active_app', 'unknown')}")
        print(f"\nRecent App Switches ({len(app_ctx.get('recent_app_switches', []))}):")
        for i, switch in enumerate(app_ctx.get('recent_app_switches', [])[-5:], 1):
            print(f"  {i}. {switch['time']}: {switch['from_app']} → {switch['to_app']}")
        print()
    
    def _handle_search_memory(self, query: str):
        """Search memory for relevant past conversations."""
        print(f"\n=== Searching Memory for: '{query}' ===")
        results = self.persistent_memory.search_memories(query, n_results=5)
        if not results:
            print("No matching memories found.")
        else:
            for i, record in enumerate(results, 1):
                score = record.get('relevance_score', 'N/A')
                print(f"\n{i}. [Relevance: {score:.4f}] [{record['timestamp'][:16]}]")
                print(f"   You: {record['user']}")
                print(f"   JARVIS: {record['assistant']}")
        print()
    
    def _handle_setup_keys(self):
        """Interactive API key setup."""
        from jarvis.security.vault import setup_api_keys
        setup_api_keys(self.vault)
    
    def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self.running:
            try:
                # Check system health
                # Update ambient state
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
    
    def set_mode(self, mode: str) -> None:
        """
        Set operating mode.
        
        Args:
            mode: 'unified', 'chat', or 'agent' (chat/agent kept for backward compatibility but unified is default)
        """
        if mode in ['chat', 'agent', 'unified']:
            self.mode = mode
            logger.info(f"Mode set to: {mode}")
        else:
            logger.warning(f"Invalid mode: {mode}")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current orchestrator state."""
        return self.state.copy()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive stats."""
        return {
            'orchestrator': self.state,
            'memory': self.memory.get_memory_stats(),
            'tools': {
                'available': len(self.tool_registry.tools),
                'loaded': list(self.tool_registry.tools.keys())
            },
            'skills': {
                'available': len(self.skill_registry.skills),
                'loaded': list(self.skill_registry.skills.keys())
            }
        }


def run_orchestrator(config: Dict[str, Any]) -> None:
    """
    Run the JARVIS orchestrator.
    
    Args:
        config: Configuration dict
    """
    orchestrator = Orchestrator(config)
    
    try:
        orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        orchestrator.stop()
