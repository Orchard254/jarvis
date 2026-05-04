"""
Context Assembly Module

Assembles all context needed for LLM inference including:
- Current conversation history
- Retrieved memories
- System state
- Available tools and skills
- User preferences
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ContextAssembler:
    """
    Assembles comprehensive context for LLM inference.
    
    Combines multiple context sources into a unified format
    optimized for the LLM's understanding.
    """
    
    def __init__(self, config: Dict[str, Any], memory_system, 
                 tool_registry=None, skill_registry=None):
        """
        Initialize context assembler.
        
        Args:
            config: Configuration dict
            memory_system: CoreMemory instance
            tool_registry: ToolRegistry instance
            skill_registry: SkillRegistry instance
        """
        self.config = config
        self.memory = memory_system
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
        
        logger.info("Context assembler initialized")
    
    def assemble_context(self, user_input: str, 
                        mode: str = 'agent',
                        include_memories: bool = True,
                        include_tools: bool = True,
                        include_skills: bool = True,
                        include_system_state: bool = True,
                        recent_results: Optional[List[Dict]] = None,
                        failed_actions: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Assemble complete context for LLM inference.
        
        Args:
            user_input: The current user input
            mode: Operating mode ('chat' or 'agent')
            include_memories: Whether to include retrieved memories
            include_tools: Whether to include tool definitions
            include_skills: Whether to include skill definitions
            include_system_state: Whether to include current system state
            recent_results: List of recent successful tool results (last 5 min)
            failed_actions: List of recent failed actions (last 2 min)
            
        Returns:
            Complete context dict for LLM
        """
        import time
        current_time = time.time()
        
        context = {
            'timestamp': datetime.now().isoformat(),
            'mode': mode,
            'user_input': user_input,
            'conversation': [],
            'memories': {},
            'tools': [],
            'skills': [],
            'system_state': {},
            'user_profile': {},
            'recent_facts': [],
            'recent_results': [],
            'failed_actions': []
        }
        
        # Get conversation history
        context['conversation'] = self.memory.get_conversation_history()
        
        # Extract recent facts from conversation (last 5 minutes of successful tool results)
        conv_history = context['conversation']
        recent_facts = []
        for msg in reversed(conv_history[-20:]):  # Check last 20 messages
            if msg.get('role') == 'tool' and msg.get('success', True):
                content = msg.get('content', '')
                if content and len(content) < 300:  # Only concise factual results
                    recent_facts.append({
                        'fact': content,
                        'tool': msg.get('name', 'tool'),
                        'timestamp': msg.get('timestamp', current_time)
                    })
                if len(recent_facts) >= 5:
                    break
        context['recent_facts'] = recent_facts
        
        # Include provided recent results (from orchestrator tracking)
        if recent_results:
            context['recent_results'] = recent_results[-5:]  # Last 5
        
        # Include provided failed actions
        if failed_actions:
            # Filter to only failures within last 2 minutes
            context['failed_actions'] = [
                f for f in failed_actions 
                if current_time - f.get('timestamp', 0) < 120
            ][-5:]  # Last 5 failures
        
        # Retrieve relevant memories if enabled
        if include_memories:
            context['memories'] = self.memory.retrieve_context(
                query=user_input,
                limit=self.config.get('memory_retrieval_limit', 5)
            )
        
        # Include tool definitions if enabled
        if include_tools and self.tool_registry:
            context['tools'] = self._get_tool_definitions()
        
        # Include skill definitions if enabled
        if include_skills and self.skill_registry:
            context['skills'] = self._get_skill_definitions()
        
        # Include system state if enabled
        if include_system_state:
            context['system_state'] = self._get_system_state()
        
        # Include user profile
        context['user_profile'] = self._get_user_profile()
        
        logger.debug(f"Assembled context with {len(context['conversation'])} messages, "
                    f"{len(context['tools'])} tools, {len(context['skills'])} skills, "
                    f"{len(context['recent_facts'])} recent facts, "
                    f"{len(context['recent_results'])} recent results")
        
        return context
    
    def _get_tool_definitions(self) -> List[Dict]:
        """
        Get simplified tool definitions for context.
        
        Returns:
            List of tool definition dicts
        """
        if not self.tool_registry:
            return []
        
        tools = []
        for tool_name, tool_class in self.tool_registry.tools.items():
            try:
                # Get tool schema if available
                if hasattr(tool_class, 'get_schema'):
                    schema = tool_class.get_schema()
                else:
                    # Create minimal schema
                    schema = {
                        'name': tool_name,
                        'description': getattr(tool_class, '__doc__', 'No description'),
                        'parameters': {
                            'type': 'object',
                            'properties': {}
                        }
                    }
                tools.append(schema)
            except Exception as e:
                logger.warning(f"Failed to get schema for tool {tool_name}: {e}")
        
        return tools
    
    def _get_skill_definitions(self) -> List[Dict]:
        """
        Get simplified skill definitions for context.
        
        Returns:
            List of skill definition dicts
        """
        if not self.skill_registry:
            return []
        
        skills = []
        for skill_name, skill_class in self.skill_registry.skills.items():
            try:
                skills.append({
                    'name': skill_name,
                    'description': getattr(skill_class, '__doc__', 'No description'),
                    'triggers': getattr(skill_class, 'TRIGGERS', [])
                })
            except Exception as e:
                logger.warning(f"Failed to get info for skill {skill_name}: {e}")
        
        return skills
    
    def _get_system_state(self) -> Dict[str, Any]:
        """
        Get current system state snapshot.
        
        Returns:
            Dict with current system state
        """
        import psutil
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Battery status (if available)
            battery = None
            try:
                battery_info = psutil.sensors_battery()
                if battery_info:
                    battery = {
                        'percent': battery_info.percent,
                        'plugged_in': battery_info.power_plugged,
                        'time_left': battery_info.secsleft if battery_info.secsleft != -1 else None
                    }
            except Exception as e:
                log.debug(f"[CONTEXT] Battery info unavailable: {e}")
            
            # Network connections count
            net_connections = len(psutil.net_connections(kind='inet'))
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': round(memory.available / (1024**3), 2),
                'battery': battery,
                'active_network_connections': net_connections,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.warning(f"Failed to get system state: {e}")
            return {'error': str(e)}
    
    def _get_user_profile(self) -> Dict[str, Any]:
        """
        Get user profile information.
        
        Returns:
            Dict with user profile data
        """
        # This would integrate with the user_profile module
        # For now, return basic structure
        return {
            'name': self.config.get('user_name', 'User'),
            'preferences': self.config.get('user_preferences', {}),
            'routines': self.config.get('user_routines', [])
        }
    
    def format_for_llm(self, context: Dict[str, Any]) -> str:
        """
        Format context as a string for LLM consumption.
        
        Args:
            context: Context dict from assemble_context
            
        Returns:
            Formatted string for LLM
        """
        parts = []
        
        # CRITICAL INSTRUCTION: Check existing knowledge before acting
        parts.append("[IMPORTANT: Before executing any tool, check if you already have this information from recent conversation or tool results. Do not repeat actions that already succeeded.]")
        
        # System state header
        if context.get('system_state'):
            state = context['system_state']
            state_parts = []
            if 'cpu_percent' in state:
                state_parts.append(f"CPU: {state['cpu_percent']}%")
            if 'memory_percent' in state:
                state_parts.append(f"Memory: {state['memory_percent']}%")
            if state.get('battery'):
                bat = state['battery']
                state_parts.append(f"Battery: {bat['percent']}%{' (Charging)' if bat.get('plugged_in') else ''}")
            if state_parts:
                parts.append(f"[System State: {', '.join(state_parts)}]")
        
        # Recently obtained facts (HIGHEST PRIORITY - from last 5 minutes)
        if context.get('recent_facts'):
            facts = context['recent_facts']
            fact_strings = []
            for fact in facts[:5]:  # Top 5 most recent
                fact_strings.append(fact.get('fact', str(fact)))
            if fact_strings:
                parts.append(f"[RECENTLY OBTAINED FACTS - Use these before running tools: {'; '.join(fact_strings)}]")
        
        # Relevant memories
        if context.get('memories'):
            memories = context['memories']
            
            if memories.get('semantic'):
                facts = [m.get('fact', m.get('text', '')) for m in memories['semantic'][:3]]
                if facts:
                    parts.append(f"[Long-term Facts: {'; '.join(facts)}]")
            
            if memories.get('procedural'):
                patterns = [m.get('description', '') for m in memories['procedural'][:2]]
                if patterns:
                    parts.append(f"[Learned Patterns: {'; '.join(patterns)}]")
        
        # Recent tool execution results (last 3 successful executions)
        if context.get('recent_results'):
            results = context['recent_results']
            result_strings = []
            for result in results[:3]:
                tool_name = result.get('tool', 'tool')
                output = result.get('output', result.get('result', ''))
                if output and len(str(output)) < 200:  # Only include concise results
                    result_strings.append(f"{tool_name} returned: {output}")
            if result_strings:
                parts.append(f"[RECENT TOOL RESULTS - Reference these instead of re-executing: {'; '.join(result_strings)}]")
        
        # Conversation history
        if context.get('conversation'):
            conv_parts = []
            for msg in context['conversation'][-10:]:  # Last 10 messages
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:200]  # Truncate long messages
                if role == 'user':
                    conv_parts.append(f"User: {content}")
                elif role == 'assistant':
                    conv_parts.append(f"Assistant: {content}")
                elif role == 'tool':
                    tool_name = msg.get('name', 'tool')
                    result = msg.get('content', '')[:100]
                    conv_parts.append(f"[{tool_name}] Result: {result}")
            
            if conv_parts:
                parts.append("[Conversation History:]")
                parts.extend(conv_parts)
        
        # Failed actions to avoid (from last 2 minutes)
        if context.get('failed_actions'):
            failed = context['failed_actions']
            fail_strings = []
            for fail in failed[:3]:
                tool_name = fail.get('tool', 'tool')
                error = fail.get('error', 'unknown error')
                fail_strings.append(f"{tool_name} failed: {error}")
            if fail_strings:
                parts.append(f"[RECENT FAILURES - Do NOT retry these: {'; '.join(fail_strings)}]")
        
        # Available tools summary
        if context.get('tools'):
            tool_names = [t.get('name', '') for t in context['tools']]
            parts.append(f"[Available Tools: {', '.join(tool_names)}]")
        
        # Available skills summary
        if context.get('skills'):
            skill_names = [s.get('name', '') for s in context['skills']]
            if skill_names:
                parts.append(f"[Available Skills: {', '.join(skill_names)}]")
        
        return '\n'.join(parts)
    
    def create_system_message(self, context: Dict[str, Any], 
                             system_prompt: str) -> Dict[str, str]:
        """
        Create the system message for LLM with full context.
        
        Args:
            context: Context dict from assemble_context
            system_prompt: Base system prompt
            
        Returns:
            System message dict ready for LLM
        """
        # Format additional context
        additional_context = self.format_for_llm(context)
        
        # Combine with base system prompt
        full_system_prompt = system_prompt
        if additional_context:
            full_system_prompt += f"\n\n{additional_context}"
        
        return {
            'role': 'system',
            'content': full_system_prompt
        }
