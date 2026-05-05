"""
core/orchestrator_resilient_patch.py — Orchestrator Integration for Resilient Tool System

This patch shows how to integrate the resilient tool routing system into the main orchestrator.

NEW EXECUTION FLOW:
===================
Input → Intent Detection → Direct Match? → Yes → Execute
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

USAGE:
======
Add these methods to your Orchestrator class:

    def __init__(self, config):
        # ... existing init code ...
        
        # Add resilient router (NEW)
        from jarvis.tools.resilient_router import ResilientToolRouter, ExecutionFeedbackLoop
        self.tool_router = ResilientToolRouter(registry=self.tool_registry)
        self.feedback_loop = ExecutionFeedbackLoop(registry=self.tool_registry)
    
    def process_command(self, user_input: str) -> Dict[str, Any]:
        # Replace existing tool handling with this
        return self._resilient_tool_route(user_input)
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger("orchestrator_patch")


class ResilientOrchestratorMixin:
    """
    Mixin class providing resilient tool routing for the main Orchestrator.
    
    Usage:
        class Orchestrator(ResilientOrchestratorMixin, ExistingBaseClass):
            pass
    """
    
    def __init_resilient_mixin(self):
        """
        Initialize resilient routing components.
        
        Call this from your Orchestrator.__init__ after self.tool_registry is set.
        """
        from jarvis.tools.resilient_router import ResilientToolRouter, ExecutionFeedbackLoop
        
        self.tool_router = ResilientToolRouter(registry=self.tool_registry)
        self.feedback_loop = ExecutionFeedbackLoop(registry=self.tool_registry)
        
        # Track LLM availability
        self._llm_available = True
        self._last_llm_check = 0
        
        logger.info("Resilient tool routing initialized")
    
    def _check_llm_availability(self) -> bool:
        """
        Check if LLM is available and responsive.
        
        Returns:
            True if LLM is available, False otherwise
        """
        # Simple check - can be enhanced with actual ping/timeout logic
        try:
            if hasattr(self, 'brain') and self.brain:
                # Could add a quick health check here
                self._llm_available = True
            else:
                self._llm_available = False
        except Exception as e:
            logger.warning(f"LLM health check failed: {e}")
            self._llm_available = False
        
        return self._llm_available
    
    def _resilient_tool_route(self, user_input: str) -> Dict[str, Any]:
        """
        Main resilient routing function - replaces old tool handling.
        
        Implements the full resilient flow:
        1. Intent detection
        2. Direct tool match (fast path)
        3. LLM-based routing (if needed)
        4. Validation
        5. Execution with feedback
        6. Verification
        
        Args:
            user_input: User's natural language input
            
        Returns:
            Result dict with success, response, and metadata
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Route the input
            routing_decision = self.tool_router.route(
                user_input,
                llm_available=self._check_llm_availability()
            )
            
            action = routing_decision.get('action')
            
            # Step 2: Handle different routing decisions
            if action == 'execute_direct':
                # Fast path - direct tool execution without LLM
                tool_name = routing_decision['tool']
                args = routing_decision['args']
                
                success, result, message = self._execute_with_feedback(tool_name, args)
                
                return {
                    'success': success,
                    'response': message if not success else str(result),
                    'action': 'direct_execute',
                    'tool': tool_name,
                    'duration': (datetime.now() - start_time).total_seconds(),
                }
            
            elif action == 'clarify':
                # Low confidence - ask for clarification
                question = routing_decision['question']
                candidates = routing_decision.get('candidates', [])
                
                return {
                    'success': False,
                    'requires_clarification': True,
                    'question': question,
                    'candidates': candidates,
                    'action': 'clarify',
                }
            
            elif action == 'respond':
                # Chat/conversation - no tool needed
                message = routing_decision['message']
                
                # If message indicates LLM response needed, delegate to brain
                if routing_decision.get('requires_llm', False):
                    llm_response = self._invoke_llm_chat(user_input)
                    return {
                        'success': True,
                        'response': llm_response,
                        'action': 'chat',
                        'duration': (datetime.now() - start_time).total_seconds(),
                    }
                
                return {
                    'success': True,
                    'response': message,
                    'action': 'direct_respond',
                }
            
            elif action == 'llm_plan':
                # Need LLM to choose/refine tool call
                return self._handle_llm_planning(user_input, routing_decision)
            
            elif action == 'error':
                # Routing error
                return {
                    'success': False,
                    'response': routing_decision['message'],
                    'suggestion': routing_decision.get('suggestion', ''),
                    'action': 'error',
                }
            
            else:
                logger.error(f"Unknown routing action: {action}")
                return {
                    'success': False,
                    'response': 'Internal routing error',
                    'action': 'error',
                }
        
        except Exception as e:
            logger.exception(f"Resilient routing failed: {e}")
            return {
                'success': False,
                'response': f'Error processing request: {str(e)}',
                'action': 'exception',
            }
    
    def _handle_llm_planning(
        self,
        user_input: str,
        routing_decision: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Handle LLM-based planning with filtered tool candidates.
        
        Args:
            user_input: Original user input
            routing_decision: Routing decision from tool_router
            
        Returns:
            Result dict
        """
        candidates = routing_decision['candidates']
        prompt = routing_decision['prompt']
        
        # Get filtered schemas for the candidate tools
        filtered_schemas = []
        for tool_name in candidates:
            schema = self.tool_registry.get_schema_for_tool(tool_name)
            if schema:
                filtered_schemas.append(schema)
        
        # Build prompt with only relevant tools (3 max)
        system_prompt = self._build_filtered_system_prompt(filtered_schemas)
        
        # Invoke LLM with filtered tools
        try:
            llm_response = self._invoke_llm_with_tools(
                user_input,
                system_prompt,
                filtered_schemas
            )
            
            # Parse LLM response
            parsed = self._parse_llm_response(llm_response)
            
            if not parsed:
                return {
                    'success': False,
                    'response': "Couldn't understand the response. Please try again.",
                    'action': 'parse_error',
                }
            
            # Handle different parsed actions
            action_type = parsed.get('action')
            
            if action_type == 'tool_call':
                tool_name = parsed['tool']
                args = parsed['args']
                
                # Validate before execution
                is_valid, error_msg = self._validate_tool_call(tool_name, args)
                if not is_valid:
                    return {
                        'success': False,
                        'response': f'Invalid tool call: {error_msg}',
                        'action': 'validation_error',
                    }
                
                # Execute with feedback loop
                success, result, message = self._execute_with_feedback(tool_name, args)
                
                return {
                    'success': success,
                    'response': message if not success else str(result),
                    'action': 'tool_execute',
                    'tool': tool_name,
                }
            
            elif action_type == 'respond':
                return {
                    'success': True,
                    'response': parsed['message'],
                    'action': 'llm_respond',
                }
            
            elif action_type == 'plan':
                # Multi-step plan
                return self._execute_multi_step_plan(parsed['steps'], user_input)
            
            else:
                return {
                    'success': False,
                    'response': f'Unknown action type: {action_type}',
                    'action': 'unknown_action',
                }
        
        except Exception as e:
            logger.exception(f"LLM planning failed: {e}")
            return {
                'success': False,
                'response': f'Planning error: {str(e)}',
                'action': 'planning_error',
            }
    
    def _execute_with_feedback(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, Any, str]:
        """
        Execute tool with verification and retry logic.
        
        Args:
            tool_name: Tool to execute
            args: Tool arguments
            
        Returns:
            Tuple of (success, result, message)
        """
        # Use the feedback loop for execution
        success, result, message = self.feedback_loop.execute_with_feedback(
            tool_name,
            args,
            verify_result=True
        )
        
        if success:
            logger.info(f"Tool {tool_name} executed successfully")
        else:
            logger.warning(f"Tool {tool_name} failed: {message}")
        
        return success, result, message
    
    def _validate_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Validate tool call using the validator.
        
        Args:
            tool_name: Tool name
            args: Tool arguments
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        from jarvis.tools.validator import validate_tool_call
        
        return validate_tool_call(tool_name, args)
    
    def _parse_llm_response(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse LLM response using the strict JSON parser.
        
        Args:
            llm_response: Raw LLM output
            
        Returns:
            Parsed dict or None if parsing failed
        """
        from jarvis.core.tool_call_parser import parse_tool_call_json
        
        parsed, error = parse_tool_call_json(llm_response)
        
        if parsed:
            return parsed
        
        logger.warning(f"Failed to parse LLM response: {error}")
        return None
    
    def _build_filtered_system_prompt(self, filtered_schemas: List[Dict]) -> str:
        """
        Build system prompt with only filtered tool schemas.
        
        Args:
            filtered_schemas: List of tool schemas (already filtered)
            
        Returns:
            System prompt string
        """
        from jarvis.core.tool_call_parser import build_system_prompt_with_tools
        
        return build_system_prompt_with_tools(filtered_schemas, max_examples=3)
    
    def _invoke_llm_with_tools(
        self,
        user_input: str,
        system_prompt: str,
        tool_schemas: List[Dict],
    ) -> str:
        """
        Invoke LLM with filtered tool schemas.
        
        Args:
            user_input: User's input
            system_prompt: System prompt with tool definitions
            tool_schemas: Filtered tool schemas
            
        Returns:
            LLM response string
        """
        # This depends on your existing LLM interface
        # Example using brain/client:
        if hasattr(self, 'brain') and self.brain:
            # Build messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
            
            # Call LLM with tool support if available
            if hasattr(self.brain, 'client') and self.brain.client:
                response = self.brain.client.generate(
                    messages=messages,
                    # Add tool-specific parameters if your client supports it
                )
                return response
            
            # Fallback to simple generation
            prompt = f"{system_prompt}\n\nUser: {user_input}"
            return self.brain.generate(prompt)
        
        raise RuntimeError("No LLM interface available")
    
    def _invoke_llm_chat(self, user_input: str) -> str:
        """
        Invoke LLM for chat/conversation (no tools).
        
        Args:
            user_input: User's input
            
        Returns:
            LLM response string
        """
        if hasattr(self, 'brain') and self.brain:
            messages = [
                {"role": "system", "content": "You are JARVIS, a helpful AI assistant."},
                {"role": "user", "content": user_input}
            ]
            
            if hasattr(self.brain, 'client') and self.brain.client:
                response = self.brain.client.generate(messages=messages)
                return response
            
            return self.brain.generate(user_input)
        
        return "I'm here to help! (LLM not available)"
    
    def _execute_multi_step_plan(
        self,
        steps: List[Dict[str, Any]],
        goal: str,
    ) -> Dict[str, Any]:
        """
        Execute a multi-step plan.
        
        Args:
            steps: List of step dicts with tool, args, description
            goal: Overall goal description
            
        Returns:
            Result dict
        """
        results = []
        success_count = 0
        
        for i, step in enumerate(steps):
            tool_name = step.get('tool')
            args = step.get('args', {})
            description = step.get('description', f'Step {i+1}')
            
            if not tool_name:
                return {
                    'success': False,
                    'response': f'Step {i+1} missing tool name',
                    'action': 'plan_error',
                }
            
            # Validate step
            is_valid, error_msg = self._validate_tool_call(tool_name, args)
            if not is_valid:
                return {
                    'success': False,
                    'response': f'Step {i+1} ({description}) failed validation: {error_msg}',
                    'action': 'plan_validation_error',
                    'completed_steps': i,
                }
            
            # Execute step
            success, result, message = self._execute_with_feedback(tool_name, args)
            
            results.append({
                'step': i + 1,
                'description': description,
                'success': success,
                'result': str(result) if result else message,
            })
            
            if success:
                success_count += 1
            else:
                # Stop on first failure
                return {
                    'success': False,
                    'response': f'Step {i+1} failed: {message}',
                    'action': 'plan_execution_error',
                    'completed_steps': i,
                    'results': results,
                }
        
        # All steps completed successfully
        return {
            'success': True,
            'response': f'Completed all {len(steps)} steps successfully.',
            'action': 'plan_complete',
            'results': results,
            'goal': goal,
        }


# =============================================================================
# CONVENIENCE FUNCTIONS FOR PATCHING EXISTING ORCHESTRATOR
# =============================================================================

def patch_orchestrator(orchestrator_instance) -> None:
    """
    Patch an existing Orchestrator instance with resilient routing.
    
    Usage:
        orchestrator = Orchestrator(config)
        patch_orchestrator(orchestrator)
    
    Args:
        orchestrator_instance: Existing Orchestrator instance
    """
    mixin = ResilientOrchestratorMixin()
    
    # Bind methods to the instance
    orchestrator_instance._resilient_tool_route = \
        lambda user_input: ResilientOrchestratorMixin._resilient_tool_route(mixin, user_input)
    orchestrator_instance._handle_llm_planning = \
        lambda user_input, routing: ResilientOrchestratorMixin._handle_llm_planning(mixin, user_input, routing)
    orchestrator_instance._execute_with_feedback = \
        lambda tool, args: ResilientOrchestratorMixin._execute_with_feedback(mixin, tool, args)
    orchestrator_instance._validate_tool_call = \
        lambda tool, args: ResilientOrchestratorMixin._validate_tool_call(mixin, tool, args)
    orchestrator_instance._parse_llm_response = \
        lambda response: ResilientOrchestratorMixin._parse_llm_response(mixin, response)
    
    # Initialize the mixin
    if hasattr(orchestrator_instance, 'tool_registry'):
        mixin.tool_registry = orchestrator_instance.tool_registry
        mixin.tool_router = ResilientToolRouter(registry=orchestrator_instance.tool_registry)
        mixin.feedback_loop = ExecutionFeedbackLoop(registry=orchestrator_instance.tool_registry)
        
        logger.info("Successfully patched orchestrator with resilient routing")
    else:
        logger.error("Cannot patch: orchestrator missing tool_registry attribute")


# Import at module level for patch function
from jarvis.tools.resilient_router import ResilientToolRouter, ExecutionFeedbackLoop
