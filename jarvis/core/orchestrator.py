"""
Main Orchestrator Module

The central coordinator for JARVIS that:
- Manages the main event loop
- Coordinates perception, reasoning, and execution
- Handles voice input/output
- Manages system state and modes
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from jarvis.core.memory import CoreMemory
from jarvis.core.context import ContextAssembler
from jarvis.core.brain import Brain
from jarvis.tools.registry import ToolRegistry
from jarvis.skills.registry import SkillRegistry
from jarvis.safety.tool_guard import ToolGuard
from jarvis.safety.audit_log import AuditLog
from jarvis.perception.intent_classifier import IntentClassifier
from jarvis.perception.vision import VisionAnalyzer
from jarvis.reasoning.planner import TaskPlanner
from jarvis.reasoning.critic import PlanCritic
from jarvis.reasoning.reflector import Reflector as OutcomeReflector
from jarvis.reasoning.strategy_selector import StrategySelector
# TTS Manager - use simple wrapper for now
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

logger = logging.getLogger(__name__)


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
        
        # Tool registry
        self.tool_registry = ToolRegistry(config)
        self.tool_registry.load_all_tools()
        
        # Skill registry
        self.skill_registry = SkillRegistry(config)
        self.skill_registry.load_skills()
        
        # Safety systems
        self.tool_guard = ToolGuard(config)
        self.audit_log = AuditLog(config)
        
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
        self.intent_classifier = IntentClassifier(config, self.brain)
        self.vision_analyzer = VisionAnalyzer(config, self.brain)
        
        # Reasoning
        self.planner = TaskPlanner(config, self.brain)
        self.critic = PlanCritic(config, self.brain)
        self.reflector = OutcomeReflector(config, self.brain)
        self.strategy_selector = StrategySelector(config)
        
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
        
        # Threads
        self.input_thread = None
        self.monitoring_thread = None
        
        logger.info("JARVIS orchestrator initialized successfully")
    
    def start(self) -> None:
        """Start the orchestrator main loop."""
        if self.running:
            logger.warning("Orchestrator already running")
            return
        
        self.running = True
        logger.info("Starting JARVIS orchestrator...")
        
        # Speak startup message
        self._speak("JARVIS online. Ready to assist.")
        
        # Start monitoring thread
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        # Start main interaction loop
        self._interaction_loop()
    
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
            # Add to memory
            self.memory.add_user_message(command, metadata={'source': 'voice' if voice else 'text'})
            
            # Classify intent (chat vs agent mode)
            intent = self.intent_classifier.classify(command)
            intended_mode = intent.get('mode', 'agent')
            
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
            
            # Store experience
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
        
        Args:
            command: User command
            
        Returns:
            Response dict
        """
        logger.info(f"Handling in chat mode: {command[:50]}...")
        
        system_prompt = get_system_prompt(mode='chat')
        
        response = self.brain.chat(
            messages=[{'role': 'user', 'content': command}],
            system_prompt=system_prompt,
            temperature=0.7
        )
        
        if response['success']:
            response_text = response['content']
            self.memory.add_assistant_message(response_text)
            self._speak(response_text)
            
            return {
                'success': True,
                'response': response_text,
                'mode': 'chat',
                'actions': []
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
        
        Args:
            command: User command
            
        Returns:
            Response dict
        """
        logger.info(f"Handling in agent mode: {command[:50]}...")
        
        # Select reasoning strategy
        strategy = self.strategy_selector.select_strategy(command)
        logger.info(f"Selected strategy: {strategy}")
        
        system_prompt = get_system_prompt(mode='agent')
        
        # Simple direct execution for straightforward commands
        if strategy == 'direct':
            return self._execute_direct(command, system_prompt)
        
        # Planning required
        elif strategy == 'plan':
            return self._execute_with_planning(command, system_prompt)
        
        # Full cycle with review
        elif strategy == 'full_cycle':
            return self._execute_full_cycle(command, system_prompt)
        
        # Default to direct
        return self._execute_direct(command, system_prompt)
    
    def _execute_direct(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """Execute command directly with tool calling."""
        response = self.brain.chat_with_tools(
            user_message=command,
            system_prompt=system_prompt,
            max_iterations=5
        )
        
        if response['success']:
            response_text = response['content']
            self.memory.add_assistant_message(response_text)
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
            return {
                'success': False,
                'error': response.get('error', 'Execution failed'),
                'response': "I couldn't complete that task.",
                'mode': 'agent',
                'strategy': 'direct',
                'actions': [],
                'iterations': response.get('iterations', 0)
            }
    
    def _execute_with_planning(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """Execute command with planning phase."""
        # Generate plan
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
        
        # Review plan
        critique = self.critic.review_plan(plan, command)
        
        # Execute plan steps
        executed_steps = []
        for step in plan:
            tool_name = step.get('tool')
            arguments = step.get('arguments', {})
            
            # Validate with tool guard
            validation = self.tool_guard.validate_tool_call(tool_name, arguments)
            if not validation.get('allowed', True):
                logger.warning(f"Tool call blocked by guard: {tool_name}")
                continue
            
            # Execute
            result = self.tool_registry.execute(tool_name, **arguments)
            executed_steps.append({
                'step': step,
                'result': result
            })
            
            # Add to memory
            self.memory.add_tool_result(tool_name, result)
        
        # Reflect on outcome
        reflection = self.reflector.analyze_outcome(
            goal=command,
            plan=plan,
            results=executed_steps
        )
        
        # Generate response
        response_text = f"Task completed. {reflection.get('summary', '')}"
        self.memory.add_assistant_message(response_text)
        self._speak(response_text)
        
        return {
            'success': True,
            'response': response_text,
            'mode': 'agent',
            'strategy': 'plan',
            'actions': executed_steps,
            'plan': plan,
            'critique': critique,
            'reflection': reflection
        }
    
    def _execute_full_cycle(self, command: str, system_prompt: str) -> Dict[str, Any]:
        """Execute with full planning, review, and reflection cycle."""
        # This would implement the most thorough execution path
        # For now, delegate to planning execution
        return self._execute_with_planning(command, system_prompt)
    
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
        if self.config.get('tts_enabled', True):
            self.tts.speak(text)
    
    def _interaction_loop(self) -> None:
        """Main interaction loop for voice commands."""
        # This would integrate with STT and wake word detection
        # For now, it's a placeholder for the voice input pipeline
        logger.info("Interaction loop started (waiting for voice input integration)")
    
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
