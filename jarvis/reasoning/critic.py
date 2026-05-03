"""
Critic - Plan reviewer and validator.
Reviews plans before execution to catch errors and suggest improvements.

MUST run after every plan before execution.
Checks in order:
a. All tool names exist in registry
b. All required parameters are present  
c. No conflicting steps (open+close same app)
d. No destructive steps without confirmation flag
e. Execution order respects dependencies
f. Estimated total duration is reasonable (under 5 min)

Returns: APPROVED, NEEDS_REVISION, or BLOCKED
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum


class CriticDecision(Enum):
    """Possible critic decisions."""
    APPROVED = "APPROVED"
    NEEDS_REVISION = "NEEDS_REVISION"
    BLOCKED = "BLOCKED"


class CriticResult:
    """Result of a critic review."""
    
    def __init__(
        self,
        decision: CriticDecision,
        issues: List[str] = None,
        fixes_needed: List[str] = None,
        blocked_reason: str = None,
        warnings: List[str] = None
    ):
        self.decision = decision
        self.issues = issues or []
        self.fixes_needed = fixes_needed or []
        self.blocked_reason = blocked_reason
        self.warnings = warnings or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'decision': self.decision.value,
            'issues': self.issues,
            'fixes_needed': self.fixes_needed,
            'blocked_reason': self.blocked_reason,
            'warnings': self.warnings
        }
    
    @classmethod
    def approved(cls, warnings: List[str] = None) -> 'CriticResult':
        """Create an approved result."""
        return cls(decision=CriticDecision.APPROVED, warnings=warnings)
    
    @classmethod
    def needs_revision(cls, fixes_needed: List[str], 
                       issues: List[str] = None) -> 'CriticResult':
        """Create a needs revision result."""
        return cls(
            decision=CriticDecision.NEEDS_REVISION,
            issues=issues or [],
            fixes_needed=fixes_needed
        )
    
    @classmethod
    def blocked(cls, reason: str, issues: List[str] = None) -> 'CriticResult':
        """Create a blocked result."""
        return cls(
            decision=CriticDecision.BLOCKED,
            blocked_reason=reason,
            issues=issues or []
        )


class PlanCritic:
    """
    Reviews and critiques plans before execution.
    
    Checks in strict order:
    a. All tool names exist in registry
    b. All required parameters are present  
    c. No conflicting steps (open+close same app)
    d. No destructive steps without confirmation flag
    e. Execution order respects dependencies
    f. Estimated total duration is reasonable (under 5 min)
    """
    
    # Maximum allowed duration in seconds (5 minutes)
    MAX_DURATION_SECONDS = 300
    
    # Tools that require confirmation flag
    DESTRUCTIVE_TOOLS = {
        'delete_file', 'delete_folder', 'remove_file',
        'run_command', 'run_powershell', 'run_shell',
        'close_app', 'kill_process', 'terminate',
        'shutdown_system', 'restart_system', 'format_drive',
        'overwrite_file', 'truncate_file'
    }
    
    # Confirmation parameter names
    CONFIRMATION_PARAMS = {'confirm', 'confirmation', 'force', 'yes', 'skip_confirm'}
    
    def __init__(self, ollama_client=None, tool_registry=None):
        """
        Initialize the plan critic.
        
        Args:
            ollama_client: OllamaClient instance for review
            tool_registry: ToolRegistry instance for validation
        """
        self.ollama_client = ollama_client
        self.tool_registry = tool_registry
        self.review_history = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def set_tool_registry(self, registry) -> None:
        """Set the tool registry."""
        self.tool_registry = registry
    
    def review_plan(self, execution_graph: Any, 
                    goal: str = None) -> CriticResult:
        """
        Review a plan and provide feedback.
        
        MUST run after every plan before execution.
        
        Args:
            execution_graph: ExecutionGraph object with steps
            goal: The overall goal (optional)
            
        Returns:
            CriticResult with decision: APPROVED, NEEDS_REVISION, or BLOCKED
        """
        # Extract steps from execution graph
        if hasattr(execution_graph, 'steps'):
            steps = execution_graph.steps
            total_duration = getattr(execution_graph, 'total_estimated_duration', 0)
        elif isinstance(execution_graph, dict):
            steps_data = execution_graph.get('steps', [])
            # Handle both ExecutionStep objects and dicts
            steps = []
            for s in steps_data:
                if hasattr(s, 'to_dict'):
                    steps.append(s.to_dict())
                else:
                    steps.append(s)
            total_duration = execution_graph.get('total_estimated_duration', 0)
        else:
            # Assume it's a list of steps
            steps = execution_graph
            total_duration = 0
        
        # Convert steps to dict format for analysis
        step_dicts = []
        for step in steps:
            if hasattr(step, 'to_dict'):
                step_dicts.append(step.to_dict())
            elif isinstance(step, dict):
                step_dicts.append(step)
            else:
                step_dicts.append({'tool_or_skill': str(step)})
        
        # Run checks IN ORDER as specified
        result = self._run_ordered_checks(step_dicts, total_duration)
        
        # Store in history
        self.review_history.append({
            'goal': goal[:200] if goal else 'Unknown',
            'num_steps': len(steps),
            'result': result.to_dict(),
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep history bounded
        if len(self.review_history) > 50:
            self.review_history = self.review_history[-50:]
        
        return result
    
    def _run_ordered_checks(self, steps: List[Dict[str, Any]], 
                            total_duration: float) -> CriticResult:
        """Run all checks in the specified order."""
        all_issues = []
        all_fixes = []
        all_warnings = []
        
        # a. Check all tool names exist in registry
        tool_check_result = self._check_tool_names_exist(steps)
        if tool_check_result['has_issues']:
            # BLOCKED - tools don't exist
            return CriticResult.blocked(
                reason=f"Unknown tools found: {', '.join(tool_check_result['unknown_tools'])}",
                issues=tool_check_result['issues']
            )
        
        # b. Check all required parameters are present
        params_check_result = self._check_required_parameters(steps)
        if params_check_result['has_issues']:
            # NEEDS_REVISION - missing parameters
            all_issues.extend(params_check_result['issues'])
            all_fixes.extend(params_check_result['fixes'])
        
        # c. Check for conflicting steps (open+close same app)
        conflict_check_result = self._check_conflicting_steps(steps)
        if conflict_check_result['has_issues']:
            # NEEDS_REVISION - conflicts detected
            all_issues.extend(conflict_check_result['issues'])
            all_fixes.extend(conflict_check_result['fixes'])
        
        # d. Check for destructive steps without confirmation
        destructive_check_result = self._check_destructive_steps(steps)
        if destructive_check_result['has_issues']:
            # BLOCKED - dangerous operations without confirmation
            return CriticResult.blocked(
                reason="Destructive operations without confirmation flag",
                issues=destructive_check_result['issues']
            )
        
        # e. Check execution order respects dependencies
        dependency_check_result = self._check_dependencies(steps)
        if dependency_check_result['has_issues']:
            # NEEDS_REVISION - dependency issues
            all_issues.extend(dependency_check_result['issues'])
            all_fixes.extend(dependency_check_result['fixes'])
        
        # f. Check estimated total duration is reasonable (under 5 min)
        duration_check_result = self._check_duration(total_duration, steps)
        if duration_check_result['has_issues']:
            # NEEDS_REVISION - too long
            all_issues.extend(duration_check_result['issues'])
            all_fixes.extend(duration_check_result['fixes'])
        
        # Determine final decision
        if all_issues:
            return CriticResult.needs_revision(
                fixes_needed=all_fixes,
                issues=all_issues
            )
        
        # Add any warnings
        if all_warnings:
            return CriticResult.approved(warnings=all_warnings)
        
        return CriticResult.approved()
    
    def _check_tool_names_exist(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check a: All tool names exist in registry."""
        unknown_tools = []
        issues = []
        
        for i, step in enumerate(steps):
            tool_name = step.get('tool_or_skill', step.get('tool', ''))
            if not tool_name:
                issues.append(f"Step {i+1}: Missing tool name")
                continue
            
            # Check against registry if available
            if self.tool_registry:
                if not self.tool_registry.has_tool(tool_name):
                    unknown_tools.append(tool_name)
                    issues.append(f"Step {i+1}: Unknown tool '{tool_name}'")
        
        return {
            'has_issues': len(unknown_tools) > 0,
            'unknown_tools': unknown_tools,
            'issues': issues
        }
    
    def _check_required_parameters(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check b: All required parameters are present."""
        issues = []
        fixes = []
        
        for i, step in enumerate(steps):
            tool_name = step.get('tool_or_skill', step.get('tool', ''))
            params = step.get('params', {})
            
            if not self.tool_registry:
                continue
            
            # Get tool schema
            tool_info = self.tool_registry.get_tool_info(tool_name)
            if not tool_info:
                continue
            
            # Check required parameters
            required_params = getattr(tool_info, 'required_parameters', [])
            if not required_params and hasattr(tool_info, 'parameters'):
                # Infer required params from schema
                param_schema = tool_info.parameters
                if isinstance(param_schema, dict):
                    required_params = [
                        p for p, spec in param_schema.items()
                        if isinstance(spec, dict) and spec.get('required', False)
                    ]
            
            for req_param in required_params:
                if req_param not in params:
                    issues.append(
                        f"Step {i+1} ({tool_name}): Missing required parameter '{req_param}'"
                    )
                    fixes.append(
                        f"Add '{req_param}' parameter to step {i+1}"
                    )
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues,
            'fixes': fixes
        }
    
    def _check_conflicting_steps(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check c: No conflicting steps (open+close same app)."""
        issues = []
        fixes = []
        
        # Track resource states
        opened_resources = {}  # resource -> step_index
        closed_resources = set()
        
        for i, step in enumerate(steps):
            tool_name = step.get('tool_or_skill', step.get('tool', '')).lower()
            params = step.get('params', {})
            
            # Identify resource being manipulated
            resource = None
            if 'app' in tool_name or 'application' in tool_name:
                resource = params.get('app_name', params.get('name', params.get('path', '')))
            elif 'file' in tool_name:
                resource = params.get('path', params.get('file', ''))
            
            if not resource:
                continue
            
            # Check for open/close conflicts
            if 'open' in tool_name and 'close' not in tool_name:
                if resource in closed_resources:
                    issues.append(
                        f"Step {i+1}: Opening '{resource}' after it was closed"
                    )
                    fixes.append(
                        f"Remove duplicate open or add reopen logic for '{resource}'"
                    )
                opened_resources[resource] = i
                
            elif 'close' in tool_name or 'kill' in tool_name:
                if resource not in opened_resources:
                    # Closing something that wasn't opened in this plan
                    # This might be OK if it was already open
                    pass
                else:
                    closed_resources.add(resource)
        
        # Check for immediate open/close pairs
        for resource, open_idx in opened_resources.items():
            if resource in closed_resources:
                # Find the close step
                for i, step in enumerate(steps):
                    tool_name = step.get('tool_or_skill', step.get('tool', '')).lower()
                    if ('close' in tool_name or 'kill' in tool_name):
                        params = step.get('params', {})
                        step_resource = params.get('app_name', params.get('name', params.get('path', '')))
                        if step_resource == resource and i == open_idx + 1:
                            issues.append(
                                f"Steps {open_idx+1}-{i+1}: Opening and immediately closing '{resource}'"
                            )
                            fixes.append(
                                f"Remove redundant open/close pair or add operations between them"
                            )
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues,
            'fixes': fixes
        }
    
    def _check_destructive_steps(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check d: No destructive steps without confirmation flag."""
        issues = []
        
        for i, step in enumerate(steps):
            tool_name = step.get('tool_or_skill', step.get('tool', '')).lower()
            params = step.get('params', {})
            
            # Check if this is a destructive tool
            is_destructive = any(
                destructive in tool_name 
                for destructive in self.DESTRUCTIVE_TOOLS
            )
            
            if is_destructive:
                # Check for confirmation flag
                has_confirmation = any(
                    param in self.CONFIRMATION_PARAMS 
                    for param in params.keys()
                )
                
                # Also check if any param value is explicitly True for confirmation-like keys
                if not has_confirmation:
                    for key, value in params.items():
                        if key in {'confirm', 'force', 'yes'} and value is True:
                            has_confirmation = True
                            break
                
                if not has_confirmation:
                    issues.append(
                        f"Step {i+1} ({tool_name}): Destructive operation without confirmation flag"
                    )
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues
        }
    
    def _check_dependencies(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check e: Execution order respects dependencies."""
        issues = []
        fixes = []
        
        step_ids = {step.get('id', f'step_{i}') for i, step in enumerate(steps)}
        
        for i, step in enumerate(steps):
            step_id = step.get('id', f'step_{i}')
            depends_on = step.get('depends_on', [])
            
            for dep_id in depends_on:
                # Check if dependency exists
                if dep_id not in step_ids:
                    issues.append(
                        f"Step {i+1} ({step_id}): Depends on non-existent step '{dep_id}'"
                    )
                    fixes.append(
                        f"Fix dependency reference in step {i+1}"
                    )
                
                # Check if dependency comes before this step
                dep_idx = None
                for j, s in enumerate(steps):
                    if s.get('id', f'step_{j}') == dep_id:
                        dep_idx = j
                        break
                
                if dep_idx is not None and dep_idx >= i:
                    issues.append(
                        f"Step {i+1} ({step_id}): Dependency '{dep_id}' comes after this step"
                    )
                    fixes.append(
                        f"Reorder steps so '{dep_id}' comes before step {i+1}"
                    )
        
        # Check for circular dependencies
        visited = set()
        rec_stack = set()
        
        def has_cycle(step_id: str, path: List[str]) -> bool:
            if step_id in rec_stack:
                cycle_path = ' -> '.join(path + [step_id])
                issues.append(f"Circular dependency detected: {cycle_path}")
                fixes.append("Break the circular dependency by reordering steps")
                return True
            
            if step_id in visited:
                return False
            
            visited.add(step_id)
            rec_stack.add(step_id)
            
            # Find step
            for i, step in enumerate(steps):
                if step.get('id', f'step_{i}') == step_id:
                    for dep in step.get('depends_on', []):
                        if has_cycle(dep, path + [step_id]):
                            return True
                    break
            
            rec_stack.remove(step_id)
            return False
        
        for i, step in enumerate(steps):
            step_id = step.get('id', f'step_{i}')
            if step_id not in visited:
                has_cycle(step_id, [])
        
        return {
            'has_issues': len(issues) > 0,
            'issues': issues,
            'fixes': fixes
        }
    
    def _check_duration(self, total_duration: float, 
                        steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check f: Estimated total duration is reasonable (under 5 min)."""
        issues = []
        fixes = []
        
        # Use provided duration or estimate from steps
        duration = total_duration
        if duration <= 0:
            # Estimate based on number of steps (assume 10s per step average)
            duration = len(steps) * 10
        
        if duration > self.MAX_DURATION_SECONDS:
            minutes = duration / 60
            issues.append(
                f"Estimated duration ({minutes:.1f} minutes) exceeds maximum (5 minutes)"
            )
            fixes.append(
                "Break task into smaller sub-tasks or optimize steps"
            )
        
        return {
            'has_issues': duration > self.MAX_DURATION_SECONDS,
            'issues': issues,
            'fixes': fixes
        }
    
    def quick_check(self, steps: List[Dict[str, Any]]) -> bool:
        """
        Quick safety check - returns True if plan is safe to execute.
        
        Only checks for blocking issues (unknown tools, destructive without confirm).
        """
        # Check tool names
        tool_check = self._check_tool_names_exist(steps)
        if tool_check['has_issues']:
            return False
        
        # Check destructive steps
        destructive_check = self._check_destructive_steps(steps)
        if destructive_check['has_issues']:
            return False
        
        return True
    
    def get_review_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent review history."""
        return self.review_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear review history."""
        self.review_history = []


# Singleton instance
_critic_instance = None

def get_critic(ollama_client=None, tool_registry=None) -> PlanCritic:
    """Get the singleton PlanCritic instance."""
    global _critic_instance
    if _critic_instance is None:
        _critic_instance = PlanCritic(ollama_client, tool_registry)
    else:
        if ollama_client:
            _critic_instance.set_client(ollama_client)
        if tool_registry:
            _critic_instance.set_tool_registry(tool_registry)
    return _critic_instance
