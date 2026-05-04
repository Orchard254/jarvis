"""
jarvis/core/json_utils.py — Robust JSON Handling Utilities

Centralized JSON parsing, validation, and normalization utilities
to handle LLM output inconsistencies and prevent future JSON-related bugs.

Features:
- Extract JSON from markdown code blocks
- Normalize parameter field names (params/arguments/parameters)
- Validate JSON structure against expected schema
- Fallback parsing strategies for malformed JSON
- Tool parameter normalization based on tool schemas
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


def extract_json_from_text(text: str, max_length: int = 10000) -> Optional[str]:
    """
    Extract JSON string from text that may contain markdown code blocks or explanations.
    
    Strategies:
    1. Look for ```json ... ``` blocks
    2. Look for ``` ... ``` blocks  
    3. Look for {...} or [...] patterns
    4. Try to parse the entire text as JSON
    
    Args:
        text: Raw text that may contain JSON
        max_length: Maximum length of JSON to extract (prevents parsing huge truncated content)
        
    Returns:
        Extracted JSON string or None if not found
    """
    if not text or not isinstance(text, str):
        return None
    
    text = text.strip()
    
    # Strategy 1: Look for ```json code blocks
    json_pattern = r'```json\s*(.*?)\s*```'
    matches = re.findall(json_pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        json_content = matches[0].strip()
        if len(json_content) > max_length:
            logger.warning(f"JSON content too long ({len(json_content)} chars), truncating to {max_length}")
            json_content = json_content[:max_length]
        logger.debug("Extracted JSON from ```json block")
        return json_content
    
    # Strategy 2: Look for generic ``` code blocks
    code_pattern = r'```\s*(.*?)\s*```'
    matches = re.findall(code_pattern, text, re.DOTALL)
    if matches:
        logger.debug("Extracted JSON from ``` block")
        return matches[0].strip()
    
    # Strategy 3: Look for JSON object or array patterns
    # Find the first { that looks like JSON start
    brace_start = text.find('{')
    bracket_start = text.find('[')
    
    if brace_start != -1 or bracket_start != -1:
        # Determine which comes first
        start_idx = max(brace_start, bracket_start) if brace_start == -1 or bracket_start == -1 else min(brace_start, bracket_start)
        candidate = text[start_idx:]
        
        # Try to find matching closing brace/bracket
        try:
            # Simple approach: try parsing progressively larger substrings
            for end_idx in range(len(candidate), 0, -1):
                substr = candidate[:end_idx]
                try:
                    json.loads(substr)
                    logger.debug(f"Extracted JSON by bracket matching ({len(substr)} chars)")
                    return substr
                except json.JSONDecodeError:
                    continue
        except Exception:
            pass
    
    # Strategy 4: Try parsing entire text as JSON
    try:
        json.loads(text)
        logger.debug("Parsed entire text as JSON")
        return text
    except json.JSONDecodeError:
        pass
    
    logger.warning(f"Could not extract JSON from text: {text[:100]}...")
    return None


def parse_json_safely(text: str, default: Any = None, max_json_length: int = 10000) -> Any:
    """
    Safely parse JSON from text with multiple fallback strategies.
    
    Args:
        text: Text containing JSON
        default: Default value if parsing fails
        max_json_length: Maximum length of JSON to extract (prevents parsing huge truncated content)
        
    Returns:
        Parsed JSON object or default value
    """
    if not text:
        return default
    
    # First extract JSON from potential markdown wrapping
    json_str = extract_json_from_text(text, max_length=max_json_length)
    if not json_str:
        logger.warning("No JSON could be extracted from text")
        return default
    
    # Try to parse the extracted JSON
    try:
        result = json.loads(json_str)
        logger.debug(f"Successfully parsed JSON: {type(result).__name__}")
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed: {e}")
        
        # Try to fix common JSON issues
        fixed_json = _fix_common_json_issues(json_str)
        if fixed_json:
            try:
                result = json.loads(fixed_json)
                logger.info("Successfully parsed JSON after applying fixes")
                return result
            except json.JSONDecodeError:
                pass
        
        return default


def _fix_common_json_issues(json_str: str) -> Optional[str]:
    """
    Attempt to fix common JSON formatting issues.
    
    Fixes:
    - Unquoted keys (JavaScript-style)
    - Single quotes instead of double quotes
    - Trailing commas
    - Non-ASCII characters that break JSON
    - Missing quotes around string values
    
    Args:
        json_str: Potentially malformed JSON string
        
    Returns:
        Fixed JSON string or None if cannot fix
    """
    fixed = json_str
    
    # Fix 1: Replace single quotes with double quotes (carefully)
    # This is risky, so only do simple cases
    # Skip for now as it can break strings containing apostrophes
    
    # Fix 2: Remove ALL trailing commas before } or ] (not just at end)
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*]', ']', fixed)
    
    # Fix 3: Quote unquoted keys (simple pattern)
    # Match word characters followed by : that aren't already quoted
    fixed = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed)
    
    # Fix 4: Replace non-breaking spaces and other special whitespace
    fixed = fixed.replace('\u00a0', ' ')  # Non-breaking space
    fixed = fixed.replace('\u2011', '-')  # Non-breaking hyphen
    fixed = fixed.replace('\u2013', '-')  # En dash
    fixed = fixed.replace('\u2014', '-')  # Em dash
    
    # Fix 5: Escape control characters
    fixed = re.sub(r'[\x00-\x1f\x7f]', lambda m: f'\\u{ord(m.group()):04x}', fixed)
    
    return fixed if fixed != json_str else None


def normalize_plan_parameters(step_dict: Dict[str, Any], tool_name: str, 
                              tool_schema: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Normalize parameter field names from LLM output to match tool expectations.
    
    Handles various field name conventions:
    - params, parameters, arguments, args
    - Direct field inclusion (app_name at top level)
    - Nested structures
    
    Args:
        step_dict: Raw step dictionary from LLM
        tool_name: Name of the tool being called
        tool_schema: Optional tool schema for validation
        
    Returns:
        Normalized parameters dictionary
    """
    if not isinstance(step_dict, dict):
        logger.warning(f"Step dict is not a dictionary: {type(step_dict)}")
        return {}
    
    # Collect parameters from various possible locations
    params = {}
    
    # Check for parameter containers (in priority order)
    param_containers = ['params', 'parameters', 'arguments', 'args', 'inputs']
    for container in param_containers:
        if container in step_dict and isinstance(step_dict[container], dict):
            params.update(step_dict[container])
            logger.debug(f"Extracted parameters from '{container}' field")
            break
    
    # Also check for direct parameter inclusion at top level
    # Exclude known non-parameter fields
    exclude_fields = {'tool', 'tool_name', 'description', 'reason', 'goal', 
                      'confidence', 'corrections', 'steps', 'params', 'parameters',
                      'arguments', 'args', 'inputs'}
    
    for key, value in step_dict.items():
        if key not in exclude_fields:
            params[key] = value
            logger.debug(f"Included direct parameter: {key}")
    
    # Special handling for common tools with frequent parameter issues
    params = _apply_tool_specific_normalization(tool_name, params, step_dict)
    
    # Validate against schema if provided
    if tool_schema:
        params = _validate_against_schema(params, tool_schema)
    
    return params


def _apply_tool_specific_normalization(tool_name: str, params: Dict[str, Any], 
                                       step_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply tool-specific parameter normalization rules.
    
    Handles common patterns where LLM uses different field names for specific tools.
    
    Args:
        tool_name: Name of the tool
        params: Current parameters dict
        step_dict: Original step dict for fallback lookups
        
    Returns:
        Normalized parameters dict
    """
    normalized = dict(params)  # Copy to avoid mutating input
    
    # open_app tool: LLM often puts app name in various fields
    if tool_name == 'open_app':
        if 'app_name' not in normalized or not normalized.get('app_name'):
            # Try alternative field names in both step_dict and normalized params
            alt_fields = ['application', 'app', 'name', 'program', 'software']
            for field in alt_fields:
                # Check in normalized params first (already extracted from params container)
                if field in normalized and normalized[field]:
                    normalized['app_name'] = normalized[field]
                    # Remove the alternative field to avoid "multiple values" error
                    del normalized[field]
                    logger.debug(f"Mapped {field} -> app_name")
                    break
                # Then check in top-level step_dict
                elif field in step_dict and step_dict[field]:
                    normalized['app_name'] = step_dict[field]
                    logger.debug(f"Found app_name in alternative field: {field}")
                    break
            
            # Last resort: check if app name is in description
            if 'app_name' not in normalized and 'description' in step_dict:
                desc = step_dict['description'].lower()
                # Common pattern: "Open [app name]" or "Launch [app name]"
                match = re.search(r'(?:open|launch|start)\s+(?:the\s+)?(\w+)', desc, re.IGNORECASE)
                if match:
                    normalized['app_name'] = match.group(1)
                    logger.debug(f"Extracted app_name from description: {normalized['app_name']}")
    
    # navigate_to_url: LLM might use 'url', 'website', 'link', 'address'
    if tool_name == 'navigate_to_url':
        if 'url' not in normalized:
            alt_fields = ['website', 'link', 'address', 'page', 'destination']
            for field in alt_fields:
                if field in step_dict and step_dict[field]:
                    normalized['url'] = step_dict[field]
                    logger.debug(f"Found url in alternative field: {field}")
                    break
    
    # search_web: might use 'query', 'search_term', 'text', 'keywords'
    if tool_name in ['search_web', 'web_search']:
        if 'query' not in normalized:
            alt_fields = ['search_term', 'text', 'keywords', 'search_query', 'term']
            for field in alt_fields:
                if field in step_dict and step_dict[field]:
                    normalized['query'] = step_dict[field]
                    logger.debug(f"Found query in alternative field: {field}")
                    break
    
    # file operations: might use 'path', 'file_path', 'filepath', 'file'
    if tool_name in ['read_file', 'write_file', 'delete_file', 'create_file']:
        if 'path' not in normalized:
            alt_fields = ['file_path', 'filepath', 'file', 'filename', 'location']
            for field in alt_fields:
                if field in step_dict and step_dict[field]:
                    normalized['path'] = step_dict[field]
                    logger.debug(f"Found path in alternative field: {field}")
                    break
    
    # press_key: LLM might use 'key' instead of 'keys'
    if tool_name == 'press_key':
        if 'keys' not in normalized:
            alt_fields = ['key', 'keystroke', 'shortcut', 'combination']
            for field in alt_fields:
                if field in step_dict and step_dict[field]:
                    normalized['keys'] = step_dict[field]
                    logger.debug(f"Found keys in alternative field: {field}")
                    break
        # Also handle case where 'key' is in normalized params (already extracted)
        elif 'key' in normalized and 'keys' in normalized:
            # If both exist, prefer 'keys' but log warning
            if normalized['key'] and not normalized['keys']:
                normalized['keys'] = normalized['key']
            del normalized['key']  # Remove to avoid conflicts
            logger.debug("Normalized 'key' parameter for press_key tool")
    
    return normalized


def _validate_against_schema(params: Dict[str, Any], 
                             tool_schema: Dict) -> Dict[str, Any]:
    """
    Validate and filter parameters against tool schema.
    
    Removes unknown parameters and ensures required parameters are present.
    
    Args:
        params: Parameters to validate
        tool_schema: Tool schema with parameter definitions
        
    Returns:
        Filtered parameters dict (only valid parameters included)
    """
    if not isinstance(params, dict) or not isinstance(tool_schema, dict):
        return params
    
    schema_params = tool_schema.get('parameters', {})
    required = tool_schema.get('required_parameters', [])
    
    # Filter to only known parameters
    filtered = {}
    for key, value in params.items():
        if key in schema_params:
            filtered[key] = value
        else:
            logger.debug(f"Filtering out unknown parameter: {key}")
    
    # Check required parameters
    missing_required = [req for req in required if req not in filtered]
    if missing_required:
        logger.warning(f"Missing required parameters: {missing_required}")
    
    return filtered


def validate_plan_structure(plan: Any) -> Tuple[bool, str]:
    """
    Validate that a plan has the minimum required structure.
    
    Args:
        plan: Plan object to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if plan is None:
        return False, "Plan is None"
    
    if not isinstance(plan, dict):
        return False, f"Plan is not a dictionary: {type(plan)}"
    
    if 'steps' not in plan:
        return False, "Plan missing 'steps' field"
    
    steps = plan.get('steps')
    if not isinstance(steps, list):
        return False, f"'steps' is not a list: {type(steps)}"
    
    if len(steps) == 0:
        return False, "Plan has no steps"
    
    # Validate each step has minimum required fields
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"Step {i} is not a dictionary: {type(step)}"
        
        # Must have a tool identifier
        has_tool = any(key in step for key in ['tool', 'tool_name', 'action'])
        if not has_tool:
            return False, f"Step {i} missing tool identifier"
    
    return True, ""


def safe_get_nested(data: Dict, *keys, default: Any = None) -> Any:
    """
    Safely get a value from nested dictionaries.
    
    Args:
        data: Dictionary to search
        *keys: Sequence of keys to traverse
        default: Default value if key path not found
        
    Returns:
        Value at key path or default
        
    Example:
        safe_get_nested(plan, 'steps', 0, 'params', 'url', default='')
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            if 0 <= key < len(current):
                current = current[key]
            else:
                return default
        else:
            return default
        
        if current is None:
            return default
    
    return current
