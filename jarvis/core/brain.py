"""
Brain Module - LLM Inference Coordinator

Coordinates all LLM interactions including:
- Chat completions
- Tool selection via function calling
- Multimodal vision analysis
- Planning and reasoning
"""

import logging
from typing import Dict, List, Any, Optional, Callable
import json
import time
import re

from jarvis.models.ollama_client import OllamaClient
from jarvis.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Brain:
    """
    LLM inference coordinator for JARVIS.
    
    Handles all communication with the LLM including:
    - Standard chat completions
    - Function/tool calling
    - Multimodal inputs (images)
    - Streaming responses
    """
    
    def __init__(self, config: Dict[str, Any], tool_registry: ToolRegistry):
        """
        Initialize the Brain.
        
        Args:
            config: Configuration dict with LLM settings
            tool_registry: ToolRegistry instance for function calling
        """
        self.config = config
        self.tool_registry = tool_registry
        
        # Initialize Ollama client
        self.client = OllamaClient(
            cloud_url=config.get('ollama_cloud_url', 'https://ollama.com/api/chat'),
            local_url=config.get('ollama_local_url', 'http://localhost:11434/api/chat'),
            api_key=config.get('ollama_api_key', ''),
            model=config.get('model', 'nemotron-3-nano:30b-cloud'),
            max_retries=config.get('max_retries', 3),
            timeout=config.get('llm_timeout', 60)
        )
        
        # Track conversation for context
        self.conversation_history: List[Dict] = []
        
        # Callbacks
        self.on_tool_call: Optional[Callable] = None
        self.on_thinking: Optional[Callable] = None
        
        # Timing tracking
        self.thinking_start_time: Optional[float] = None
        self.last_thinking_duration: Optional[float] = None
        self._thinking_callback_active: bool = False
        
        logger.info("Brain initialized with model: %s", 
                   config.get('model', 'nemotron-3-nano:30b-cloud'))
    
    def set_callbacks(self, on_tool_call: Optional[Callable] = None,
                     on_thinking: Optional[Callable] = None) -> None:
        """
        Set callback functions for brain events.
        
        Args:
            on_tool_call: Called when LLM requests a tool call
            on_thinking: Called when LLM is thinking/processing
        """
        self.on_tool_call = on_tool_call
        self.on_thinking = on_thinking
    
    def _parse_thinking_content(self, content: str) -> tuple[str, list[str]]:
        """
        Parse <think>...</think> sections from reasoning model output.
        
        Args:
            content: Raw LLM response content
            
        Returns:
            Tuple of (cleaned_content, thinking_sections)
        """
        thinking_sections = []
        cleaned_content = content
        
        # Find all <think>...</think> sections
        think_pattern = r'<think>(.*?)</think>'
        matches = re.findall(think_pattern, content, re.DOTALL | re.IGNORECASE)
        
        if matches:
            thinking_sections = [match.strip() for match in matches]
            # Remove thinking tags from content
            cleaned_content = re.sub(think_pattern, '', content, flags=re.DOTALL | re.IGNORECASE).strip()
        
        return cleaned_content, thinking_sections
    
    def _start_thinking_timer(self) -> None:
        """Start timing the LLM thinking phase."""
        self.thinking_start_time = time.time()
        self._thinking_callback_active = True
    
    def _stop_thinking_timer(self) -> Optional[float]:
        """
        Stop the thinking timer and return duration.
        
        Returns:
            Duration in seconds, or None if timer wasn't started
        """
        if self.thinking_start_time is None:
            return None
        
        duration = time.time() - self.thinking_start_time
        self.last_thinking_duration = duration
        self.thinking_start_time = None
        self._thinking_callback_active = False
        return duration
    
    def chat(self, messages: List[Dict], 
             system_prompt: Optional[str] = None,
             temperature: float = 0.7,
             max_tokens: int = 1024,  # Reduced from 2048 to prevent context overflow
             stream: bool = False,
             include_tools: bool = True) -> Dict[str, Any]:
        """
        Send a chat message to the LLM.
        
        Args:
            messages: List of message dicts with role and content
            system_prompt: Optional system prompt to prepend
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            stream: Whether to stream the response
            include_tools: Whether to include tool schemas for function calling
            
        Returns:
            Response dict with content and metadata
        """
        # Prepare messages
        prepared_messages = self._prepare_messages(messages, system_prompt)
        
        # Get tools schema for function calling (only if requested)
        tools_schema = self._get_tools_schema() if include_tools else None
        
        # Start thinking timer
        self._start_thinking_timer()
        
        if self.on_thinking:
            self.on_thinking("Thinking...")
        
        try:
            response = self.client.chat(
                messages=prepared_messages,
                tools=tools_schema if tools_schema else None,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            
            # Stop thinking timer
            thinking_duration = self._stop_thinking_timer()
            
            # Parse thinking content from reasoning models
            raw_content = response.get('content', '')
            cleaned_content, thinking_sections = self._parse_thinking_content(raw_content)
            
            # Update conversation history with cleaned content
            response['content'] = cleaned_content
            self._update_history(prepared_messages, response)
            
            return {
                'success': True,
                'content': cleaned_content,
                'thinking_sections': thinking_sections,
                'thinking_duration': thinking_duration,
                'tool_calls': response.get('tool_calls', []),
                'finish_reason': response.get('finish_reason', 'stop'),
                'usage': response.get('usage', {}),
                'model': response.get('model', self.config.get('model', 'unknown'))
            }
            
        except Exception as e:
            # Stop timer on error
            self._stop_thinking_timer()
            logger.error(f"LLM chat failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'content': None,
                'thinking_sections': [],
                'thinking_duration': None,
                'tool_calls': [],
                'finish_reason': 'error'
            }
    
    def chat_with_tools(self, user_message: str,
                       system_prompt: Optional[str] = None,
                       max_iterations: int = 5,
                       temperature: float = 0.7) -> Dict[str, Any]:
        """
        Chat with automatic tool execution loop.
        
        The LLM can call tools, and results are fed back until
        it produces a final answer or reaches max iterations.
        
        Args:
            user_message: The user's message
            system_prompt: Optional system prompt
            max_iterations: Maximum tool call iterations
            temperature: Sampling temperature
            
        Returns:
            Final response after tool execution
        """
        # Add user message to history
        self.conversation_history.append({
            'role': 'user',
            'content': user_message
        })
        
        iteration = 0
        final_response = None
        total_thinking_time = 0.0
        all_thinking_sections = []
        
        while iteration < max_iterations:
            iteration += 1
            
            if self.on_thinking:
                self.on_thinking(f"Thinking (iteration {iteration})...")
            
            # Get LLM response
            response = self.chat(
                messages=self.conversation_history,
                system_prompt=system_prompt,
                temperature=temperature
            )
            
            # Accumulate thinking time and sections
            if response.get('thinking_duration'):
                total_thinking_time += response['thinking_duration']
            if response.get('thinking_sections'):
                all_thinking_sections.extend(response['thinking_sections'])
            
            if not response['success']:
                return {
                    'success': False,
                    'error': response.get('error', 'LLM call failed'),
                    'content': None,
                    'iterations': iteration,
                    'total_thinking_time': total_thinking_time,
                    'thinking_sections': all_thinking_sections
                }
            
            # Check if there are tool calls
            tool_calls = response.get('tool_calls', [])
            
            if not tool_calls:
                # No tool calls, we have our final response
                final_response = response
                break
            
            # Execute tool calls
            tool_results = []
            for tool_call in tool_calls:
                result = self._execute_tool_call(tool_call)
                tool_results.append(result)
                
                # Add tool result to conversation
                # Handle both Ollama format (nested in 'function') and direct format
                if 'function' in tool_call:
                    tool_name = tool_call['function'].get('name', 'unknown')
                    tool_id = tool_call.get('id', '')
                else:
                    tool_name = tool_call.get('name', 'unknown')
                    tool_id = tool_call.get('id', '')
                    
                self.conversation_history.append({
                    'role': 'tool',
                    'name': tool_name,
                    'content': str(result.get('output', result.get('error', 'No output'))),
                    'tool_call_id': tool_id
                })
            
            # Notify callback
            if self.on_tool_call:
                self.on_tool_call(tool_calls, tool_results)
        
        if final_response is None:
            # Max iterations reached without final answer
            return {
                'success': True,
                'content': "I reached the maximum number of tool call iterations without completing the task.",
                'tool_calls': [],
                'iterations': iteration,
                'total_thinking_time': total_thinking_time,
                'thinking_sections': all_thinking_sections,
                'warning': 'max_iterations_reached'
            }
        
        return {
            'success': True,
            'content': final_response['content'],
            'tool_calls': final_response.get('tool_calls', []),
            'iterations': iteration,
            'total_thinking_time': total_thinking_time,
            'thinking_sections': all_thinking_sections,
            'usage': final_response.get('usage', {})
        }
    
    def analyze_image(self, image_base64: str, 
                     prompt: str,
                     system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze an image using multimodal LLM.
        
        Args:
            image_base64: Base64 encoded image
            prompt: Question/prompt about the image
            system_prompt: Optional system prompt
            
        Returns:
            Analysis result
        """
        messages = [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{image_base64}'}}
            ]
        }]
        
        return self.chat(messages, system_prompt=system_prompt)
    
    def validate_tool_name(self, tool_name: str) -> bool:
        """
        Validate that a tool name exists in the registry.
        
        Args:
            tool_name: Name of the tool to validate
            
        Returns:
            True if tool exists
        """
        return self.tool_registry.has_tool(tool_name)
    
    def get_available_tool_names(self) -> List[str]:
        """
        Get list of available tool names.
        
        Returns:
            List of tool names
        """
        return self.tool_registry.get_tool_names()
    
    def _prepare_messages(self, messages: List[Dict], 
                         system_prompt: Optional[str]) -> List[Dict]:
        """
        Prepare messages for LLM by adding system prompt.
        
        Args:
            messages: User messages
            system_prompt: System prompt
            
        Returns:
            Prepared message list
        """
        prepared = []
        
        # Add system prompt first
        if system_prompt:
            prepared.append({'role': 'system', 'content': system_prompt})
        
        # Add conversation history (limited to avoid token overflow)
        # Reduced from 20 to 6 to prevent context bloat causing Ollama timeouts
        history_limit = self.config.get('conversation_history_limit', 6)
        prepared.extend(self.conversation_history[-history_limit:])
        
        # Add new messages
        prepared.extend(messages)
        
        return prepared
    
    def _update_history(self, messages: List[Dict], response: Dict) -> None:
        """
        Update conversation history with new exchange.
        
        Args:
            messages: Messages sent to LLM
            response: LLM response
        """
        # Only add the last user message and the response
        # Reduced from 20 to 6 to prevent context bloat causing Ollama timeouts
        history_limit = self.config.get('conversation_history_limit', 6)
        
        # Find last user message
        last_user_msg = None
        for msg in reversed(messages):
            if msg['role'] == 'user':
                last_user_msg = msg
                break
        
        if last_user_msg:
            self.conversation_history.append(last_user_msg)
        
        # Add assistant response
        assistant_msg = {
            'role': 'assistant',
            'content': response.get('content', '')
        }
        
        # Include tool calls in history if present
        if response.get('tool_calls'):
            assistant_msg['tool_calls'] = response['tool_calls']
        
        self.conversation_history.append(assistant_msg)
        
        # Trim history if too long
        if len(self.conversation_history) > history_limit:
            self.conversation_history = self.conversation_history[-history_limit:]
    
    def _get_tools_schema(self) -> List[Dict]:
        """
        Get tool schemas for function calling.
        
        Returns:
            List of tool schema dicts
        """
        return self.tool_registry.get_all_schemas()
    
    def _execute_tool_call(self, tool_call: Dict) -> Dict[str, Any]:
        """
        Execute a single tool call.
        
        Args:
            tool_call: Tool call dict from LLM
            
        Returns:
            Tool execution result
        """
        # Ollama returns tool_calls in format: {'function': {'name': ..., 'arguments': ...}, 'id': ..., 'type': ...}
        # But we need to handle both formats
        if 'function' in tool_call:
            # Ollama format
            tool_name = tool_call['function'].get('name', '')
            arguments = tool_call['function'].get('arguments', {})
        else:
            # Direct format
            tool_name = tool_call.get('name', '')
            arguments = tool_call.get('arguments', {})
        
        # Validate tool exists
        if not self.validate_tool_name(tool_name):
            error_msg = f"Tool '{tool_name}' not found. Available tools: {', '.join(self.get_available_tool_names())}"
            logger.warning(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'output': None,
                'exit_code': -1
            }
        
        # Execute the tool
        try:
            result = self.tool_registry.execute(tool_name, **arguments)
            # Convert ToolResult to dict if needed
            if hasattr(result, 'to_dict'):
                result_dict = result.to_dict()
            else:
                result_dict = result
            logger.info(f"Executed tool {tool_name}: success={result_dict.get('success', False)}")
            return result_dict
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'output': None,
                'exit_code': -1
            }
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")
    
    def get_history(self) -> List[Dict]:
        """
        Get current conversation history.
        
        Returns:
            List of conversation messages
        """
        return self.conversation_history.copy()
    
    def inject_system_message(self, message: str) -> None:
        """
        Inject a system message into conversation history.
        
        Args:
            message: System message to inject
        """
        self.conversation_history.append({
            'role': 'system',
            'content': message
        })
