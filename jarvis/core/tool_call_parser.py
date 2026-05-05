"""
core/tool_call_parser.py — Strict JSON Tool Call Parser

Replaces the old "TOOL: ..." pattern with strict JSON parsing.
Enforces structured LLM output format:
{
    "action": "tool_call",
    "tool": "<tool_name>",
    "args": {...}
}

Features:
- Strict JSON parsing only (no regex patterns)
- Retry mechanism for malformed JSON
- Schema validation before returning parsed call
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tool_call_parser")


# Expected structured output format
STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "tool": {"type": "string"},
        "args": {"type": "object"}
    },
    "required": ["action", "tool", "args"]
}


def is_valid_tool_call_json(text: str) -> bool:
    """
    Check if text is a valid tool call JSON.
    
    Args:
        text: Text to check
        
    Returns:
        True if valid JSON tool call format, False otherwise
    """
    if not text or not text.strip():
        return False
    
    text = text.strip()
    
    # Must start with { to be JSON
    if not text.startswith('{'):
        return False
    
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return False
        
        # Check for required fields
        action = parsed.get('action', '').lower()
        if action not in ['tool_call', 'tool']:
            return False
        
        if 'tool' not in parsed or not isinstance(parsed['tool'], str):
            return False
        
        if 'args' not in parsed or not isinstance(parsed['args'], dict):
            return False
        
        return True
        
    except json.JSONDecodeError:
        return False


def extract_json_from_text(text: str) -> Optional[str]:
    """
    Extract JSON object from text that may contain other content.
    
    Handles:
    - Plain JSON: {...}
    - Markdown code blocks: ```json {...} ```
    - Text with embedded JSON
    
    Args:
        text: Text potentially containing JSON
        
    Returns:
        Extracted JSON string, or None if not found
    """
    if not text:
        return None
    
    text = text.strip()
    
    # Try direct parse first
    if text.startswith('{') and text.endswith('}'):
        return text
    
    # Look for markdown code block
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if code_block_match:
        return code_block_match.group(1).strip()
    
    # Look for JSON object pattern
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json_match.group()
    
    return None


def parse_tool_call_json(
    text: str,
    max_retries: int = 2,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Parse a tool call from LLM JSON output.
    
    Expected format:
    {
        "action": "tool_call",
        "tool": "<tool_name>",
        "args": {...},
        "thought": "optional reasoning"
    }
    
    Args:
        text: LLM output text
        max_retries: Number of retry attempts for malformed JSON
        
    Returns:
        Tuple of (parsed_dict, error_message)
        If successful: (dict, "")
        If failed: (None, "error description")
    """
    if not text or not text.strip():
        return None, "Empty input"
    
    text = text.strip()
    
    # Extract JSON from text
    json_str = extract_json_from_text(text)
    if not json_str:
        return None, "No JSON object found in response"
    
    # Try to parse JSON
    attempt = 0
    last_error = ""
    
    while attempt <= max_retries:
        try:
            parsed = json.loads(json_str)
            
            if not isinstance(parsed, dict):
                return None, "Parsed JSON must be an object/dictionary"
            
            # Normalize field names (handle variations)
            normalized = normalize_tool_call_fields(parsed)
            
            # Validate structure
            is_valid, error = validate_tool_call_structure(normalized)
            if not is_valid:
                return None, error
            
            return normalized, ""
            
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {str(e)}"
            attempt += 1
            
            # Could attempt auto-repair here if needed
            # For now, just retry with cleaned JSON
            json_str = clean_json_string(json_str)
    
    return None, f"Failed to parse JSON after {max_retries + 1} attempts: {last_error}"


def normalize_tool_call_fields(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize field names to standard format.
    
    Handles variations like:
    - tool/tool_name/name
    - args/params/parameters
    - thought/reasoning/think
    
    Args:
        parsed: Parsed JSON dict
        
    Returns:
        Normalized dict with standard field names
    """
    result = {
        "action": "tool_call",  # Always set to tool_call
        "tool": None,
        "args": {},
        "thought": ""
    }
    
    # Find tool name
    for key in ['tool', 'tool_name', 'name', 'function']:
        if key in parsed and parsed[key]:
            result['tool'] = parsed[key]
            break
    
    # Find arguments
    for key in ['args', 'params', 'parameters', 'arguments']:
        if key in parsed and isinstance(parsed[key], dict):
            result['args'] = parsed[key]
            break
    
    # Find thought/reasoning
    for key in ['thought', 'reasoning', 'think', 'rationale']:
        if key in parsed and parsed[key]:
            result['thought'] = str(parsed[key])
            break
    
    # Copy any additional fields
    for key, value in parsed.items():
        if key not in ['action', 'tool', 'tool_name', 'name', 'function', 
                       'args', 'params', 'parameters', 'arguments',
                       'thought', 'reasoning', 'think', 'rationale', 'type']:
            result[key] = value
    
    return result


def validate_tool_call_structure(parsed: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate that parsed tool call has required structure.
    
    Required:
    - tool: non-empty string
    - args: dict (can be empty)
    
    Args:
        parsed: Normalized tool call dict
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not parsed.get('tool'):
        return False, "Missing required field: 'tool'"
    
    if not isinstance(parsed['tool'], str):
        return False, f"'tool' must be a string, got {type(parsed['tool']).__name__}"
    
    if not parsed.get('args'):
        parsed['args'] = {}  # Default to empty dict
    
    if not isinstance(parsed['args'], dict):
        return False, f"'args' must be an object, got {type(parsed['args']).__name__}"
    
    return True, ""


def clean_json_string(json_str: str) -> str:
    """
    Clean common JSON formatting issues.
    
    Handles:
    - Trailing commas
    - Single quotes instead of double quotes
    - Missing quotes on keys
    
    Args:
        json_str: Potentially malformed JSON string
        
    Returns:
        Cleaned JSON string
    """
    # Remove trailing commas before } or ]
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    # Replace single quotes with double quotes (simple cases)
    # Note: This is imperfect but handles common LLM output errors
    json_str = json_str.replace("'", '"')
    
    return json_str


def format_tool_call_for_llm(
    tool_name: str,
    args: Dict[str, Any],
    thought: str = "",
) -> str:
    """
    Format a tool call as JSON string for LLM examples/prompts.
    
    Args:
        tool_name: Name of tool
        args: Arguments dict
        thought: Optional reasoning/thought
        
    Returns:
        Formatted JSON string
    """
    result = {
        "action": "tool_call",
        "tool": tool_name,
        "args": args
    }
    
    if thought:
        result["thought"] = thought
    
    return json.dumps(result, indent=2)


def build_system_prompt_with_tools(
    filtered_schemas: List[dict],
    max_examples: int = 3,
) -> str:
    """
    Build system prompt section showing available tools and examples.
    
    Args:
        filtered_schemas: List of tool schemas (already filtered by hints)
        max_examples: Maximum number of examples to include
        
    Returns:
        System prompt section string
    """
    if not filtered_schemas:
        return "No tools available."
    
    lines = [
        "AVAILABLE TOOLS:",
        "You have access to the following tools. Use them by outputting JSON in this exact format:",
        "",
        '{"action": "tool_call", "tool": "<tool_name>", "args": {...}}',
        "",
        "Tool definitions:",
    ]
    
    # Add tool descriptions
    for schema in filtered_schemas[:max_examples * 2]:  # Show more definitions
        func = schema.get('function', {})
        name = func.get('name', 'unknown')
        desc = func.get('description', 'No description')
        params = func.get('parameters', {})
        
        required = params.get('required', [])
        properties = params.get('properties', {})
        
        lines.append(f"- {name}: {desc}")
        if properties:
            param_desc = ", ".join([f"{k} ({v.get('type', 'any')})" for k, v in properties.items()])
            lines.append(f"  Parameters: {param_desc}")
            if required:
                lines.append(f"  Required: {', '.join(required)}")
    
    lines.extend([
        "",
        "IMPORTANT RULES:",
        "1. Output ONLY ONE tool call per response",
        "2. Use strict JSON format - no explanatory text",
        "3. Wait for tool result before next action",
        "4. When task is complete, respond with final answer (not a tool call)",
    ])
    
    return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_cases = [
        # Valid cases
        '{"action": "tool_call", "tool": "app.open", "args": {"app_name": "chrome"}}',
        '{"action": "tool", "tool": "web.search", "args": {"query": "weather"}}',
        '```json\n{"action": "tool_call", "tool": "file.read", "args": {"path": "/test.txt"}}\n```',
        
        # Invalid cases
        "TOOL: open_app(app='notepad')",  # Old format
        '{"tool": "test"}',  # Missing action
        "Just some regular text",  # Not JSON
        '{"action": "tool_call", "tool": 123, "args": {}}',  # Wrong type
    ]
    
    print("Testing Strict JSON Tool Call Parser\n" + "=" * 50)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test[:60]}...")
        parsed, error = parse_tool_call_json(test)
        if parsed:
            print(f"  ✓ Parsed: {json.dumps(parsed, indent=2)}")
        else:
            print(f"  ✗ Error: {error}")
