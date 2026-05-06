# JARVIS 30-Tool Capability Architecture

## Overview

This document describes the refactored JARVIS architecture organized around **30 core capabilities** instead of random tools. This design prevents routing confusion, overlapping responsibilities, and brittle decision chains.

**Target Stack:** GPT-OSS 120B (Reasoning) + Gemma 3 27B (Vision)

---

## Architecture Principles

1. **Capability-Based Organization**: Tools are grouped by functional capability, not implementation details
2. **Deterministic Execution**: Each capability has a clear, single responsibility
3. **Tight Interfaces**: Standardized `execute()` method with consistent return format
4. **Model Integration Ready**: Placeholder hooks for GPT-OSS 120B and Gemma 3 27B integration

---

## The 30 Core Capabilities

### 1. Core Orchestration (4 tools)
*Controls decision flow and system state*

| Tool | Purpose | Status |
|------|---------|--------|
| `intent_router` | Classifies user command → tool routing | ✅ Implemented |
| `task_planner` | Breaks goal into steps | ✅ Implemented |
| `tool_dispatcher` | Executes selected tool | ✅ Implemented |
| `memory_manager` | Store/retrieve short + long term context | ✅ Implemented |

### 2. System Control (6 tools)
*Direct OS-level interaction*

| Tool | Purpose | Status |
|------|---------|--------|
| `run_terminal_command` | Execute shell commands (admin capable) | ✅ Implemented |
| `run_python_code` | Safe local execution sandbox | ✅ Implemented |
| `window_manager` | Minimize/maximize/focus apps | ✅ Implemented |
| `process_manager` | Kill/start processes | ✅ Implemented |
| `system_info` | CPU, RAM, disk, OS state | ✅ Implemented |
| `shutdown_restart_control` | Power actions | ✅ Implemented |

### 3. Vision & Screen Understanding (3 tools)
*Powered by Gemma 3 27B*

| Tool | Purpose | Status |
|------|---------|--------|
| `screen_capture` | Grab screen or region | ✅ Implemented |
| `ocr_extract_text` | Text from images/screen | ✅ Implemented |
| `vision_analyzer` | Interpret UI, detect buttons, objects | ✅ Implemented |

### 4. Web & Knowledge (5 tools)
*External intelligence layer*

| Tool | Purpose | Status |
|------|---------|--------|
| `web_search` | Real-time search | ✅ Implemented |
| `web_scraper` | Extract page content | ✅ Implemented |
| `url_reader` | Structured page parsing | ✅ Implemented |
| `summarizer` | Compress long text | ✅ Implemented |
| `fact_checker` | Validate claims across sources | ✅ Implemented |

### 5. File & Data System (4 tools)
*For local productivity*

| Tool | Purpose | Status |
|------|---------|--------|
| `file_reader` | Read files from disk | ✅ Implemented |
| `file_writer` | Write files to disk | ✅ Implemented |
| `file_search` | Search for files | ✅ Implemented |
| `data_parser` | CSV/JSON/Excel handling | ✅ Implemented |

### 6. Productivity Tools (4 tools)
*Everyday assistant layer*

| Tool | Purpose | Status |
|------|---------|--------|
| `calendar_manager` | Manage calendar events | ✅ Implemented |
| `task_scheduler` | Schedule and manage tasks | ✅ Implemented |
| `notes_manager` | Create and manage notes | ✅ Implemented |
| `email_handler` | Send and manage emails | ✅ Implemented |

### 7. Media & Interaction (3 tools)
*Human-facing interaction layer*

| Tool | Purpose | Status |
|------|---------|--------|
| `audio_player` | YouTube/Spotify local control | ✅ Implemented |
| `voice_synthesizer` | Text-to-Speech (TTS) | ✅ Implemented |
| `voice_recognizer` | Speech-to-Text (STT) | ✅ Implemented |

### 8. AI Internal Tools (3 tools)
*Model-to-model intelligence layer*

| Tool | Purpose | Status |
|------|---------|--------|
| `reasoning_engine` | GPT-OSS 120B main planner | ✅ Implemented |
| `vision_reasoning_bridge` | Gemma → text reasoning conversion | ✅ Implemented |
| `tool_self_evaluator` | Checks tool outputs for errors | ✅ Implemented |

---

## Directory Structure

```
jarvis/capabilities/
├── __init__.py                 # Core exports and validation
├── registry.py                 # Unified capability registry
├── orchestration/
│   └── __init__.py             # 4 orchestration tools
├── system_control/
│   └── __init__.py             # 6 system control tools
├── vision/
│   └── __init__.py             # 3 vision tools
├── web_knowledge/
│   └── __init__.py             # 5 web tools
├── file_data/
│   └── __init__.py             # 4 file tools
├── productivity/
│   └── __init__.py             # 4 productivity tools
├── media_interaction/
│   └── __init__.py             # 3 media tools
└── ai_internal/
    └── __init__.py             # 3 AI internal tools
```

---

## Usage

### Basic Initialization

```python
from jarvis.capabilities.registry import initialize_registry

# Initialize with models
registry = initialize_registry(
    reasoning_model=gpt_oss_120b,  # Your GPT-OSS 120B instance
    vision_model=gemma_3_27b,      # Your Gemma 3 27B instance
    config={"sandbox_mode": True}
)

# Execute any capability
result = registry.execute("system_info", info_type="all")
print(result["output"])

# List all capabilities
capabilities = registry.list_capabilities()
for cap in capabilities:
    print(f"{cap['name']}: {cap['category']}")
```

### Direct Tool Access

```python
from jarvis.capabilities.system_control import get_system_info

tool = get_system_info()
result = tool.execute(info_type="cpu")
```

---

## Migration from Old Toolset

The old `jarvis/tools/` directory contained 78+ fragmented tools with significant overlap. 

### What Changed

| Before | After |
|--------|-------|
| 78+ scattered tools | 30 organized capabilities |
| Overlapping functionality | Clear capability boundaries |
| Inconsistent interfaces | Standardized `execute()` method |
| No central registry | Unified `CapabilityRegistry` |
| Random naming | Capability-based naming |

### Deprecated Tools

The following tool categories have been consolidated:
- Multiple screenshot tools → `screen_capture`
- Multiple URL openers → `web_search` + `url_reader`
- Multiple window managers → `window_manager`
- Multiple process tools → `process_manager`

Old tools remain in `jarvis/tools/` for reference but should not be used in new code.

---

## Next Steps

1. **Model Integration**: Connect actual GPT-OSS 120B and Gemma 3 27B instances
2. **Backend Configuration**: Configure SMTP, calendar APIs, search APIs
3. **Testing**: Add comprehensive test suite for each capability
4. **Documentation**: Expand docstrings with examples
5. **Performance**: Add caching and optimization layers

---

## Design Notes

### Why 30 Tools?

Exceeding ~30-35 tools leads to:
- Routing confusion in the LLM
- Overlapping responsibilities
- Brittle decision chains

30 is the balanced minimum viable "real JARVIS" architecture covering:
- OS control
- Vision
- Web intelligence
- Productivity
- AI reasoning loop

### Interface Standardization

All capabilities follow the same pattern:
```python
class CapabilityName:
    def execute(self, param1, param2, **kwargs) -> dict:
        """Execute the capability."""
        try:
            # Implementation
            return {"success": True, "output": {...}}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

This consistency enables:
- Predictable error handling
- Easy tool swapping
- Simplified testing
- Clear documentation
