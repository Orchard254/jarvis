"""Low-level tool execution dispatcher.

Handles the actual invocation of tools, parameter validation,
timeout management, and result collection.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import logging
import asyncio

from config.config import get_config
from safety.audit_log import AuditLog
from execution.rollback import RollbackAction

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    rollback_actions: list[RollbackAction] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolRunner:
    """Executes individual tools with safety checks and timeout handling.
    
    Responsibilities:
    - Load and validate tool implementations
    - Execute tools with parameter validation
    - Enforce timeouts to prevent hangs
    - Collect results and rollback actions
    - Track tool reliability metrics
    """
    
    def __init__(self, audit_log: AuditLog):
        self.config = get_config()
        self.audit_log = audit_logger
        self._tools_registry: dict[str, Any] = {}
        self._load_tools()
    
    def _load_tools(self):
        """Load all available tools from the tools registry."""
        from tools.registry import get_all_tools
        
        self._tools_registry = get_all_tools()
        logger.info(f"Loaded {len(self._tools_registry)} tools")
    
    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        timeout_ms: Optional[float] = None,
    ) -> ToolResult:
        """Execute a single tool.
        
        Args:
            tool_name: Name of the tool to execute
            params: Parameters to pass to the tool
            timeout_ms: Maximum execution time in milliseconds
            
        Returns:
            ToolResult with success status, output, and any errors
        """
        if timeout_ms is None:
            timeout_ms = self.config.get('execution.tool_timeout_ms', 30000)
        
        logger.debug(f"Executing tool '{tool_name}' with params: {params}")
        
        # Validate tool exists
        if tool_name not in self._tools_registry:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )
        
        tool = self._tools_registry[tool_name]
        start_time = asyncio.get_event_loop().time() * 1000
        
        try:
            # Validate parameters
            validation_result = self._validate_params(tool, params)
            if not validation_result[0]:
                return ToolResult(
                    success=False,
                    error=f"Parameter validation failed: {validation_result[1]}",
                )
            
            # Execute with timeout
            result = await asyncio.wait_for(
                self._invoke_tool(tool, params),
                timeout=timeout_ms / 1000,
            )
            
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            
            # Extract rollback actions if present
            rollback_actions = []
            if isinstance(result, dict) and 'rollback_actions' in result:
                rollback_actions = result['rollback_actions']
            elif hasattr(result, 'rollback_actions'):
                rollback_actions = result.rollback_actions
            
            # Log successful execution
            self.audit_log.log_tool_execution(
                tool_name,
                params,
                True,
                duration_ms,
                error=None,
            )
            
            return ToolResult(
                success=True,
                output=result,
                duration_ms=duration_ms,
                rollback_actions=rollback_actions,
                metadata={'tool_version': getattr(tool, '__version__', '1.0')},
            )
            
        except asyncio.TimeoutError:
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            error_msg = f"Tool '{tool_name}' timed out after {timeout_ms}ms"
            logger.error(error_msg)
            
            self.audit_log.log_tool_execution(
                tool_name,
                params,
                False,
                duration_ms,
                error=error_msg,
            )
            
            return ToolResult(
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            error_msg = f"Tool '{tool_name}' failed: {str(e)}"
            logger.exception(error_msg)
            
            self.audit_log.log_tool_execution(
                tool_name,
                params,
                False,
                duration_ms,
                error=error_msg,
            )
            
            return ToolResult(
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
            )
    
    def _validate_params(
        self, 
        tool: Any, 
        params: dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate tool parameters against schema.
        
        Args:
            tool: Tool instance or class
            params: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Get tool schema if available
        schema = getattr(tool, 'schema', None)
        if schema is None:
            # No schema defined, skip validation
            return True, None
        
        # Check required parameters
        required = schema.get('required', [])
        for param in required:
            if param not in params:
                return False, f"Missing required parameter: {param}"
        
        # Type checking could be added here based on schema
        # For now, just check presence
        
        return True, None
    
    async def _invoke_tool(self, tool: Any, params: dict[str, Any]) -> Any:
        """Invoke a tool with the given parameters.
        
        Args:
            tool: Tool instance or class
            params: Parameters to pass
            
        Returns:
            Tool execution result
        """
        # Check if tool is async
        if asyncio.iscoroutinefunction(tool.execute):
            return await tool.execute(**params)
        else:
            # Run sync tool in executor to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: tool.execute(**params)
            )
    
    def get_tool_info(self, tool_name: str) -> Optional[dict[str, Any]]:
        """Get information about a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool metadata or None if not found
        """
        if tool_name not in self._tools_registry:
            return None
        
        tool = self._tools_registry[tool_name]
        return {
            'name': tool_name,
            'description': getattr(tool, 'description', 'No description'),
            'schema': getattr(tool, 'schema', {}),
            'category': getattr(tool, 'category', 'unknown'),
        }
    
    def list_tools(self) -> list[str]:
        """List all available tool names."""
        return list(self._tools_registry.keys())
