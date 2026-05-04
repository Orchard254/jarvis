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
from jarvis.core.react_agent import ReActAgent
from jarvis.core.predictive_planner import PredictivePlanner
from jarvis.tools.registry import ToolRegistry
from jarvis.skills.registry import SkillsRegistry as SkillRegistry
from jarvis.safety import InputFilter, PlanValidator, ToolGuard, AuditLog
from jarvis.perception.intent_classifier import IntentClassifier
from jarvis.perception.vision import VisionAnalyzer
from jarvis.reasoning.planner import TaskPlanner
from jarvis.reasoning.critic import PlanCritic, CriticDecision
from jarvis.reasoning.reflector import Reflector as OutcomeReflector
from jarvis.reasoning.strategy_selector import StrategySelector, TaskComplexity
from jarvis.monitoring.ambient import get_ambient_monitor, start_monitoring
from jarvis.config.config import get_config
from jarvis.memory.persistent import PersistentMemory
from jarvis.security.vault import CredentialVault

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
        self.plan_validator.tool_registry = self.tool_registry
        self.tool_guard = ToolGuard()
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
            skill_registry=self.skill_registry
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
            
            # Route based on intent - but respect explicit agent mode override
            # If system is already in agent mode, stay in agent mode unless explicitly told to chat
            if self.mode == 'agent' and intended_mode != 'chat':
                # Stay in agent mode for consecutive commands
                result = self._handle_agent_mode(command)
            elif intended_mode == 'chat':
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
                
                # Also store in persistent memory with RAG
                try:
                    self.persistent_memory.add_experience(
                        user_input=command,
                        assistant_response=result.get('response', ''),
                        context={
                            'success': result.get('success', False),
                            'actions_count': len(result.get('actions', [])),
                            'mode': 'agent'
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to store in persistent memory: {e}")
            
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
        
        # Track consecutive failures
        task_key = hash(command) % 10000
        
        # PREDICTIVE EXECUTION: Use LLM's internal knowledge for direct execution
        # This bypasses ReAct loops for tasks where the LLM already knows the answer
        if strategy in ['direct', 'plan']:
            logger.info(f"[Predictive] Using LLM's internal knowledge for direct execution...")
            
            # Generate predictive plan using LLM's world knowledge
            tools_dict = {name: {'description': getattr(tool, 'description', '')} 
                         for name, tool in self.tool_registry.get_all_tools().items()}
            
            plan = self.predictive_planner.generate_plan(command, tools_dict)
            
            if plan and plan.get('steps'):
                logger.info(f"Generated predictive plan with {len(plan['steps'])} steps (confidence: {plan.get('confidence', 'unknown')})")
                
                # Execute the plan directly
                result = self.predictive_planner.execute_plan(plan, self.tool_registry)
                
                return {
                    'success': result['success'],
                    'response': result.get('summary', ''),
                    'mode': 'predictive',
                    'strategy': 'predictive',
                    'actions': plan.get('steps', []),
                    'iterations': len(plan.get('steps', []))
                }
            
            # Fallback to ReAct if predictive planning fails
            logger.warning("Predictive planning failed, falling back to ReAct agent...")
        
        # Traditional ReAct agent fallback
        if strategy == 'direct':
            logger.info(f"[ReAct] Using autonomous agent mode for: {command[:50]}...")
            react_result = self.react_agent.execute(command, context=memories)
            result = {
                'success': True,
                'response': react_result,
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
        
        plan = [step.to_dict() for step in execution_graph.steps]
        
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
            revised_plan = self.planner.revise_plan(command, plan, critique.fixes_needed)
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
            
            # Extract tool name and arguments from step (handle both formats)
            # LLM may output 'tool_or_skill'/'params' or 'tool'/'arguments'
            tool_name = step.get('tool') or step.get('tool_or_skill')
            arguments = step.get('arguments', {}) or step.get('params', {})
            
            # Phase 3 Safety: Tool guard validation (third safety layer)
            is_valid, error_msg = self.tool_guard.validate_tool_call(tool_name, arguments)
            if not is_valid:
                logger.warning(f"Tool call blocked by guard at step {idx}: {tool_name} - {error_msg}")
                self.audit_log.log_security_event(
                    event_type='tool_blocked',
                    details={
                        'step_index': idx,
                        'tool': tool_name,
                        'reason': error_msg,
                        'parameters': arguments
                    }
                )
                continue
            
            # Execute with retry logic
            result = None
            max_retries = 2
            for attempt in range(max_retries):
                result = self.tool_registry.execute(tool_name, **arguments)
                
                if result.success:
                    break
                    
                # Retry on failure with exponential backoff
                if attempt < max_retries - 1:
                    logger.warning(f"Tool {tool_name} failed (attempt {attempt + 1}/{max_retries}), retrying...")
                    time.sleep(0.5 * (attempt + 1))
                else:
                    logger.error(f"Tool {tool_name} failed after {max_retries} attempts")
            
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
            'critique': critique.to_dict()
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
                elif command.lower() == 'setup keys':
                    self._handle_setup_keys()
                    continue
                elif command.lower().startswith('search memory '):
                    query = command[14:].strip()
                    self._handle_search_memory(query)
                    continue
                
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
