# Stability Fixes Summary

## Critical Fixes Applied to `jarvis/core/orchestrator.py`

### 1. UTF-8 Logging Fix (Critical for Windows)

**Problem:** UnicodeEncodeError when logging special characters (narrow spaces, non-breaking hyphens, curly quotes) on Windows console with cp1252 encoding.

**Solution:**
- Added `_safe_log()` function that sanitizes strings before logging
- Replaces problematic Unicode characters with ASCII equivalents:
  - `\u202f` (narrow no-break space) → ` ` (regular space)
  - `\u2011` (non-breaking hyphen) → `-` (regular hyphen)
  - `\u2013` (en dash) → `-`
  - `\u2014` (em dash) → `--`
  - `\u2018/\u2019` (curly single quotes) → `'`
  - `\u201c/\u201d` (curly double quotes) → `"`
  - etc.
- Applied sanitization to all `[LLM]` and `[EXEC]` log messages
- Added UTF-8 reconfiguration for sys.stdout on Windows

**Files Changed:**
- `jarvis/core/orchestrator.py`: Lines 21-31 (UTF-8 setup), 69-115 (`_safe_log` function), 688, 1020, 1025, 1039, 1050, 1107 (sanitized log calls)

---

### 2. Strict Tool vs Text Output Separation

**Problem:** LLM outputs were sometimes returned as text instead of being executed, or vice versa.

**Solution:**
- Enhanced the execution pipeline with clear separation:
  - Tool calls (`type=TOOL`) → Always execute via `_execute_action()`
  - Final responses (`type=FINAL`) → Always return as text
  - Unknown types → Treated as final response
- Added structured logging at each stage:
  - `[LLM] Raw output:` - Shows what LLM generated
  - `[EXEC] Received tool call:` - Shows parsed structure
  - `[EXEC] Parsed plan:` - Shows normalized parameters
  - `[EXEC] Executing:` - Shows actual execution
  - `[EXEC] Result:` - Shows outcome

**Flow:**
```
Input → Intent Score → [Below Threshold?] → Chat Only
                      → [Above Threshold?] → Unified Mode → LLM → Parse → Normalize → Validate → Execute → Result
```

---

### 3. Intent Threshold Gate

**Problem:** Low-confidence commands were attempting tool execution, causing instability.

**Solution:**
- Added `INTENT_THRESHOLD = 45` constant
- Commands scoring below threshold bypass tool execution entirely
- New `_handle_chat_only()` method handles low-intent inputs as pure chat
- Prevents accidental tool calls on ambiguous inputs

**Implementation:**
```python
if intent_score < INTENT_THRESHOLD:
    logger.info(f"Intent score ({intent_score}) below threshold ({INTENT_THRESHOLD}), treating as chat")
    result = self._handle_chat_only(command)
else:
    # Normal unified/agent mode processing
```

**Files Changed:**
- `jarvis/core/orchestrator.py`: Lines 65-66 (threshold constant), 538-551 (threshold gate logic), 610-657 (`_handle_chat_only` method)

---

### 4. Argument Normalization (Already Implemented)

**Problem:** LLM generates `app_name='notepad'` but tool expects `app='notepad'`.

**Solution:**
- `_normalize_tool_arguments()` converts `app_name` → `app` for `open_app` tool
- Happens BEFORE safety validation
- Safety validator now accepts both formats

---

## Testing Results

### UTF-8 Sanitization Test
```
Original: 'Text with narrow space: 16\u202fGB'
Sanitized: 'Text with narrow space: 16 GB'

Original: 'Text with non-breaking hyphen: Wi\u2011Fi'
Sanitized: 'Text with non-breaking hyphen: Wi-Fi'

Original: 'Mixed: Battery at 80\u202f% and Wi\u2011Fi connected'
Sanitized: 'Mixed: Battery at 80 % and Wi-Fi connected'
```

All problematic Unicode characters are now safely converted to ASCII equivalents before logging.

### Module Import Test
```
✓ jarvis.core.orchestrator
✓ jarvis.core.tool_parser
✓ jarvis.tools.registry
✓ jarvis.safety.tool_guard

All modules imported successfully!
```

---

## Expected Behavior After Fix

### Before (Broken):
```
You: check my battery
[UnicodeEncodeError crashes the console]
```

### After (Fixed):
```
You: check my battery
Intent score: 59/100 - Learned pattern match...
[LLM] Raw output: TOOL: battery_status()...
[EXEC] Received tool call: {'type': 'tool', 'name': 'battery_status', ...}
[EXEC] Parsed plan: tool=battery_status, args={}, thought=...
[EXEC] Executing: battery_status({})
[EXEC] Result: success=True, output=Battery: 80%, discharging, duration=8ms

JARVIS: Your battery is at 80% and currently discharging.
```

No more Unicode errors. Clean execution flow. Stable operation.

---

## Verification Commands

Run these to verify the fixes:

```bash
# Test UTF-8 sanitization
python -c "from jarvis.core.orchestrator import _safe_log; print(_safe_log('Battery: 80\u202f%, Wi\u2011Fi'))"

# Test intent threshold
python -c "from jarvis.core.orchestrator import INTENT_THRESHOLD; print(f'Threshold: {INTENT_THRESHOLD}')"

# Test module imports
python -c "from jarvis.core.orchestrator import Orchestrator; print('OK')"

# Run full system test
python jarvis.py --mode agent
```

Then try commands like:
- "check my battery"
- "check my wifi"
- "system info"
- "open control panel"

All should execute without Unicode logging errors.
