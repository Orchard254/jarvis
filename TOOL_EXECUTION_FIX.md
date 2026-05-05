# Tool Call Execution Pipeline Fix

## Summary

Fixed the agent system so that LLM outputs are **executed as actions**, not returned as text to the user.

## Problem

**Before:** When the LLM output `TOOL: open_control_panel()`, the system would print this text to the user instead of actually opening the control panel.

**After:** The same LLM output is now detected, parsed, and executed - the control panel actually opens.

## Changes Made

### 1. New Parser Module (`jarvis/core/tool_parser.py`)

Created a deterministic parser with three key functions:

- **`is_tool_call(text)`** - Detects if LLM output contains a tool call pattern
- **`parse_tool_call(text)`** - Converts text into structured schema:
  ```python
  {
      "type": "tool",
      "name": "<tool_name>",
      "args": {},
      "thought": "<optional reasoning>"
  }
  ```
- **`validate_tool_call_schema(tool_call)`** - Validates the parsed structure

Supports multiple input formats:
- Explicit: `TOOL: open_app(app_name='notepad')`
- JSON: `{"type": "tool", "name": "open_app", "args": {...}}`
- Natural: `"use open_app to launch Chrome"`

### 2. Orchestrator Updates (`jarvis/core/orchestrator.py`)

#### Added imports:
```python
from jarvis.core.tool_parser import is_tool_call, parse_tool_call, validate_tool_call_schema
```

#### New execution method `_execute_action()`:
A complete pipeline that:
1. Logs raw LLM output
2. Validates schema
3. Checks safety (ToolGuard)
4. Executes the tool from registry
5. Logs execution result with timing
6. Returns structured result dict

#### Updated `_handle_unified_mode()`:
Modified the tool execution flow to use the new parser and executor:
```python
# Convert parsed response to structured tool call
tool_call_dict = {
    "type": "tool",
    "name": parsed.get('tool'),
    "args": parsed.get('params', {}),
    "thought": parsed.get('thought', '')
}

# Log raw LLM output
logger.info(f"[LLM] Raw output: {assistant_message[:200]}...")

# Use structured execution pipeline
exec_result = self._execute_action(tool_call_dict)
```

## Pipeline Flow

```
User Input → Intent Classification → LLM → Detection → Parsing → Execution → Result
                                                      ↓
                                    ┌─────────────────┴──────────────┐
                                    │                                │
                              [is_tool_call=True]              [is_tool_call=False]
                                    │                                │
                                    ↓                                ↓
                            Parse to schema                    Return as chat
                                    │
                                    ↓
                            Validate schema
                                    │
                                    ↓
                            Safety check (ToolGuard)
                                    │
                                    ↓
                            Execute tool from registry
                                    │
                                    ↓
                            Log & return result
```

## Logging

Each stage is logged with `[EXEC]` prefix:
- `[EXEC] Received tool call: {...}`
- `[EXEC] Parsed plan: tool=open_app, args={...}, thought=...`
- `[EXEC] Executing: open_app({...})`
- `[EXEC] Result: success=True, output=Opening..., duration=45ms`

## Example

**User says:** "open the control panel"

**Old behavior:**
```
LLM: TOOL: open_app(app_name='control panel')
System shows: "TOOL: open_app(app_name='control panel')" ❌
```

**New behavior:**
```
LLM: TOOL: open_app(app_name='control panel')
Parser detects tool call
Executor calls open_app.execute(app_name='control panel')
Control panel ACTUALLY OPENS via subprocess
System shows: "Opening control panel" ✓
```

## Files Changed

1. `jarvis/core/tool_parser.py` - NEW (parser module)
2. `jarvis/core/orchestrator.py` - Modified (execution pipeline)
3. `example_tool_execution.py` - NEW (demo script)

## Testing

Run the example:
```bash
python example_tool_execution.py
```

Verify imports work:
```bash
python -c "from jarvis.core.tool_parser import is_tool_call, parse_tool_call; print('OK')"
python -c "from jarvis.core.orchestrator import Orchestrator; print('OK')"
```

## Constraints Followed

- ✅ Did NOT redesign the whole architecture
- ✅ Only fixed the bridge between LLM output and execution
- ✅ Did NOT touch brain.py, tool implementations, memory files, skill files, perception files, or reasoning files
- ✅ Minimal changes focused on detection, parsing, and execution
