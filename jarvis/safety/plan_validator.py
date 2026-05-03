"""
JARVIS Plan Validator - Reviews and validates execution plans before running.

Second layer of safety system. Analyzes multi-step plans for:
- Dangerous action sequences
- Circular dependencies
- Resource conflicts
- Missing prerequisites
- Excessive scope
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class PlanRiskLevel(Enum):
    """Risk assessment levels for plans."""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


@dataclass
class PlanValidationResult:
    """Result of plan validation."""
    is_valid: bool
    risk_level: PlanRiskLevel
    warnings: List[str] = field(default_factory=list)
    blocked_steps: List[int] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
    
    def add_suggestion(self, suggestion: str):
        self.suggestions.append(suggestion)
    
    def block_step(self, step_index: int, reason: str):
        self.blocked_steps.append(step_index)
        self.add_warning(f"Step {step_index} blocked: {reason}")


class PlanValidator:
    """
    Validates execution plans before they are run.
    
    Checks for:
    - Dangerous action combinations
    - Destructive operation chains
    - Missing error handling
    - Resource exhaustion risks
    - Logical inconsistencies
    """
    
    # Tools that are considered high-risk
    HIGH_RISK_TOOLS = {
        'delete_file',
        'run_powershell',
        'run_command',
        'run_python',
        'shutdown_pc',
        'restart_pc',
        'close_app',
        'focus_window',  # Could be used maliciously
    }
    
    # Tools that require confirmation when combined
    REQUIRES_CONFIRMATION_COMBOS = [
        {'delete_file', 'run_command'},
        {'shutdown_pc', 'delete_file'},
        {'restart_pc', 'run_command'},
        {'run_powershell', 'delete_file'},
    ]
    
    # Maximum steps in a single plan without explicit approval
    MAX_STEPS_WITHOUT_APPROVAL = 10
    
    # Maximum number of destructive operations allowed
    MAX_DESTRUCTIVE_OPS = 3
    
    # Destructive operation tools
    DESTRUCTIVE_TOOLS = {
        'delete_file',
        'shutdown_pc',
        'restart_pc',
        'close_app',
    }
    
    def review(self, plan: List[Dict[str, Any]]) -> PlanValidationResult:
        """
        Review a plan for safety issues.
        
        Args:
            plan: List of step dictionaries with 'tool_or_skill' and 'params' keys
            
        Returns:
            PlanValidationResult with validation details
        """
        result = PlanValidationResult(
            is_valid=True,
            risk_level=PlanRiskLevel.LOW
        )
        
        if not plan:
            result.is_valid = False
            result.add_warning("Empty plan")
            return result
        
        # Check plan length
        if len(plan) > self.MAX_STEPS_WITHOUT_APPROVAL:
            result.requires_confirmation = True
            result.add_suggestion(
                f"Plan has {len(plan)} steps (>{self.MAX_STEPS_WITHOUT_APPROVAL}). "
                "Consider breaking into smaller sub-tasks."
            )
        
        # Analyze each step
        tool_set = set()
        destructive_count = 0
        
        for i, step in enumerate(plan):
            step_result = self._validate_step(i, step)
            
            if not step_result[0]:  # is_valid
                result.is_valid = False
                result.block_step(i, step_result[1])  # reason
            
            # Use 'tool_or_skill' key (standard from ExecutionStep.to_dict())
            tool_name = step.get('tool_or_skill', '')
            tool_set.add(tool_name)
            
            if tool_name in self.DESTRUCTIVE_TOOLS:
                destructive_count += 1
            
            # Check for missing parameters (use 'params' key from ExecutionStep.to_dict())
            if 'params' not in step:
                result.add_warning(f"Step {i}: Missing 'params' key")
        
        # Check destructive operation limit
        if destructive_count > self.MAX_DESTRUCTIVE_OPS:
            result.risk_level = PlanRiskLevel.HIGH
            result.requires_confirmation = True
            result.add_warning(
                f"Plan contains {destructive_count} destructive operations "
                f"(limit: {self.MAX_DESTRUCTIVE_OPS})"
            )
        
        # Check for dangerous combinations
        for combo in self.REQUIRES_CONFIRMATION_COMBOS:
            if combo.issubset(tool_set):
                result.requires_confirmation = True
                result.add_warning(
                    f"Dangerous combination detected: {combo}. "
                    "Requires explicit user confirmation."
                )
        
        # Check for high-risk tool concentration
        high_risk_count = len(tool_set.intersection(self.HIGH_RISK_TOOLS))
        if high_risk_count >= 3:
            result.risk_level = PlanRiskLevel.HIGH
            result.requires_confirmation = True
            result.add_warning(
                f"Plan uses {high_risk_count} high-risk tools. "
                "Review carefully before execution."
            )
        
        # Detect potential loops
        if self._detect_potential_loop(plan):
            result.add_warning("Potential infinite loop detected in plan structure")
            result.add_suggestion("Add termination conditions or step limits")
        
        # Determine final risk level
        if result.blocked_steps:
            result.risk_level = PlanRiskLevel.CRITICAL
            result.is_valid = False
        elif result.requires_confirmation:
            if result.risk_level == PlanRiskLevel.LOW:
                result.risk_level = PlanRiskLevel.MEDIUM
        
        return result
    
    def _validate_step(self, index: int, step: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate an individual step.
        
        Returns:
            Tuple of (is_valid, reason_if_invalid)
        """
        # Use 'tool_or_skill' key (standard from ExecutionStep.to_dict())
        tool_name = step.get('tool_or_skill', '')
        # Use 'params' key (standard from ExecutionStep.to_dict())
        parameters = step.get('params', {})
        
        # Check for empty tool name
        if not tool_name:
            return False, "Missing tool name"
        
        # Check for obviously dangerous parameter patterns
        if isinstance(parameters, dict):
            for key, value in parameters.items():
                if isinstance(value, str):
                    # Check for path traversal in parameters
                    if '..' in value and ('path' in key.lower() or 'file' in key.lower()):
                        return False, f"Path traversal detected in parameter '{key}'"
                    
                    # Check for encoded commands
                    if 'command' in key.lower() and len(value) > 100 and value.count(' ') < 5:
                        return False, f"Potentially encoded command in parameter '{key}'"
        
        return True, None
    
    def _detect_potential_loop(self, plan: List[Dict[str, Any]]) -> bool:
        """
        Detect potential infinite loops in plan structure.
        
        Simple heuristic: looks for repeated tool calls with same parameters.
        """
        if len(plan) < 3:
            return False
        
        # Look for 3+ consecutive identical tool calls
        consecutive_same = 1
        last_tool = None
        last_params = None
        
        for step in plan:
            # Use 'tool_or_skill' key (standard from ExecutionStep.to_dict())
            tool = step.get('tool_or_skill', '')
            # Use 'params' key (standard from ExecutionStep.to_dict())
            params = str(step.get('params', {}))
            
            if tool == last_tool and params == last_params:
                consecutive_same += 1
                if consecutive_same >= 3:
                    return True
            else:
                consecutive_same = 1
            
            last_tool = tool
            last_params = params
        
        return False
    
    def get_safe_plan_subset(
        self, 
        plan: List[Dict[str, Any]], 
        max_steps: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get a safe subset of a plan (first N non-blocked steps).
        
        Useful for progressive execution with user confirmation.
        """
        result = []
        count = 0
        
        for i, step in enumerate(plan):
            is_valid, _ = self._validate_step(i, step)
            if is_valid:
                result.append(step)
                count += 1
                if count >= max_steps:
                    break
        
        return result
    
    def suggest_plan_modifications(
        self, 
        plan: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Suggest modifications to make a plan safer.
        
        Returns list of suggestion strings.
        """
        suggestions = []
        
        # Check if plan lacks error recovery
        has_error_handling = any(
            'on_error' in step or 'retry' in step 
            for step in plan
        )
        if not has_error_handling and len(plan) > 2:
            suggestions.append(
                "Consider adding error handling or retry logic for critical steps"
            )
        
        # Check for backup before destructive ops
        delete_indices = [
            i for i, step in enumerate(plan) 
            if step.get('tool_or_skill', '') in self.DESTRUCTIVE_TOOLS
        ]
        if delete_indices:
            has_backup = any(
                'backup' in str(step.get('params', {})).lower()
                or 'copy' in step.get('tool_or_skill', '').lower()
                for step in plan[:delete_indices[0]]
            )
            if not has_backup:
                suggestions.append(
                    "Create backups before destructive operations"
                )
        
        # Suggest breaking up long plans
        if len(plan) > self.MAX_STEPS_WITHOUT_APPROVAL:
            suggestions.append(
                f"Break plan into chunks of {self.MAX_STEPS_WITHOUT_APPROVAL} steps "
                "with intermediate verification"
            )
        
        return suggestions


# Singleton instance
_plan_validator: Optional[PlanValidator] = None


def get_plan_validator() -> PlanValidator:
    """Get the singleton plan validator instance."""
    global _plan_validator
    if _plan_validator is None:
        _plan_validator = PlanValidator()
    return _plan_validator


def reset_plan_validator():
    """Reset the singleton instance (for testing)."""
    global _plan_validator
    _plan_validator = None


def review_plan(plan: List[Dict[str, Any]]) -> PlanValidationResult:
    """Convenience function to review a plan using singleton validator."""
    return get_plan_validator().review(plan)
