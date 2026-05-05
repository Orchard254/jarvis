# Parameter Name Fixes Summary

## Issue Identified
The LLM (gpt-oss:120b-cloud) was generating tool calls with incorrect parameter names that didn't match the actual tool implementations, causing tool execution failures.

## Root Causes Found

### 1. **Schema vs Implementation Mismatch**
   - Tool schemas defined `app_name` but tools expected `app`
   - Tool schemas defined `window_title` but tools expected `title`
   - Schema definitions were not aligned with actual tool parameter names

### 2. **Shallow Copy Bug in Schema Generation**
   - The `create_schema()` function used `.copy()` instead of `copy.deepcopy()`
   - This caused all schemas to share the same nested dictionary references
   - Result: All 48 schemas had identical content (last defined schema)

## Fixes Applied

### File: `/workspace/jarvis/config/schemas/tool_schemas.py`

#### Fix 1: Deep Copy for Schema Creation
```python
# BEFORE (line 41):
schema = TOOL_SCHEMA_TEMPLATE.copy()

# AFTER:
import copy
schema = copy.deepcopy(TOOL_SCHEMA_TEMPLATE)
```
**Impact**: All 48 tool schemas now have correct, unique definitions

#### Fix 2: open_app/close_app Parameters
```python
# BEFORE (lines 154, 159, 165, 174):
"app_name": {...}
required=["app_name"]

# AFTER:
"app": {...}
required=["app"]
```
**Impact**: LLM now generates correct `open_app(app='notepad')` instead of failing `open_app(app_name='notepad')`

#### Fix 3: focus_window Parameter
```python
# BEFORE (lines 201, 206):
"window_title": {...}
required=["window_title"]

# AFTER:
"title": {...}
required=["title"]
```
**Impact**: LLM now generates correct `focus_window(title='Notepad')` instead of failing

### File: `/workspace/jarvis/tools/executor.py`

#### Fix: Backward Compatibility for Verification Functions
```python
# BEFORE (lines 144, 158):
app_name = arguments.get("app_name", "").lower()

# AFTER:
# Support both 'app' (preferred) and 'app_name' (legacy) parameter names
app_name = arguments.get("app") or arguments.get("app_name", "")
```
**Impact**: Verification functions work with both old and new parameter names

## Other Potential Issues Investigated

### Tools Already Correct (No Changes Needed):
- `open_url` - uses `url` ✓
- `type_text` - uses `text` ✓
- `press_key` - uses `key` ✓
- `set_volume` - uses `level` ✓
- All file operations - use `path`, `content` ✓
- All web automation - use `selector`, `value`, `url` ✓

### Prompts Already Updated:
All prompt files already had correct warnings about using `app` instead of `app_name`:
- `jarvis/config/prompts/planning_prompt.py` ✓
- `jarvis/config/prompts/critic_prompt.py` ✓
- `jarvis/config/prompts/jarvis_prompt.py` ✓

## Testing Verification

Run this command to verify schemas are correct:
```bash
python -c "from jarvis.config.schemas.tool_schemas import get_schema_by_name; import json; print(json.dumps(get_schema_by_name('open_app'), indent=2))"
```

Expected output should show `"app"` as required parameter, not `"app_name"`.

## Prevention Guidelines

1. **Always check tool implementation first** - The source of truth is the `parameters` dict and `required_parameters` list in each tool class
2. **Use deepcopy for nested structures** - Never use `.copy()` on dictionaries containing nested dicts/lists
3. **Test schema generation** - Verify schemas match implementations after any changes
4. **Support backward compatibility** - When renaming parameters, support both old and new names during transition

## Files Modified
1. `/workspace/jarvis/config/schemas/tool_schemas.py` - Fixed schema definitions and deep copy bug
2. `/workspace/jarvis/tools/executor.py` - Added backward compatibility for verification functions
