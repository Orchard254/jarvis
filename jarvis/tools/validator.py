"""
tools/validator.py — Tool Call Validator

Provides strict validation of tool calls before execution:
1. Validates tool exists in registry
2. Validates args match schema (types, required fields, enums)
3. Fails fast with descriptive error messages

This is a critical safety layer that prevents invalid tool calls
from reaching execution.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseTool, ToolResult
from .registry import get_registry, ToolRegistry

logger = logging.getLogger("tool_validator")


class ToolCallValidator:
    """
    Validates tool calls against the registry and schemas.
    
    Validation pipeline:
    1. Check tool exists in registry
    2. Validate required parameters are present
    3. Validate parameter types match schema
    4. Validate enum constraints if present
    5. Run tool-specific validation
    """
    
    def __init__(self, registry: Optional[ToolRegistry] = None):
        """
        Initialize validator with optional registry.
        
        Args:
            registry: ToolRegistry instance. If None, uses global registry.
        """
        self._registry = registry or get_registry()
    
    def validate(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Validate a tool call completely.
        
        Args:
            tool_name: Name of tool to validate
            args: Arguments dict to validate
            
        Returns:
            Tuple of (is_valid, error_message)
            If valid: (True, "")
            If invalid: (False, "Description of validation failure")
        """
        # Step 1: Check tool exists
        tool = self._registry.get(tool_name)
        if tool is None:
            available = sorted(self._registry.get_tool_names())
            similar = [t for t in available if tool_name.lower() in t.lower()]
            
            error = f"Tool '{tool_name}' does not exist"
            if similar:
                error += f". Did you mean: {', '.join(similar[:3])}?"
            error += f". Available tools: {', '.join(available[:10])}"
            if len(available) > 10:
                error += f"... ({len(available)} total)"
            
            logger.warning(f"Validation failed - unknown tool: {tool_name}")
            return False, error
        
        # Step 2: Validate required parameters
        required_params = getattr(tool, 'required_parameters', [])
        for param in required_params:
            if param not in args:
                logger.warning(f"Validation failed - missing required param '{param}' for {tool_name}")
                return False, f"Missing required parameter: '{param}'"
        
        # Step 3: Validate parameter types and constraints
        type_error = self._validate_parameter_types(tool, args)
        if type_error:
            logger.warning(f"Validation failed - type error: {type_error}")
            return False, type_error
        
        # Step 4: Run tool-specific validation (includes semantic checks)
        is_valid, error_msg = tool.validate(**args)
        if not is_valid:
            logger.warning(f"Validation failed - tool validation: {error_msg}")
            return False, error_msg
        
        # Step 5: Semantic safety check (NEW)
        # Check for dangerous patterns that schema validation won't catch
        semantic_error = self._semantic_safety_check(tool_name, args)
        if semantic_error:
            logger.warning(f"Validation failed - semantic safety: {semantic_error}")
            return False, semantic_error
        
        logger.debug(f"Validation passed for {tool_name}")
        return True, ""
    
    def _semantic_safety_check(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> Optional[str]:
        """
        Perform semantic safety validation that schema can't catch.
        
        Examples:
        - file.delete with path="C:\\" → dangerous (root of system drive)
        - file.write with path="/etc/passwd" → dangerous (system file)
        - system.run_command with "rm -rf /" → dangerous (destructive command)
        
        Args:
            tool_name: Tool being validated
            args: Tool arguments
            
        Returns:
            Error message if unsafe, None if safe
        """
        # Dangerous path patterns - exact matches or root directories only
        dangerous_root_paths = [
            "c:\\", "c:/",  # Root of system drive (lowercase for comparison)
            "/etc/", "/bin/", "/usr/", "/root/", "/",  # Linux system dirs
            "/System/", "/Applications/",  # macOS system dirs
        ]
        
        # Dangerous substrings that should never appear in paths
        dangerous_path_substrings = [
            "windows\\system32", "windows/system32",  # Windows system dir
            "/etc/passwd", "/etc/shadow",  # Critical Linux files
            "/bin/bash", "/bin/sh",  # Shell binaries (when used as file targets)
        ]
        
        # Dangerous commands
        dangerous_commands = [
            "rm -rf /", "deltree", "format c:", "fdisk",
            "shutdown -s -t 0", "shutdown /s /t 0",  # Immediate shutdown
        ]
        
        # Check file operations - only block truly dangerous paths
        if tool_name.startswith("file.") or "path" in args:
            path = args.get("path", "").lower().strip()
            
            # Check for exact root matches (too broad)
            for dangerous in dangerous_root_paths:
                if path == dangerous or path.rstrip('\\/') == dangerous.rstrip('\\/'):
                    return f"Dangerous path detected: '{args.get('path')}'. Operation not allowed for safety."
            
            # Check for dangerous substrings
            for dangerous in dangerous_path_substrings:
                if dangerous in path:
                    return f"Dangerous path detected: '{args.get('path')}'. System directory access not allowed."
        
        # Check command execution
        if "run_command" in tool_name or "execute" in tool_name:
            cmd = args.get("command", "").lower()
            for dangerous in dangerous_commands:
                if dangerous in cmd:
                    return f"Dangerous command detected: '{args.get('command')}'. Operation not allowed for safety."
        
        return None
    
    def _validate_parameter_types(
        self,
        tool: BaseTool,
        args: Dict[str, Any],
    ) -> Optional[str]:
        """
        Validate parameter types match the tool's schema.
        
        Args:
            tool: Tool instance
            args: Arguments to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        # Get schema - could be old format (dict) or new format (JSON Schema)
        params_schema = getattr(tool, 'parameters', {})
        
        # Handle new JSON Schema format
        if isinstance(params_schema, dict) and 'properties' in params_schema:
            properties = params_schema.get('properties', {})
        else:
            # Old format - params_schema is directly the properties dict
            properties = params_schema
        
        for param_name, param_value in args.items():
            if param_name not in properties:
                # Unknown parameter - may be allowed or not depending on strictness
                continue
            
            param_def = properties[param_name]
            
            # Handle JSON Schema format
            if isinstance(param_def, dict):
                expected_type = param_def.get('type')
                
                if expected_type:
                    type_error = self._check_type(param_name, param_value, expected_type)
                    if type_error:
                        return type_error
                
                # Check enum constraint
                enum_values = param_def.get('enum')
                if enum_values and param_value not in enum_values:
                    return f"Invalid value for '{param_name}': must be one of {enum_values}, got '{param_value}'"
        
        return None
    
    def _check_type(
        self,
        param_name: str,
        value: Any,
        expected_type: str,
    ) -> Optional[str]:
        """
        Check if a value matches the expected JSON Schema type.
        
        Args:
            param_name: Parameter name for error messages
            value: Value to check
            expected_type: Expected JSON Schema type string
            
        Returns:
            Error message if type mismatch, None if valid
        """
        # Handle nullable values
        if value is None:
            return None
        
        type_mapping = {
            'string': str,
            'integer': int,
            'number': (int, float),
            'boolean': bool,
            'array': list,
            'object': dict,
        }
        
        expected_python_type = type_mapping.get(expected_type)
        if expected_python_type is None:
            # Unknown type, skip validation
            return None
        
        # Special handling for integer vs number
        if expected_type == 'integer':
            if isinstance(value, bool) or not isinstance(value, int):
                return f"Parameter '{param_name}' must be an integer, got {type(value).__name__}"
        elif expected_type == 'number':
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"Parameter '{param_name}' must be a number, got {type(value).__name__}"
        elif expected_type == 'boolean':
            if not isinstance(value, bool):
                return f"Parameter '{param_name}' must be a boolean, got {type(value).__name__}"
        elif expected_type == 'string':
            if not isinstance(value, str):
                return f"Parameter '{param_name}' must be a string, got {type(value).__name__}"
        elif expected_type == 'array':
            if not isinstance(value, list):
                return f"Parameter '{param_name}' must be an array, got {type(value).__name__}"
        elif expected_type == 'object':
            if not isinstance(value, dict):
                return f"Parameter '{param_name}' must be an object, got {type(value).__name__}"
        
        return None
    
    def validate_from_parsed_call(
        self,
        parsed_call: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Validate a parsed tool call from the LLM.
        
        Expected format:
        {
            "type": "tool",
            "name": "<tool_name>",
            "args": {...}
        }
        
        Args:
            parsed_call: Parsed tool call dict
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate structure
        if not isinstance(parsed_call, dict):
            return False, "Tool call must be a dictionary"
        
        if parsed_call.get('type') != 'tool':
            return False, f"Invalid type: expected 'tool', got '{parsed_call.get('type')}'"
        
        name = parsed_call.get('name')
        if not name or not isinstance(name, str):
            return False, "Missing or invalid 'name' field"
        
        args = parsed_call.get('args', {})
        if not isinstance(args, dict):
            return False, f"'args' must be a dictionary, got {type(args).__name__}"
        
        # Delegate to main validate method
        return self.validate(name, args)


# Global validator instance
_validator: Optional[ToolCallValidator] = None


def get_validator() -> ToolCallValidator:
    """Get the global validator instance."""
    global _validator
    if _validator is None:
        _validator = ToolCallValidator()
    return _validator


def validate_tool_call(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a tool call using the global validator.
    
    Args:
        tool_name: Name of tool to validate
        args: Arguments dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    return get_validator().validate(tool_name, args)


def validate_parsed_call(parsed_call: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a parsed tool call using the global validator.
    
    Args:
        parsed_call: Parsed tool call dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    return get_validator().validate_from_parsed_call(parsed_call)
