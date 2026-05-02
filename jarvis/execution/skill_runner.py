"""BaseSkill execution engine.

Manages the execution of high-level skills, which are composable
sequences of tool calls and logic for complex tasks.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import logging
import asyncio

from jarvis.config.config import get_config
from jarvis.safety.audit_log import AuditLog
from jarvis.execution.rollback import RollbackAction
from jarvis.skills.base import BaseSkill

logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionResult:
    """Result of executing a skill."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    rollback_actions: list[RollbackAction] = field(default_factory=list)
    intermediate_steps: list[dict[str, Any]] = field(default_factory=list)


class SkillRunner:
    """Executes skills with context management and error handling.
    
    Responsibilities:
    - Load and validate skill implementations
    - Execute skills with proper context
    - Manage skill lifecycle (setup, execute, cleanup)
    - Collect results and rollback actions
    - Track intermediate steps for debugging
    """
    
    def __init__(self, audit_log: AuditLog):
        self.config = get_config()
        self.audit_log = audit_log
        self._skills_registry: dict[str, BaseSkill] = {}
        self._load_skills()
    
    def _load_skills(self):
        """Load all available skills from the skills registry."""
        from jarvis.skills.registry import get_registry
        
        registry = get_registry()
        self._skills_registry = registry.get_all_skills()
        logger.info(f"Loaded {len(self._skills_registry)} skills")
    
    async def execute(
        self,
        skill_name: str,
        params: dict[str, Any],
        context: dict[str, Any],
        timeout_ms: Optional[float] = None,
    ) -> SkillExecutionResult:
        """Execute a single skill.
        
        Args:
            skill_name: Name of the skill to execute
            params: Parameters to pass to the skill
            context: Execution context shared across steps
            timeout_ms: Maximum execution time in milliseconds
            
        Returns:
            SkillExecutionResult with success status, output, and any errors
        """
        if timeout_ms is None:
            timeout_ms = self.config.get('execution.skill_timeout_ms', 60000)
        
        logger.debug(f"Executing skill '{skill_name}' with params: {params}")
        
        # Validate skill exists
        if skill_name not in self._skills_registry:
            return SkillExecutionResult(
                success=False,
                error=f"Unknown skill: {skill_name}",
            )
        
        skill = self._skills_registry[skill_name]
        start_time = asyncio.get_event_loop().time() * 1000
        intermediate_steps = []
        
        try:
            # Validate parameters
            validation_result = self._validate_params(skill, params)
            if not validation_result[0]:
                return SkillExecutionResult(
                    success=False,
                    error=f"Parameter validation failed: {validation_result[1]}",
                )
            
            # Create skill execution context
            skill_context = self._create_skill_context(context, params)
            
            # Execute skill lifecycle
            await self._on_skill_start(skill, skill_context)
            
            # Execute with timeout
            result = await asyncio.wait_for(
                self._invoke_skill(skill, skill_context),
                timeout=timeout_ms / 1000,
            )
            
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            
            # Extract rollback actions if present
            rollback_actions = []
            if isinstance(result, dict) and 'rollback_actions' in result:
                rollback_actions = result['rollback_actions']
            elif hasattr(result, 'rollback_actions'):
                rollback_actions = result.rollback_actions
            
            # Capture intermediate steps if available
            if isinstance(result, dict) and 'steps' in result:
                intermediate_steps = result['steps']
            elif hasattr(result, 'intermediate_steps'):
                intermediate_steps = result.intermediate_steps
            
            # Log successful execution
            self.audit_log.log_skill_execution(
                skill_name,
                params,
                True,
                duration_ms,
                error=None,
            )
            
            return SkillExecutionResult(
                success=True,
                output=result,
                duration_ms=duration_ms,
                rollback_actions=rollback_actions,
                intermediate_steps=intermediate_steps,
            )
            
        except asyncio.TimeoutError:
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            error_msg = f"BaseSkill '{skill_name}' timed out after {timeout_ms}ms"
            logger.error(error_msg)
            
            await self._on_skill_error(skill, error_msg)
            
            self.audit_log.log_skill_execution(
                skill_name,
                params,
                False,
                duration_ms,
                error=error_msg,
            )
            
            return SkillExecutionResult(
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
                intermediate_steps=intermediate_steps,
            )
            
        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() * 1000) - start_time
            error_msg = f"BaseSkill '{skill_name}' failed: {str(e)}"
            logger.exception(error_msg)
            
            await self._on_skill_error(skill, error_msg)
            
            self.audit_log.log_skill_execution(
                skill_name,
                params,
                False,
                duration_ms,
                error=error_msg,
            )
            
            return SkillExecutionResult(
                success=False,
                error=error_msg,
                duration_ms=duration_ms,
                intermediate_steps=intermediate_steps,
            )
        
        finally:
            await self._on_skill_end(skill)
    
    def _validate_params(
        self, 
        skill: BaseSkill, 
        params: dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Validate skill parameters against schema.
        
        Args:
            skill: BaseSkill instance
            params: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = getattr(skill, 'schema', None)
        if schema is None:
            return True, None
        
        required = schema.get('required', [])
        for param in required:
            if param not in params:
                return False, f"Missing required parameter: {param}"
        
        return True, None
    
    def _create_skill_context(
        self, 
        global_context: dict[str, Any], 
        params: dict[str, Any]
    ) -> dict[str, Any]:
        """Create isolated context for skill execution.
        
        Args:
            global_context: Global execution context
            params: BaseSkill-specific parameters
            
        Returns:
            Combined context for skill execution
        """
        return {
            **global_context,
            'params': params,
            'shared': {},  # For skill to store intermediate state
        }
    
    async def _on_skill_start(self, skill: BaseSkill, context: dict[str, Any]):
        """Called when a skill starts execution."""
        if hasattr(skill, 'on_start'):
            try:
                await skill.on_start(context)
            except Exception as e:
                logger.warning(f"BaseSkill on_start hook failed: {e}")
    
    async def _on_skill_end(self, skill: BaseSkill):
        """Called when a skill finishes execution."""
        if hasattr(skill, 'on_end'):
            try:
                await skill.on_end()
            except Exception as e:
                logger.warning(f"BaseSkill on_end hook failed: {e}")
    
    async def _on_skill_error(self, skill: BaseSkill, error: str):
        """Called when a skill encounters an error."""
        if hasattr(skill, 'on_error'):
            try:
                await skill.on_error(error)
            except Exception as e:
                logger.warning(f"BaseSkill on_error hook failed: {e}")
    
    async def _invoke_skill(self, skill: BaseSkill, context: dict[str, Any]) -> Any:
        """Invoke a skill with the given context.
        
        Args:
            skill: BaseSkill instance
            context: Execution context
            
        Returns:
            BaseSkill execution result
        """
        if asyncio.iscoroutinefunction(skill.execute):
            return await skill.execute(context)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: skill.execute(context)
            )
    
    def get_skill_info(self, skill_name: str) -> Optional[dict[str, Any]]:
        """Get information about a specific skill.
        
        Args:
            skill_name: Name of the skill
            
        Returns:
            BaseSkill metadata or None if not found
        """
        if skill_name not in self._skills_registry:
            return None
        
        skill = self._skills_registry[skill_name]
        return {
            'name': skill_name,
            'description': getattr(skill, 'description', 'No description'),
            'schema': getattr(skill, 'schema', {}),
            'category': getattr(skill, 'category', 'unknown'),
        }
    
    def list_skills(self) -> list[str]:
        """List all available skill names."""
        return list(self._skills_registry.keys())
