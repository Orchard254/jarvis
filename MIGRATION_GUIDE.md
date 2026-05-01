# JARVIS Refactoring Migration Guide

## Overview

This guide explains how to migrate from the old monolithic architecture to the new modular architecture.

## Current State

**Old Architecture:**
- `jarvis.py` — Main orchestration (does too much)
- `pc_control.py` — 3,144 lines, all tools in one file with 7 duplicate handlers
- `brain.py` — LLM inference calls
- `control_plane.py` — Tool validation
- `tools.py` — Tool schemas
- And 12+ other scattered files

**New Architecture:**
```
jarvis/
├── core/           — Orchestrator, brain, memory, context
├── perception/     — STT, wake word, vision, intent classifier
├── reasoning/      — Planner, critic, reflector, strategy
├── execution/      — Control plane, skill runner, tool runner
├── tools/          — Modular tool implementations (by category)
├── skills/         — High-level skill definitions
├── memory/         — Working, episodic, semantic, procedural
├── safety/         — Input filter, plan validator, tool guard
├── output/         — TTS, notifications, formatting
├── monitoring/     — Ambient, reliability, health check
├── models/         — Ollama client, router
├── profile/        — User profile, learning, routines
└── config/         — Config, prompts, schemas
```

## Files Already Created

### Core Infrastructure
1. ✅ `models/ollama_client.py` — LLM client with cloud/local fallback
2. ✅ `models/router.py` — Task routing to model configs
3. ✅ `tools/base.py` — BaseTool abstract class
4. ✅ `tools/registry.py` — Tool registry and loader
5. ✅ `tools/executor.py` — Tool execution dispatcher

### System Tools
6. ✅ `tools/system/power.py` — lock_pc, sleep_pc, restart_pc, shutdown_pc
7. ✅ `tools/system/info.py` — battery_status, system_info, system_health, get_top_processes, get_uptime
8. ✅ `tools/system/display.py` — set_brightness, toggle_dark_mode

### App Tools
9. ✅ `tools/apps/launcher.py` — open_app, close_app, list_running_apps
10. ✅ `tools/apps/window.py` — get_window_list, focus_window, minimize_windows

### Audio Tools
11. ✅ `tools/audio/volume.py` — set_volume, volume_up, volume_down, mute_volume, get_volume

### File Tools
12. ✅ `tools/files/operations.py` — read_file, create_file, open_file, delete_file

### Network Tools
13. ✅ `tools/network/connectivity.py` — get_wifi, get_ip, ping

### Screen Tools
14. ✅ `tools/screen/capture.py` — screenshot, analyze_screen, click_at, find_on_screen

### Input Tools
15. ✅ `tools/input/clipboard.py` — copy_to_clipboard, paste_from_clipboard, type_text, press_key

### Web Tools
16. ✅ `tools/web/browser.py` — search_web, open_url

### Time Tools
17. ✅ `tools/time/clock.py` — get_time, get_date, set_timer, wait

### Settings Tools
18. ✅ `tools/settings/windows.py` — open_settings, open_control_panel, open_recycle_bin

### Task Tools
19. ✅ `tools/tasks/background.py` — task_manager

### Script Tools
20. ✅ `tools/scripts/runner.py` — run_powershell, run_command, run_python

### Data Tools
21. ✅ `tools/data/notes.py` — create_note, read_notes, delete_note
22. ✅ `tools/data/todo.py` — add_todo, list_todos, complete_todo, delete_todo
23. ✅ `tools/data/calculate.py` — calculate

## Migration Steps

### Phase 1: Setup New Structure (Complete)
1. Create directory structure ✅
2. Create __init__.py files ✅
3. Implement base classes ✅

### Phase 2: Port Tools (In Progress)
The following tools need to be verified against the old pc_control.py:

**Duplicate Handlers to Remove:**
- `run_command` → Use `tools/scripts/runner.py:RunCommandTool`
- `search_web` → Use `tools/web/browser.py:SearchWebTool`
- `create_file` → Use `tools/files/operations.py:CreateFileTool`
- `get_time` → Use `tools/time/clock.py:GetTimeTool`
- `get_date` → Use `tools/time/clock.py:GetDateTool`
- `screenshot` → Use `tools/screen/capture.py:ScreenshotTool`
- `calculate` → Use `tools/data/calculate.py:CalculateTool`

### Phase 3: Safety Layer
Create these files:
- `safety/tool_guard.py` — Replaces control_plane.py
- `safety/audit_log.py` — Immutable action log
- `safety/input_filter.py` — Input sanitization
- `safety/plan_validator.py` — Plan review

### Phase 4: Memory System
Create these files:
- `memory/working.py` — Conversation window
- `memory/episodic.py` — Session history
- `memory/semantic.py` — User facts with embeddings
- `memory/procedural.py` — Learned patterns
- `memory/manager.py` — Coordinates all memory types

### Phase 5: Perception
Create these files:
- `perception/stt.py` — Google STT wrapper
- `perception/wake_word.py` — openwakeword wrapper
- `perception/vision.py` — Screen analysis with multimodal LLM
- `perception/intent_classifier.py` — Chat vs agent routing ONLY

### Phase 6: Reasoning
Create these files:
- `reasoning/planner.py` — Task decomposer
- `reasoning/critic.py` — Plan reviewer
- `reasoning/reflector.py` — Outcome analyzer
- `reasoning/strategy_selector.py` — Picks reasoning depth

### Phase 7: Output
Create these files:
- `output/tts.py` — Kokoro/Piper TTS with queue
- `output/notifier.py` — Windows toast notifications
- `output/formatter.py` — Response formatting

### Phase 8: Core Integration
Create these files:
- `core/context.py` — Context assembly
- `core/brain.py` — LLM inference coordinator
- `core/orchestrator.py` — Main loop (replaces jarvis.py)

### Phase 9: Entry Point
Update `jarvis.py` to be a thin entry point that starts the orchestrator.

## Key Design Changes

### 1. Tool Registry is Single Source of Truth
```python
from jarvis.tools.registry import get_registry, execute_tool

# Before: Giant if-else chain in pc_control.py
# After: Registry-based dispatch
result = execute_tool("set_volume", level=50)

# Invalid tool names are rejected immediately
if not get_registry().has_tool(tool_name):
    error = f"Unknown tool: '{tool_name}'. Available: {get_registry().get_tool_names()}"
```

### 2. Intent Classifier Only Routes Modes
```python
# Before: Intent classifier filtered tool choices (WRONG)
# After: Intent classifier only routes chat vs agent mode
mode = intent_classifier.classify(user_input)
if mode == "chat":
    # Direct LLM response, no tools
else:
    # Enable tool calling
```

### 3. Vision Layer Feeds Screenshots to LLM
```python
from jarvis.perception.vision import analyze_image_with_llm

base64_img = take_screenshot()
analysis = analyze_image_with_llm(base64_img, "What's on screen?")
# Feed analysis back to LLM for context
```

### 4. Four-Type Memory System
```python
from jarvis.memory.manager import get_memory_manager

memory = get_memory_manager()

# Working: Current conversation
memory.working.add_message("user", "Hello")

# Episodic: Past sessions
memory.episodic.save_session(session_data)

# Semantic: User facts
memory.semantic.remember("User prefers dark mode")

# Procedural: Learned patterns
memory.procedural.learn_pattern("morning_routine", steps)
```

### 5. Layered Safety
```python
# Each layer is independent
input_filter.check(user_input)      # Layer 1
plan_validator.review(plan)         # Layer 2
tool_guard.validate(tool_call)      # Layer 3
execution_monitor.watch(execution)  # Layer 4
audit_log.record(action)            # Layer 5
```

## Testing Strategy

### Unit Tests
Test each tool independently:
```python
def test_set_volume():
    result = execute_tool("set_volume", level=50)
    assert result.success
    assert "50" in result.output
```

### Integration Tests
Test tool chains:
```python
def test_open_app_and_set_volume():
    execute_tool("open_app", app_name="spotify")
    execute_tool("set_volume", level=30)
    # Verify both succeeded
```

### Safety Tests
Verify blocked operations:
```python
def test_dangerous_command_blocked():
    result = execute_tool("run_command", command="format C:")
    assert not result.success
    assert "blocked" in result.error.lower()
```

## Rollback Plan

If issues occur:
1. Keep old `pc_control.py` as backup
2. New architecture imports old tools as fallback
3. Gradual migration tool-by-tool

## Next Steps

1. Complete remaining tool modules
2. Implement safety layer
3. Build memory system
4. Create vision integration
5. Update main orchestrator
6. Test end-to-end

## Contact

For questions about the migration, refer to the inline documentation in each module.
