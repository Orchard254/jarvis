# Argument Normalization Fix - Summary

## Problem

The LLM was generating valid tool calls like:
```
TOOL: open_app(app_name='notepad')
```

But the safety layer was blocking them with **"No app specified"** because:
- LLM outputs `app_name` parameter
- Safety validator only checked for `app` parameter
- Mismatch caused valid calls to be rejected
- System fell back to `run_command`, causing instability

## Solution

Implemented a **three-layer fix**:

### 1. Safety Layer (`jarvis/safety/tool_guard.py`)

Updated validators to accept **both** parameter names:

```python
def _validate_open_app(self, params: Dict[str, Any]) -> Tuple[bool, str]:
    # Accept both 'app' and 'app_name' parameter names
    app = params.get('app', '') or params.get('app_name', '')
    if not app:
        return False, "No app specified"
    # ... rest of validation
```

**Files changed:**
- `_validate_open_app()` - now checks both `app` and `app_name`
- `_validate_close_app()` - now checks both `app` and `app_name`
- Added missing `logging` import

### 2. Orchestrator Normalization (`jarvis/core/orchestrator.py`)

Added argument normalization layer that runs **before** safety validation:

```python
def _normalize_tool_arguments(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Convert LLM parameter names to tool-expected names."""
    normalized = args.copy()
    
    arg_mappings = {
        'open_app': {'app_name': 'app'},
        'close_app': {'app_name': 'app'},
    }
    
    if tool_name in arg_mappings:
        for external_name, internal_name in arg_mappings[tool_name].items():
            if external_name in normalized and internal_name not in normalized:
                normalized[internal_name] = normalized.pop(external_name)
    
    return normalized
```

**Updated execution pipeline:**
```python
# STEP 1: Normalize arguments before validation
normalized_args = self._normalize_tool_arguments(tool_name, args)

# STEP 2: Safety validation with normalized args
is_valid, error_msg = self.tool_guard.validate_tool_call(tool_name, normalized_args)

# STEP 3: Execute with normalized args
result = tool.execute(**normalized_args)
```

### 3. Logging Enhancements

Added comprehensive logging at each stage:
- `[EXEC] Parsed plan: tool=open_app, args={'app_name': 'notepad'}, thought=...`
- `[EXEC] Normalized args: {'app': 'notepad'}`
- `[EXEC] Executing: open_app({'app': 'notepad'})`
- `[EXEC] Result: success=True, output=..., duration=17ms`

## Pipeline Flow

```
Input → LLM → Detect Tool Call → Parse → Normalize Args → Validate → Execute → Result
                                                  ↓
                                          app_name → app
```

## Test Results

All tests pass:
```
✓ LLM standard format (app_name='notepad') → validates successfully
✓ Tool expected format (app='chrome') → validates successfully  
✓ Close app with app_name → validates successfully
✓ Close app with app → validates successfully
✓ Empty arguments → correctly blocked
```

## Impact

**Before fix:**
- LLM outputs `TOOL: open_app(app_name='notepad')`
- Safety blocks: "No app specified" ❌
- Falls back to `run_command('notepad')` 
- Instability and unpredictable behavior

**After fix:**
- LLM outputs `TOOL: open_app(app_name='notepad')`
- Normalizes to `{'app': 'notepad'}`
- Safety validates successfully ✓
- Executes `open_app` directly
- Stable, predictable execution

## Files Modified

1. `jarvis/safety/tool_guard.py`
   - Added `logging` import
   - Updated `_validate_open_app()` to check both param names
   - Updated `_validate_close_app()` to check both param names

2. `jarvis/core/orchestrator.py`
   - Added `_normalize_tool_arguments()` method
   - Updated `_execute_action()` to normalize before validation
   - Updated all logging to use normalized args
   - Added `retry_allowed: False` on safety failures

## Verification

Run the test script:
```bash
python test_arg_normalization.py
```

Expected output:
```
✓ ALL TESTS PASSED

The fix ensures:
  1. LLM can use 'app_name' parameter (natural naming)
  2. Safety layer accepts both 'app' and 'app_name'
  3. Orchestrator normalizes app_name → app before execution
  4. No more fallback to run_command for valid tool calls
```
