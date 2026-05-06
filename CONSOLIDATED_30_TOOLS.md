# 30-Tool Consolidated Schema Implementation

## Overview

This implementation consolidates the previous **76 tools** into exactly **30 well-parameterized entry points**, following the principle: **"Parameterization > Proliferation"**.

## Key Benefits

1. **Zero Duplication** — Every tool owns a unique capability boundary
2. **Planner-Friendly** — 120B model can reliably rank 30 choices, not 76
3. **Complexity in Arguments** — Not in tool count
4. **Vision Isolated** — Gemma only activates when strictly necessary

---

## Tool Categories (30 Total)

### 1. Application & Window Control (4 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `app_control` | open, close, list | action, app_name |
| `window_control` | focus, minimize, maximize, close, list | action, window_id |
| `browser_control` | open, close, new_tab, close_tab, list_tabs | action |
| `tab_control` | switch, close | action, tab_id |

### 2. Interaction Layer (2 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `computer_interact` | click, type, keypress, scroll | action, target, value |
| `web_interact` | click, fill, submit, extract | action, selector, value |

### 3. Vision & Perception (3 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `screenshot` | (single action) | — |
| `vision_analyze` | analyze image | image, query |
| `find_on_screen` | find object/text | image, target_description |

### 4. File System (3 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `file_system` | read, write, delete, open, list | action, path, content |
| `file_search` | search files | query, path |
| `file_metadata` | get metadata | path |

### 5. System & OS (4 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `system_query` | info, health, uptime, processes, time | type |
| `process_control` | list, kill, inspect | action, process_id |
| `power_control` | shutdown, restart, sleep, lock | action |
| `settings_control` | brightness, dark_mode, volume | setting, value |

### 6. Network (2 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `network_query` | wifi, ip, status | type |
| `network_test` | ping, latency | type, target |

### 7. Execution Layer (3 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `shell_execute` | run shell command | command, admin |
| `python_execute` | run Python code | code |
| `task_manager` | start, status, wait, kill, result | action, task_id |

### 8. Web & Search (2 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `web_search` | search web | query |
| `web_navigate` | navigate to URL | url |

### 9. State & Memory (2 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `notes_manager` | create, read, delete | action, content |
| `todo_manager` | add, list, complete, delete | action, item |

### 10. Utilities (5 tools)

| Tool | Actions | Parameters |
|------|---------|------------|
| `clipboard` | copy, paste | action, content |
| `timer` | set, check, cancel | action, duration |
| `calculate` | evaluate expression | expression |
| `text_transform` | summarize, rewrite, translate | action, text |
| `date_time` | now, convert | action, input |

---

## Migration Strategy

### Current State
- **76 tools** with overlapping functionality
- Multiple tools for similar actions (e.g., `open_app`, `close_app`, `list_running_apps`)

### Target State
- **30 tools** with parameterized actions
- Single entry point per capability class

### Example Migrations

#### Before (multiple tools):
```python
open_app(app="chrome")
close_app(app="chrome")
list_running_apps()
```

#### After (single tool with actions):
```python
app_control(action="open", app_name="chrome")
app_control(action="close", app_name="chrome")
app_control(action="list")
```

#### Before (multiple tools):
```python
system_info()
system_health()
get_uptime()
get_time()
```

#### After (single tool with types):
```python
system_query(type="info")
system_query(type="health")
system_query(type="uptime")
system_query(type="time")
```

---

## Implementation Details

### File Location
```
jarvis/tools/consolidated.py
```

### Usage

```python
from jarvis.tools.consolidated import CONSOLIDATED_TOOLS

# Get all 30 tools
for tool_class in CONSOLIDATED_TOOLS:
    tool = tool_class()
    print(f"{tool.name}: {tool.description}")

# Execute a consolidated tool
from jarvis.tools.registry import get_registry
registry = get_registry()

# Use the new consolidated tools
result = registry.execute("app_control", action="open", app_name="notepad")
result = registry.execute("system_query", type="health")
result = registry.execute("file_system", action="read", path="/tmp/test.txt")
```

### Backward Compatibility

The consolidated tools delegate to existing implementations in the registry, ensuring:
- All existing tool logic remains functional
- No breaking changes to underlying implementations
- Gradual migration path for LLM prompts

---

## Enforcement Rules

1. **No Adding Tools** — Unless it introduces a **new capability class**
2. **Extend, Don't Add** — If a new feature fits inside an existing tool via parameters
3. **Log Usage** — If a tool is used <1% → **Remove it**

---

## Schema Generation

Each tool provides an Ollama/OpenAI function-calling schema:

```python
from jarvis.tools.consolidated import AppControlTool

tool = AppControlTool()
schema = tool.get_schema()
# Returns standard function-calling format
```

---

## Testing

Run validation tests:

```bash
cd /workspace
python -c "
from jarvis.tools.consolidated import CONSOLIDATED_TOOLS
print(f'Total tools: {len(CONSOLIDATED_TOOLS)}')
for t in CONSOLIDATED_TOOLS:
    tool = t()
    valid, err = tool.validate()
    print(f'{tool.name}: valid={valid}')
"
```

---

## Next Steps

1. **Update LLM Prompts** — Train planner to use 30-tool schema
2. **Monitor Usage** — Track which tools are actually used
3. **Deprecate Old Tools** — Gradually remove 76 legacy tools from registry
4. **Documentation** — Update all references to use consolidated names

---

## Summary

| Metric | Before | After |
|--------|--------|-------|
| Total Tools | 76 | 30 |
| Tool Categories | 12+ | 10 |
| Avg Parameters | 2-3 | 2-3 |
| Planner Complexity | High | Low |
| Duplication | Yes | Zero |

This implementation transforms the system from "feature-rich" to **agent-grade**.
