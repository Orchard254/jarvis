"""
Jarvis Runtime - Main runtime integrating supervision, memory, and recovery.
Provides the execution environment for the supercomputer personal assistant.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class JarvisRuntime:
    """
    Main runtime environment for JARVIS supercomputer assistant.
    
    Integrates:
    - Supervisor skill for quality-assured execution
    - Persistent memory for learning and context
    - Hierarchical error recovery for resilience
    - Dynamic tool registry for extensibility
    
    This is the primary entry point for task execution.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the JARVIS runtime.
        
        Args:
            config: Configuration dictionary with optional keys:
                - memory_db_path: Path to SQLite memory database
                - max_refinement_cycles: Max critique-refine loops
                - quality_threshold: Minimum quality score (0-1)
                - recovery_max_retries: Max retry attempts
                - data_dir: Directory for memory storage
        """
        self.config = config or {}
        
        # Lazy imports to avoid circular dependency
        from jarvis.skills.supervisor import SupervisorSkill
        from jarvis.core.memory import CoreMemory
        from jarvis.core.recovery import HierarchicalRecovery, RecoveryConfig
        from jarvis.tools.registry_dynamic import get_registry
        
        # Initialize components
        logger.info("Initializing JARVIS Runtime...")
        
        # 1. Initialize memory system
        memory_config = {
            'data_dir': self.config.get('data_dir', 'jarvis_data'),
            'working_memory_max_messages': self.config.get('working_memory_max_messages', 20),
            'working_memory_max_tokens': self.config.get('working_memory_max_tokens', 4000)
        }
        self.memory = CoreMemory(memory_config)
        logger.info("Memory system initialized")
        
        # 2. Initialize supervisor skill
        self.supervisor = SupervisorSkill()
        self.supervisor.set_memory(self.memory)
        
        # Configure supervisor from config
        if 'max_refinement_cycles' in self.config:
            self.supervisor.max_refinement_cycles = self.config['max_refinement_cycles']
        if 'quality_threshold' in self.config:
            self.supervisor.quality_threshold = self.config['quality_threshold']
        
        logger.info("Supervisor skill initialized")
        
        # 3. Initialize error recovery system
        recovery_config = RecoveryConfig(
            max_retries=self.config.get('recovery_max_retries', 3),
            base_delay=self.config.get('recovery_base_delay', 1.0),
            max_delay=self.config.get('recovery_max_delay', 60.0)
        )
        self.recovery = HierarchicalRecovery(recovery_config)
        logger.info("Error recovery system initialized")
        
        # 4. Initialize tool registry
        self.tool_registry = get_registry()
        logger.info(f"Tool registry initialized with {len(self.tool_registry.list_tools())} tools")
        
        # Runtime state
        self._current_task: Optional[str] = None
        self._execution_history: List[Dict[str, Any]] = []
        self._started_at = datetime.now()
        
        logger.info("JARVIS Runtime ready")
    
    def execute_task(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a task with full supervision and error recovery.
        
        Args:
            task: Task description from user
            context: Optional additional context
            
        Returns:
            Execution result with success status, output, and metadata
        """
        self._current_task = task
        start_time = datetime.now()
        
        logger.info(f"Executing task: {task[:100]}...")
        
        # Store in working memory
        self.memory.add_user_message(task, metadata={'type': 'task', 'timestamp': start_time.isoformat()})
        
        # Retrieve relevant context from long-term memory
        retrieved_context = self.memory.retrieve_context(query=task, limit=5)
        
        # Enrich context with provided context
        if context:
            retrieved_context['provided_context'] = context
        
        try:
            # Execute with supervisor
            plan = self.supervisor.plan(task)
            result = self.supervisor.execute(plan)
            
            # Store outcome in memory
            success = result.get('success', False)
            self.memory.log_interaction(
                task=task,
                plan=str([{'id': s.id, 'name': s.name} for s in plan]),
                outcome=str(result.get('output', result.get('error', ''))),
                success=success
            )
            
            # Add assistant response to working memory
            if success:
                self.memory.add_assistant_message(
                    str(result.get('output', 'Task completed')),
                    metadata={'task': task, 'result': result}
                )
            else:
                self.memory.add_assistant_message(
                    f"Task encountered issues: {result.get('error', 'Unknown error')}",
                    metadata={'task': task, 'error': result.get('error')}
                )
            
            # Record in execution history
            execution_record = {
                'task': task,
                'start_time': start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'success': success,
                'cycles_run': result.get('cycles_run', 0),
                'final_quality': result.get('final_quality', 0.0),
                'result': result
            }
            self._execution_history.append(execution_record)
            
            # Keep history bounded
            if len(self._execution_history) > 100:
                self._execution_history = self._execution_history[-100:]
            
            logger.info(f"Task execution completed: success={success}")
            
            return {
                'success': success,
                'output': result.get('output'),
                'error': result.get('error'),
                'cycles_run': result.get('cycles_run', 0),
                'final_quality': result.get('final_quality', 0.0),
                'metadata': {
                    'task_id': len(self._execution_history),
                    'duration_seconds': (datetime.now() - start_time).total_seconds()
                }
            }
            
        except Exception as e:
            logger.error(f"Task execution failed with exception: {e}")
            
            # Attempt recovery
            recovery_result = self.recovery.execute_with_recovery(
                operation=lambda: (_ for _ in ()).throw(e),  # Re-raise for classification
                context={'task': task},
                operation_name=f"task_execution:{task[:50]}"
            )
            
            error_result = {
                'success': False,
                'error': str(e),
                'recovery_attempted': True,
                'recovery_strategy': recovery_result.strategy_used.value if recovery_result else None,
                'metadata': {
                    'task_id': len(self._execution_history),
                    'duration_seconds': (datetime.now() - start_time).total_seconds()
                }
            }
            
            self._execution_history.append({
                'task': task,
                'start_time': start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'success': False,
                'error': str(e),
                'recovery': error_result
            })
            
            return error_result
        
        finally:
            self._current_task = None
    
    def execute_with_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any],
        task_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a specific tool with error recovery.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            task_description: Optional task description for context
            
        Returns:
            Tool execution result
        """
        tool = self.tool_registry.get_tool(tool_name)
        
        if not tool:
            return {
                'success': False,
                'error': f"Tool '{tool_name}' not found",
                'available_tools': self.tool_registry.list_tools()
            }
        
        # Validate parameters
        is_valid, error_msg = tool.validate(**parameters)
        if not is_valid:
            return {
                'success': False,
                'error': f"Validation failed: {error_msg}"
            }
        
        # Execute with recovery
        def tool_operation():
            return tool.execute(**parameters)
        
        recovery_result = self.recovery.execute_with_recovery(
            operation=tool_operation,
            context={'tool': tool_name, 'parameters': parameters},
            operation_name=f"tool:{tool_name}"
        )
        
        if recovery_result.success:
            tool_result = recovery_result.recovered_value
            return {
                'success': tool_result.success,
                'output': tool_result.output,
                'error': tool_result.error,
                'verified': tool_result.verified,
                'recovery_info': {
                    'retries': recovery_result.retries_attempted,
                    'strategy': recovery_result.strategy_used.value
                } if recovery_result.retries_attempted > 0 else None
            }
        else:
            return {
                'success': False,
                'error': recovery_result.error_message,
                'recovery_info': {
                    'retries': recovery_result.retries_attempted,
                    'strategy': recovery_result.strategy_used.value
                }
            }
    
    def create_dynamic_tool(
        self,
        name: str,
        description: str,
        execute_fn,
        validate_fn=None,
        category: str = "custom"
    ) -> bool:
        """
        Create and register a custom tool at runtime.
        
        Args:
            name: Tool name
            description: Tool description
            execute_fn: Function to execute (should return ToolResult or value)
            validate_fn: Optional validation function
            category: Tool category
            
        Returns:
            True if successful
        """
        try:
            self.tool_registry.create_temporary_tool(
                name=name,
                description=description,
                execute_fn=execute_fn,
                validate_fn=validate_fn,
                category=category
            )
            logger.info(f"Created dynamic tool: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create dynamic tool {name}: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get runtime status and statistics."""
        return {
            'status': 'running',
            'uptime_seconds': (datetime.now() - self._started_at).total_seconds(),
            'current_task': self._current_task,
            'tasks_executed': len(self._execution_history),
            'successful_tasks': sum(1 for t in self._execution_history if t.get('success', False)),
            'memory_stats': self.memory.get_memory_stats(),
            'tool_registry_stats': self.tool_registry.get_stats(),
            'supervisor_config': {
                'max_refinement_cycles': self.supervisor.max_refinement_cycles,
                'quality_threshold': self.supervisor.quality_threshold
            },
            'recovery_config': {
                'max_retries': self.recovery.config.max_retries,
                'base_delay': self.recovery.config.base_delay
            }
        }
    
    def get_recent_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent task execution history."""
        return self._execution_history[-limit:]
    
    def clear_memory(self):
        """Clear working memory (long-term memory preserved)."""
        self.memory.clear_working_memory()
        logger.info("Working memory cleared")
    
    def shutdown(self):
        """Gracefully shutdown the runtime."""
        logger.info("Shutting down JARVIS Runtime...")
        
        # End any active memory session
        try:
            self.memory.end_current_session(summary="Runtime shutdown")
        except Exception as e:
            logger.warning(f"Error ending memory session: {e}")
        
        logger.info("JARVIS Runtime shutdown complete")


# Convenience function for creating runtime instance
def create_runtime(config: Optional[Dict[str, Any]] = None) -> JarvisRuntime:
    """
    Create and initialize a JARVIS runtime instance.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Initialized JarvisRuntime instance
    """
    return JarvisRuntime(config)


__all__ = ['JarvisRuntime', 'create_runtime']
