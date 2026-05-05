"""
Tool Call Parser Module

Provides deterministic parsing of LLM outputs into executable tool calls.
Converts natural language tool references into structured action plans.
"""

import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


def is_tool_call(text: str) -> bool:
    """
    Detect if text contains a tool call pattern.
    
    Checks for:
    - "TOOL: tool_name(params)" pattern
    - JSON format with type="tool" or type="TOOL"
    - Simple patterns like "use tool_name" or "call tool_name"
    
    Args:
        text: The LLM output text to analyze
        
    Returns:
        True if text appears to be a tool call, False otherwise
    """
    if not text or not text.strip():
        return False
    
    text = text.strip()
    
    # Check for TOOL: pattern (case insensitive)
    if re.search(r'TOOL:\s*\w+', text, re.IGNORECASE):
        return True
    
    # Check for JSON format with tool type
    if text.startswith('{'):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                action_type = parsed.get('type', '').upper()
                if action_type in ['TOOL', 'ACTION', 'EXECUTE']:
                    return True
        except json.JSONDecodeError:
            pass
    
    # Check for simple tool invocation patterns
    if re.search(r'(?:use|call|run|execute)\s+\w+', text, re.IGNORECASE):
        # But exclude common false positives
        if not re.search(r'(?:use|call|run|execute)\s+(?:this|that|it|the|a|an)\s', text, re.IGNORECASE):
            return True
    
    return False


def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a tool call from LLM output into structured format.
    
    Expected schema:
    {
        "type": "tool",
        "name": "<tool_name>",
        "args": {},
        "thought": "<optional reasoning>"
    }
    
    Supports formats:
    1. "TOOL: tool_name(param1='value1', param2='value2')"
    2. JSON: {"type": "tool", "name": "...", "args": {...}}
    3. Simple: "use tool_name" or "call tool_name"
    
    Args:
        text: The LLM output text
        
    Returns:
        Parsed tool call dict, or None if not a valid tool call
    """
    if not text or not text.strip():
        return None
    
    text = text.strip()
    
    # Try TOOL: pattern first (most explicit)
    tool_match = re.search(
        r'TOOL:\s*(\w+)\s*\(([^)]*(?:\([^)]*\))*[^)]*)\)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    if tool_match:
        tool_name = tool_match.group(1)
        params_str = tool_match.group(2)
        
        # Extract thought from surrounding text if present
        thought_match = re.search(r'(?:because|since|to|for)\s+[^.]+', text, re.IGNORECASE)
        thought = thought_match.group(0).strip() if thought_match else "Tool call from explicit TOOL: pattern"
        
        # Parse parameters
        args = {}
        if params_str.strip():
            # Handle various parameter formats
            # Format: param1='value1', param2="value2", param3=value3
            param_matches = re.findall(
                r"(\w+)\s*=\s*(?:['\"]([^'\"]*)['\"]|(\d+\.?\d*)|(\w+))",
                params_str
            )
            for match in param_matches:
                param_name = match[0]
                # Value could be in group 1 (string), 2 (number), or 3 (boolean/other)
                param_value = match[1] or match[2] or match[3]
                # Convert types
                if param_value.lower() == 'true':
                    param_value = True
                elif param_value.lower() == 'false':
                    param_value = False
                elif isinstance(param_value, str) and param_value.isdigit():
                    param_value = int(param_value)
                elif isinstance(param_value, str):
                    try:
                        param_value = float(param_value)
                        if param_value.is_integer():
                            param_value = int(param_value)
                    except ValueError:
                        pass
                args[param_name] = param_value
        
        return {
            "type": "tool",
            "name": tool_name,
            "args": args,
            "thought": thought
        }
    
    # Try JSON format
    if text.startswith('{'):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                action_type = parsed.get('type', '').upper()
                if action_type in ['TOOL', 'ACTION', 'EXECUTE']:
                    # Normalize to our schema
                    return {
                        "type": "tool",
                        "name": parsed.get('name') or parsed.get('tool') or parsed.get('tool_name'),
                        "args": parsed.get('args') or parsed.get('params') or parsed.get('parameters') or {},
                        "thought": parsed.get('thought') or parsed.get('reasoning', '')
                    }
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse JSON tool call: {e}")
    
    # Try simple patterns: "use tool_name" or "call tool_name"
    simple_match = re.search(
        r'(?:use|call|run|execute)\s+(\w+)(?:\s+with\s+(.+?))?(?:\.|$)',
        text,
        re.IGNORECASE
    )
    if simple_match:
        tool_name = simple_match.group(1)
        # Skip if it's a generic reference
        if tool_name.lower() in ['this', 'that', 'it', 'the', 'a', 'an', 'some', 'any']:
            return None
        
        args = {}
        # Try to extract any mentioned parameters from the rest of the text
        if simple_match.group(2):
            context = simple_match.group(2)
            # Look for quoted values
            value_matches = re.findall(r'["\']([^"\']+)["\']', context)
            if value_matches:
                args['value'] = value_matches[0]
        
        return {
            "type": "tool",
            "name": tool_name,
            "args": args,
            "thought": "Tool call from natural language"
        }
    
    return None


def parse_multiple_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Parse multiple tool calls from a single LLM response.
    
    WARNING: Multiple tool calls in one response can lead to unpredictable behavior.
    This function is provided for debugging and analysis only.
    The orchestrator should reject responses with multiple tool calls.
    
    Args:
        text: The LLM output text
        
    Returns:
        List of parsed tool call dicts (empty list if none found)
    """
    calls = []
    
    # Find all TOOL: patterns
    tool_matches = re.finditer(
        r'TOOL:\s*(\w+)\s*\(([^)]*(?:\([^)]*\))*[^)]*)\)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    
    for match in tool_matches:
        parsed = parse_tool_call(f"TOOL: {match.group(1)}({match.group(2)})")
        if parsed:
            calls.append(parsed)
    
    return calls


def validate_tool_call_schema(tool_call: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate that a tool call matches the expected schema.
    
    Required schema:
    {
        "type": "tool",
        "name": "<non-empty string>",
        "args": <dict>
    }
    
    Args:
        tool_call: The parsed tool call dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(tool_call, dict):
        return False, "Tool call must be a dictionary"
    
    if tool_call.get('type') != 'tool':
        return False, f"Invalid type: expected 'tool', got '{tool_call.get('type')}'"
    
    name = tool_call.get('name')
    if not name or not isinstance(name, str):
        return False, "Missing or invalid 'name' field (must be non-empty string)"
    
    args = tool_call.get('args')
    if args is not None and not isinstance(args, dict):
        return False, f"'args' must be a dictionary, got {type(args).__name__}"
    
    return True, ""


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_cases = [
        "TOOL: open_app(app_name='notepad')",
        "TOOL: navigate_to_url(url='https://example.com')",
        '{"type": "tool", "name": "search_web", "args": {"query": "weather"}}',
        "I'll use open_app to launch Chrome",
        "Call the search tool with query 'news'",
        "The weather is nice today",  # Not a tool call
    ]
    
    print("Testing Tool Call Parser\n" + "=" * 50)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test[:60]}...")
        print(f"  is_tool_call: {is_tool_call(test)}")
        parsed = parse_tool_call(test)
        if parsed:
            print(f"  parsed: {json.dumps(parsed, indent=4)}")
            valid, msg = validate_tool_call_schema(parsed)
            print(f"  valid: {valid} ({msg})")
        else:
            print(f"  parsed: None")
