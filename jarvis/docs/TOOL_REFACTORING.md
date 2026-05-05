# Tool System Refactoring - Deterministic Tool Selection

## Overview

This refactoring eliminates incorrect tool selection and makes all tool calls deterministic through:

1. **Strict naming convention**: `<domain>.<verb>_<object>`
2. **Typed JSON schemas** with enum constraints
3. **TOOL_HINTS filtering**: Only 3-5 relevant tools sent to LLM
4. **Structured JSON output**: No more "TOOL: ..." pattern
5. **Validation layer**: Fail fast on invalid calls

## New Execution Flow

```
Input → Tool Hint Filter → LLM (with 3-5 tools) → Structured JSON Parse → 
Validation → Execution
```

**Replaces old flow:**
```
Input → All Tools → LLM → TOOL: pattern parse → Execute
```

## Files Created/Modified

### New Files

| File | Purpose |
|------|---------|
| `jarvis/tools/registry_refactored.py` | New registry with strict naming, TOOL_HINTS, filtering |
| `jarvis/tools/refactored_examples.py` | Example tools showing new pattern |
| `jarvis/tools/validator.py` | Tool call validator (schema + type checking) |
| `jarvis/core/tool_call_parser.py` | Strict JSON parser (replaces TOOL: regex) |
| `jarvis/core/orchestrator_patch.py` | Integration guide for orchestrator |

### Key Components

#### 1. TOOL_HINTS Dictionary (`registry_refactored.py`)

Maps tool names to keywords for deterministic filtering:

```python
TOOL_HINTS = {
    "system.lock_pc": ["lock", "secure", "screen", "workstation"],
    "file.read": ["read", "open", "view", "contents", "text", "file"],
    "app.open": ["open", "launch", "start", "run", "application", "app"],
    "web.search": ["search", "google", "find", "query", "web", "internet"],
    # ... 26 tool hints defined
}
```

**Usage:**
```python
from jarvis.tools.registry_refactored import filter_tools

# Get only relevant tools for user input
filtered = filter_tools("open notepad", max_tools=5)
# Returns: {'file.read': ..., 'file.open': ..., 'app.open': ...}
```

#### 2. Strict Naming Convention

All tools must follow: `<domain>.<verb>_<object>`

| Old Name | New Name |
|----------|----------|
| `lock_pc` | `system.lock_pc` |
| `open_app` | `app.open` |
| `read_file` | `file.read` |
| `search_web` | `web.search` |
| `close_browser` | `web.close_browser` |

**Migration:** Legacy names are auto-converted during registration via `_migrate_tool_name()`.

#### 3. Typed JSON Schemas

Each tool now has strict schema with enums for constrained inputs:

```python
class AppOpenTool(BaseTool):
    name = "app.open"
    description = "Open an application by name."
    
    parameters = {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application",
                "enum": ["chrome", "firefox", "notepad", "vscode", ...]  # Constrains LLM
            }
        },
        "required": ["app_name"]
    }
```

#### 4. Structured JSON Output Format

**Old format (rejected):**
```
TOOL: open_app(app='notepad')
```

**New format (required):**
```json
{
    "action": "tool_call",
    "tool": "app.open",
    "args": {"app_name": "notepad"},
    "thought": "User wants to edit text"
}
```

#### 5. Validation Pipeline

```
1. Check tool exists in registry
2. Validate required parameters present
3. Validate parameter types match schema
4. Validate enum constraints
5. Run tool-specific validation
6. Execute
```

**Usage:**
```python
from jarvis.tools.validator import validate_tool_call

is_valid, error = validate_tool_call("app.open", {"app_name": "chrome"})
if not is_valid:
    raise Exception(f"Invalid tool call: {error}")
```

## Integration Guide

### Step 1: Update Orchestrator

Replace `_build_tools_json()` and related methods with:

```python
from jarvis.core.orchestrator_patch import OrchestratorToolPatch

class Orchestrator(OrchestratorToolPatch):
    # Inherits new methods:
    # - _get_filtered_tools_for_llm()
    # - _build_strict_json_prompt()
    # - _parse_and_validate_tool_call()
    # - _execute_validated_tool_call()
    # - process_command_with_new_flow()
    pass
```

### Step 2: Update System Prompt

Use `_build_strict_json_prompt()` which includes:
- Filtered tools (3-5 max)
- Strict JSON format requirement
- Examples in correct format

### Step 3: Update LLM Temperature

Set temperature to 0 for deterministic output:
```python
llm_response = self.brain.chat(messages, temperature=0)
```

### Step 4: Add Retry Logic

For malformed JSON responses:
```python
parsed, error = parse_tool_call_json(llm_response, max_retries=2)
if not parsed:
    # Ask LLM to retry with correct format
    messages.append({
        "role": "user",
        "content": f"Invalid JSON: {error}. Respond with: {{\"action\": \"tool_call\", \"tool\": \"...\", \"args\": {{}}}}"
    })
```

## Testing

Run tests:
```bash
cd /workspace
python -c "
from jarvis.tools.registry_refactored import filter_tools
from jarvis.core.tool_call_parser import parse_tool_call_json
from jarvis.tools.validator import validate_tool_call

# Test filtering
print(filter_tools('open notepad'))

# Test parsing
valid_json = '{\"action\": \"tool_call\", \"tool\": \"app.open\", \"args\": {\"app_name\": \"chrome\"}}'
parsed, error = parse_tool_call_json(valid_json)
print(parsed)

# Test validation
is_valid, error = validate_tool_call('app.open', {'app_name': 'chrome'})
print(is_valid)
"
```

## Migration Checklist

- [ ] Update existing tool definitions to use new naming
- [ ] Add missing entries to TOOL_HINTS
- [ ] Update system prompts to require JSON format
- [ ] Set LLM temperature to 0
- [ ] Add validation before execution
- [ ] Remove old TOOL: pattern parsers
- [ ] Test all critical paths

## Benefits

1. **Deterministic selection**: Same input → same tools filtered
2. **Fewer hallucinations**: LLM sees only 3-5 relevant tools
3. **Type safety**: Enums prevent invalid app names, etc.
4. **Fail fast**: Invalid calls rejected before execution
5. **Maintainable**: Clear naming convention, consistent schemas

## Backward Compatibility

Legacy tool names are auto-migrated during registration. The migration map in `_migrate_tool_name()` handles common patterns. Warnings are logged for unmigrated names.
