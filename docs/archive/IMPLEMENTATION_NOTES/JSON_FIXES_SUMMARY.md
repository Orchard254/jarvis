# JSON Handling Bug Fixes - Summary

## Root Cause Analysis

The `open_app` tool failures ("app_name must be a non-empty string") were caused by **inconsistent parameter field naming** in LLM-generated plans combined with **fragile JSON parsing**.

### Problems Identified:

1. **LLM Parameter Inconsistency**: The LLM sometimes outputs parameters using different field names:
   - `params`, `parameters`, `arguments`, `args`
   - Direct fields like `app_name`, `application`, `name` at top level
   - Parameters embedded in description text

2. **Fragile JSON Parsing**: Original code used simple string splitting for markdown code blocks:
   ```python
   if "```json" in response:
       response = response.split("```json")[1].split("```\")[0]
   ```
   This fails with malformed JSON, trailing commas, or unusual formatting.

3. **No Validation**: Plans weren't validated before execution, leading to cryptic errors downstream.

## Solutions Implemented

### 1. New Module: `jarvis/core/json_utils.py`

Centralized utilities for robust JSON handling:

#### Key Functions:

- **`parse_json_safely(text, default)`**: Multi-strategy JSON extraction
  - Extracts from markdown code blocks (```json and ```)
  - Bracket matching for embedded JSON
  - Falls back to parsing entire text
  - Applies automatic fixes for common issues

- **`_fix_common_json_issues(json_str)`**: Auto-repairs malformed JSON
  - Removes trailing commas: `{"a": 1,}` → `{"a": 1}`
  - Quotes unquoted keys: `{key: "val"}` → `{"key": "val"}`
  - Handles non-ASCII characters and control characters

- **`normalize_plan_parameters(step_dict, tool_name, tool_schema)`**: Parameter normalization
  - Checks multiple container fields: `params`, `parameters`, `arguments`, `args`
  - Extracts direct top-level parameters
  - Tool-specific extraction rules:
    - `open_app`: looks for `app_name`, `application`, `app`, `name`, `program`
    - `navigate_to_url`: looks for `url`, `website`, `link`, `address`
    - `search_web`: looks for `query`, `search_term`, `text`, `keywords`
    - File operations: looks for `path`, `file_path`, `filepath`, `file`
  - Extracts from description as last resort (e.g., "Open notepad" → app_name="notepad")

- **`validate_plan_structure(plan)`**: Validates minimum plan requirements
  - Checks plan is a dict with 'steps' array
  - Validates each step has tool identifier
  - Returns `(is_valid, error_message)` tuple

- **`safe_get_nested(data, *keys, default)`**: Safe nested dictionary access

### 2. Updated: `jarvis/core/predictive_planner.py`

**Before:**
```python
if "```json" in response:
    response = response.split("```json")[1].split("```\")[0]
elif "```" in response:
    response = response.split("```\")[1].split("```\")[0]
plan = json.loads(response.strip())

if not isinstance(plan, dict):
    logger.error(f"Invalid plan structure (not a dict): {type(plan)}")
    return None
```

**After:**
```python
from jarvis.core.json_utils import (
    parse_json_safely,
    validate_plan_structure,
    normalize_plan_parameters
)

# Use robust JSON parsing with multiple fallback strategies
plan = parse_json_safely(response, default=None)

if plan is None:
    logger.error(f"Failed to parse JSON from LLM response")
    return None

# Validate plan structure
is_valid, error_msg = validate_plan_structure(plan)
if not is_valid:
    logger.error(f"Invalid plan structure: {error_msg}")
    return None
```

### 3. Updated: `jarvis/core/orchestrator.py`

**Before:**
```python
for step_dict in plan['steps']:
    tool_name = step_dict.get('tool') or step_dict.get('tool_or_skill')
    arguments = step_dict.get('arguments', {}) or step_dict.get('params', {})
    
    # Special handling for open_app: if params empty but app name mentioned, extract it
    if tool_name == 'open_app' and (not arguments or 'app_name' not in arguments):
        if 'app_name' in step_dict:
            arguments = {'app_name': step_dict['app_name']}
        elif 'application' in step_dict:
            arguments = {'app_name': step_dict['application']}
        elif 'name' in step_dict:
            arguments = {'app_name': step_dict['name']}
```

**After:**
```python
for step_dict in plan['steps']:
    tool_name = step_dict.get('tool') or step_dict.get('tool_or_skill')
    
    # Use robust parameter normalization that handles all edge cases
    from jarvis.core.json_utils import normalize_plan_parameters
    arguments = normalize_plan_parameters(step_dict, tool_name)
```

## Benefits

### Immediate Fixes:
✅ `open_app` now works regardless of how LLM specifies the app name  
✅ JSON parsing handles markdown blocks, trailing commas, unquoted keys  
✅ Clear error messages when plans are invalid  

### Future-Proofing:
✅ **Extensible**: Easy to add new tool-specific normalization rules  
✅ **Defensive**: Multiple fallback strategies prevent single points of failure  
✅ **Validated**: Plans checked before execution, failing fast with clear errors  
✅ **Maintainable**: Centralized logic instead of scattered special cases  

### Test Results:
```
✅ Parse JSON from markdown blocks
✅ Normalize app_name from 'application' field
✅ Normalize app_name from 'name' field  
✅ Validate plan structure
✅ Extract app_name from description text
```

## Files Changed

1. **`/workspace/jarvis/core/json_utils.py`** — NEW (407 lines)
   - Core JSON utilities module

2. **`/workspace/jarvis/core/predictive_planner.py`** — MODIFIED
   - Imports and uses `parse_json_safely`, `validate_plan_structure`
   - Replaced fragile string splitting with robust parsing

3. **`/workspace/jarvis/core/orchestrator.py`** — MODIFIED
   - Uses `normalize_plan_parameters` for all tool calls
   - Removed ad-hoc parameter extraction logic

## Usage Examples

```python
from jarvis.core.json_utils import (
    parse_json_safely,
    normalize_plan_parameters,
    validate_plan_structure
)

# Example 1: Parse messy LLM output
llm_output = '''Here's my plan:
```json
{
    "goal": "Open calculator",
    "steps": [
        {"tool": "open_app", "application": "calculator",}
    ]
}
```'''
plan = parse_json_safely(llm_output)
# Returns: {"goal": "...", "steps": [{"tool": "open_app", "application": "calculator"}]}

# Example 2: Normalize parameters
step = {"tool": "open_app", "name": "chrome", "description": "Open Chrome"}
params = normalize_plan_parameters(step, "open_app")
# Returns: {"app_name": "chrome"}

# Example 3: Validate plan
is_valid, error = validate_plan_structure(plan)
# Returns: (True, "") or (False, "error message")
```

## Prevention Guidelines

For future development, always:

1. **Use `parse_json_safely()`** for any LLM JSON output
2. **Use `normalize_plan_parameters()`** for extracting tool parameters
3. **Use `validate_plan_structure()`** before executing plans
4. **Add tool-specific rules** in `_apply_tool_specific_normalization()` when new tools show parameter issues
5. **Log warnings** for malformed input, don't crash
