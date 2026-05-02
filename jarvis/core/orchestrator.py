"""
Main Orchestrator Module

The central coordinator for JARVIS that:
- Manages the main event loop
- Coordinates perception, reasoning, and execution
- Handles voice input/output
- Manages system state and modes
- Implements full pipeline: listen → transcribe → classify → retrieve → 
  select strategy → plan if complex → critic review → execute → reflect → store → respond
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
import queue

from jarvis.core.memory import CoreMemory
from jarvis.core.context import ContextAssembler
from jarvis.core.brain import Brain
from jarvis.tools.registry import ToolRegistry
from jarvis.skills.registry import SkillsRegistry as SkillRegistry
from jarvis.safety import InputFilter, PlanValidator, ToolGuard, AuditLog
from jarvis.perception.intent_classifier import IntentClassifier
from jarvis.perception.vision import VisionAnalyzer
from jarvis.reasoning.planner import TaskPlanner
from jarvis.reasoning.critic import PlanCritic
from jarvis.reasoning.reflector import Reflector as OutcomeReflector
from jarvis.reasoning.strategy_selector import StrategySelector, TaskComplexity
from jarvis.monitoring.ambient import get_ambient_monitor, start_monitoring
from jarvis.config.config import get_config

# Constants
MAX_AGENT_ROUNDS = 8
MAX_CONSECUTIVE_FAILURES = 3
CACHE_TTL_SECONDS = 5

logger = logging.getLogger(__name__)


class TTSManager:
    """Simple TTS wrapper that delegates to the existing tts module."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize TTS manager."""
        self.config = config
        self.enabled = config.get('tts_enabled', True)
        
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
            logger.warning(f"TTS not available: {e}")
            print(f"JARVIS: {text}")


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
        self.mode = 'agent'  # 'chat' or 'agent'
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
        self.tool_guard = ToolGuard()
        self.audit_log = AuditLog()
        
        # Memory system
        self.memory = CoreMemory(config)
        
        # Context assembler
        self.context_assembler = ContextAssembler(
            config=config,
            memory_system=self.memory,
            tool_registry=self.tool_registry,
            skill_registry=self.skill_registry
        )
        
        # Brain (LLM coordinator)
        self.brain = Brain(config, self.tool_registry)
        self.brain.set_callbacks(
            on_tool_call=self._on_tool_call,
            on_thinking=self._on_thinking
        )
        
        # Perception
        self.intent_classifier = IntentClassifier(self.brain.client)
        self.vision_analyzer = VisionAnalyzer(self.brain.client)
        
        # Reasoning
        self.planner = TaskPlanner(ollama_client=self.brain.client, tool_registry=self.tool_registry)
        self.critic = PlanCritic(ollama_client=self.brain.client)
        self.reflector = OutcomeReflector(ollama_client=self.brain.client, memory_manager=self.memory)
        self.strategy_selector = StrategySelector()
        
        # Output
        self.tts = TTSManager(config)
        
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
        
        # Timer monitor thread
        timer_thread = threading.Thread(target=self._timer_monitor_loop, daemon=True)
        timer_thread.start()
        self.ambient_monitors.append(timer_thread)
        
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
        """Monitor user idle time in background."""
        last_activity = time.time()
        while self.running:
            try:
                # Check if user is idle (no input for extended period)
                idle_time = time.time() - last_activity
                if idle_time > 300:  # 5 minutes
                    logger.debug(f"User idle for {idle_time:.0f} seconds")
            except Exception as e:
                logger.debug(f"Idle monitor error: {e}")
            time.sleep(60)  # Check every minute
    
    def _timer_monitor_loop(self) -> None:
        """Monitor timers and scheduled tasks in background."""
        while self.running:
            try:
                # Check for any pending timers or scheduled tasks
                # This would integrate with a scheduler if present
                pass
            except Exception as e:
                logger.debug(f"Timer monitor error: {e}")
            time.sleep(5)  # Check every 5 seconds
    
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
        
        try:
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
            
            # Classify intent (chat vs agent mode) BEFORE adding to memory
            intent = self.intent_classifier.classify(command)
            intended_mode = intent.get('mode', 'agent')
            
            # Add to memory only for agent mode (to reduce memory usage)
            if intended_mode == 'agent':
                self.memory.add_user_message(command, metadata={'source': 'voice' if voice else 'text'})
            
            # Route based on intent
            if intended_mode == 'chat' or self.mode == 'chat':
                result = self._handle_chat_mode(command)
            else:
                result = self._handle_agent_mode(command)
            
            # Update state
            self.state['total_interactions'] += 1
            if result.get('success'):
                self.state['successful_tasks'] += 1
            else:
                self.state['failed_tasks'] += 1
            
            # Store experience only for significant tasks (not simple chat)
            if result.get('mode') == 'agent' and result.get('actions'):
                self.memory.store_experience(
                    goal=command,
                    actions=result.get('actions', []),
                    outcome=result.get('response', ''),
                    success=result.get('success', False)
                )
            
            # Audit log
            self.audit_log.log_action(
                action_type='user_command',
                details={
                    'command': command,
                    'mode': self.mode,
                    'intent': intent,
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
        
        system_prompt = get_system_prompt(mode='chat')
        
        # Use streaming for low latency
        response = self.brain.chat(
            messages=[{'role': 'user', 'content': command}],
            system_prompt=system_prompt,
            temperature=0.7,
            stream=True  # Enable streaming for low latency
        )
        
        if response['success']:
            response_text = response['content']
            # Don't store assistant messages in chat mode to reduce memory usage
            
            # Start speaking immediately for low latency (before full response if streaming)
            self._speak(response_text)
            
            return {
                'success': True,
                'response': response_text,
                'mode': 'chat',
                'actions': [],
                'streamed': True
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
        Handle agent mode - full reasoning and tool execution.
        
        Implements the full pipeline:
        retrieve memories → select strategy → plan if complex → critic review → execute → reflect → store → respond
        
        Args:
            command: User command
            
        Returns:
            Response dict
        """
        logger.info(f"Handling in agent mode: {command[:50]}...")
        
        # Clear abort flag for new task
        self.clear_abort()
        
        # Retrieve relevant memories
        context = self.memory.retrieve_context(query=command)
        memories = context.get('episodic', []) + context.get('semantic', []) + context.get('procedural', [])
        logger.debug(f"Retrieved {len(memories)} relevant memories")
        
        # Select reasoning strategy based on task complexity
        classification = self.strategy_selector.classify(command)
        strategy = self._map_complexity_to_strategy(classification.complexity)
        logger.info(f"Selected strategy: {strategy} (complexity: {classification.complexity.value})")
        
        system_prompt = get_system_prompt(mode='agent')
        
        # Track consecutive failures
        task_key = hash(command) % 10000
        
        # Simple direct execution for straightforward commands (trivial/simple tasks)
        if strategy == 'direct':
            result = self._execute_direct(command, system_prompt)
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
            # Don't store assistant messages to reduce memory usage
            
            # Start speaking before full response is generated for low latency
            self._speak(response_text)
            
            return {
                'success': True,
                'response': response_text,
                'mode': 'agent',
                'strategy': 'direct',
                'actions': response.get('tool_calls', []),
                'iterations': response.get('iterations', 0)
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
        Execute command with planning phase.
        
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
        
        plan = plan_result.get('plan', [])
        
        # Phase 3 Safety: Plan validation (second safety layer)
        plan_validation = self.plan_validator.review(plan)
        
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
        critique = self.critic.review_plan(plan, command)
        
        # Handle critic results
        if critique.get('verdict') == 'BLOCKED':
            logger.warning(f"Plan blocked by critic: {critique.get('reason', 'Unknown')}")
            return {
                'success': False,
                'error': 'Plan blocked by critic',
                'response': f"I cannot proceed: {critique.get('reason', 'The plan has issues.')}",
                'mode': 'agent',
                'strategy': 'plan',
                'actions': [],
                'critique': critique
            }
        
        elif critique.get('verdict') == 'NEEDS_REVISION':
            logger.info(f"Plan needs revision: {critique.get('fixes_needed', [])}")
            # Attempt to fix the plan
            revised_plan = self.planner.revise_plan(command, plan, critique.get('fixes_needed', []))
            if revised_plan.get('success'):
                plan = revised_plan.get('plan', plan)
                logger.info("Plan revised successfully")
            else:
                logger.warning("Plan revision failed, proceeding with original plan")
        
        # Execute plan steps with safety validation and abort checking
        executed_steps = []
        for idx, step in enumerate(plan):
            # Check for abort during execution
            if self.check_abort():
                logger.info("Execution aborted by user")
                # Rollback completed steps
                self._rollback_steps(executed_steps)
                return {
                    'success': False,
                    'error': 'Task aborted by user',
                    'response': "Task cancelled. Changes rolled back.",
                    'mode': 'agent',
                    'strategy': 'plan',
                    'actions': executed_steps
                }
            
            tool_name = step.get('tool')
            arguments = step.get('arguments', {})
            
            # Phase 3 Safety: Tool guard validation (third safety layer)
            validation = self.tool_guard.validate_tool_call(tool_name, arguments)
            if not validation.get('allowed', True):
                logger.warning(f"Tool call blocked by guard at step {idx}: {tool_name} - {validation.get('reason', 'Unknown')}")
                self.audit_log.log_security_event(
                    event_type='tool_blocked',
                    details={
                        'step_index': idx,
                        'tool': tool_name,
                        'reason': validation.get('reason', 'Unknown'),
                        'parameters': arguments
                    }
                )
                continue
            
            # Execute
            result = self.tool_registry.execute(tool_name, **arguments)
            executed_steps.append({
                'step': step,
                'result': result,
                'validated': True
            })
            
            # Don't add tool results to memory to reduce memory usage
        
        # Skip reflection to reduce memory usage
        # self.reflector.reflect(...)
        
        # Generate response
        response_text = f"Task completed. Steps executed: {len(executed_steps)}"
        # Don't store assistant message to reduce memory usage
        self._speak(response_text)
        
        return {
            'success': True,
            'response': response_text,
            'mode': 'agent',
            'strategy': 'plan',
            'actions': executed_steps,
            'plan': plan,
            'critique': critique
        }
    
    def _rollback_steps(self, executed_steps: List[Dict]) -> None:
        """Rollback executed steps in reverse order."""
        logger.info(f"Rolling back {len(executed_steps)} steps")
        for step_info in reversed(executed_steps):
            step = step_info.get('step', {})
            tool_name = step.get('tool')
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
    
    def _speak(self, text: str) -> None:
        """Speak text using TTS."""
        # Skip empty or whitespace-only text to avoid blank output
        if not text or not text.strip():
            return
            
        if self.config.get('tts_enabled', True):
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
                
                # Process command
                result = self.process_command(command, voice=False)
                
                # Show result
                if result.get('success'):
                    print(f"\nJARVIS: {result.get('response', '')}")
                else:
                    print(f"\nJARVIS: [Error] {result.get('error', 'Unknown error')}")
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                break
            except EOFError:
                logger.info("EOF received")
                break
            except Exception as e:
                logger.error(f"Interaction loop error: {e}", exc_info=True)
                print(f"\nError: {e}")
    
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
            mode: 'chat' or 'agent'
        """
        if mode in ['chat', 'agent']:
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
