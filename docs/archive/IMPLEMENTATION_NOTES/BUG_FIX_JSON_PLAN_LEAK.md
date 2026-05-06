# Bug Fix: JSON Plan Leakage in Unified Mode

## Problem
When executing commands like "clear notepad" in unified loop mode, the LLM was returning structured JSON plans instead of natural language responses or single tool calls:

```json
{
    "goal": "Clear all text in Notepad",
    "corrections": [],
    "confidence": "high",
    "needs_clarification": false,
    "steps": [
        {
            "tool": "clear_text",
            "params": {"target_app": "notepad"},
            "reason": "Remove any existing content from the Notepad window"
        }
    ]
}
```

This JSON was being displayed directly to the user instead of being executed or converted to natural language.

## Root Cause

### 1. Mode Confusion
The LLM was confused between two different execution modes:
- **Unified Loop Mode**: Should output ONE tool call at a time (`TOOL: tool_name(params)`) or final response
- **Predictive Planning Mode**: Outputs complete plans with multiple steps in JSON format

### 2. Missing Validation
The `_parse_natural_response()` method in `orchestrator.py` was treating ANY JSON as valid, including plan structures that should only appear in predictive planning mode.

### 3. No Fallback for Plan Leakage
When a plan JSON leaked into unified mode, the system had no mechanism to:
- Detect it was invalid for the current mode
- Force the LLM to regenerate a proper response
- Convert it to executable actions

## Solution

### Fix Applied: Enhanced JSON Detection in `_parse_natural_response()`

**File**: `/workspace/jarvis/core/orchestrator.py`  
**Function**: `_parse_natural_response()` (lines 1096-1118)

**Changes**:
```python
# Default: treat as final response if it's not empty
# CRITICAL: If response contains a "steps" array, it's a plan that leaked - don't show to user
if text:
    # Check if this is a leaked plan JSON (should not happen in unified mode)
    if text.strip().startswith('{'):
        try:
            import json as json_module
            parsed_json = json_module.loads(text.strip())
            if isinstance(parsed_json, dict) and parsed_json.get('steps'):
                # This is a plan JSON that leaked - log warning and return None to trigger retry
                logger.warning(f"Plan JSON leaked to unified mode: {text[:100]}...")
                # Return None to force LLM to regenerate proper response
                return None
        except:
            pass  # Not valid JSON, continue normally
    
    return {
        'type': 'FINAL',
        'response': text,
        'thought': 'Natural language response'
    }

return None
```

### How It Works

1. **Detection**: When parsing a response, check if it's JSON containing a "steps" array
2. **Rejection**: Return `None` instead of treating it as valid
3. **Retry Logic**: The orchestrator sees `None` and sends a clarification message to the LLM
4. **Regeneration**: LLM produces correct single-tool or natural language response

### Flow Diagram

```
User: "clear notepad"
  ↓
Unified Loop Mode
  ↓
LLM Response: {"goal": "...", "steps": [...]}  ← WRONG!
  ↓
_parse_natural_response()
  ↓
Detects "steps" array → Returns None
  ↓
Orchestrator: "I didn't understand your response..."
  ↓
LLM Retry
  ↓
LLM Response: "TOOL: clear_text(target_app='notepad')"  ← CORRECT!
  ↓
Execute tool → Success
```

## Testing Checklist

- [x] Import test: `from jarvis.core.orchestrator import Orchestrator` ✓
- [ ] Test "clear notepad" command - should execute tool, not show JSON
- [ ] Test other simple commands in unified mode
- [ ] Verify multi-step commands still use predictive planner correctly
- [ ] Confirm no regression in chat-only mode

## Related Files

1. **`jarvis/core/orchestrator.py`** - Main fix location
   - `_parse_natural_response()`: Added plan leakage detection
   - `_handle_unified_mode()`: Uses parser results

2. **`jarvis/core/predictive_planner.py`** - Generates plans (should be separate from unified mode)

3. **`jarvis/core/tool_parser.py`** - Parses individual tool calls (working correctly)

## Prevention Strategies

### For Future Development

1. **Clear Mode Separation**: Ensure LLM prompts clearly distinguish between:
   - Unified mode: One tool at a time
   - Planning mode: Complete multi-step plans
   
2. **Schema Validation**: Add stricter validation for expected response formats per mode

3. **Logging**: Enhanced warnings when unexpected formats detected (already implemented)

4. **Testing**: Add unit tests for each mode's expected response formats

## Status

✅ **FIXED** - Plan JSON leakage now detected and handled gracefully
⏳ **TESTING NEEDED** - Run actual commands to verify fix works in production

## Additional Notes

This bug was related to but distinct from the earlier JSON leakage issues:
- **Previous bug**: ReAct agent leaking clarification JSON → Fixed with response sanitization
- **This bug**: Unified mode receiving plan JSON → Fixed with detection + retry logic

Both fixes ensure users never see raw JSON structures in their interactions with JARVIS.
