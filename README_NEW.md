# JARVIS Enhanced System - New Architecture Documentation

## Overview

This document describes the enhanced JARVIS system with its new modular architecture, including the reasoning layer, skills system, vision perception, and comprehensive testing framework.

## Table of Contents

1. [Quick Start](#quick-start)
2. [System Architecture](#system-architecture)
3. [How to Run the System](#how-to-run-the-system)
4. [Adding New Tools](#adding-new-tools)
5. [Adding New Skills](#adding-new-skills)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements_new.txt

# 2. Run migration (first time only)
python migrate.py

# 3. Run tests to verify installation
python test_tools.py
python test_pipeline.py

# 4. Start JARVIS
python jarvis.py
```

---

## System Architecture

### Layer Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                          │
│              (Voice Input / TTS Output)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Orchestrator                         │
│  listen → transcribe → classify → retrieve → plan → execute │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│   Reasoning   │   │     Skills      │   │    Vision     │
│   Layer       │   │     Layer       │   │   Perception  │
│               │   │                 │   │               │
│ • Planner     │   │ • BaseSkill     │   │ • ScreenState │
│ • Critic      │   │ • MorningBrief  │   │ • VisionAna.  │
│ • Reflector   │   │ • FocusMode     │   │ • FindOnScreen│
│ • Strategy    │   │ • SysOptimizer  │   │               │
└───────────────┘   └─────────────────┘   └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Tool Registry                           │
│         All tools auto-discovered from tools/                │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│    Memory     │   │    Monitoring   │   │    Safety     │
│               │   │                 │   │               │
│ • Semantic    │   │ • Ambient       │   │ • InputFilter │
│ • Procedural  │   │ • Battery       │   │ • PlanValid.  │
│ • Episodic    │   │ • Resource      │   │               │
└───────────────┘   └─────────────────┘   └───────────────┘
```

### Component Responsibilities

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Reasoning** | `planner.py` | Creates ExecutionGraph for complex tasks |
| **Reasoning** | `critic.py` | Reviews plans before execution |
| **Reasoning** | `reflector.py` | Learns from completed tasks |
| **Reasoning** | `strategy_selector.py` | Classifies task complexity |
| **Skills** | `base.py` | Abstract base for all skills |
| **Skills** | `registry.py` | Discovers and manages skills |
| **Vision** | `vision.py` | Analyzes screenshots with LLM |
| **Core** | `orchestrator.py` | Main pipeline controller |

---

## How to Run the System

### Standard Mode (Voice-Activated)

```bash
python jarvis.py
```

JARVIS will:
1. Initialize all components
2. Start ambient monitors (battery, resources, idle, timers)
3. Listen for wake word ("Hey Jarvis")
4. Process voice commands continuously

### Text-Only Mode (Development)

```bash
python jarvis.py --text-mode
```

Useful for:
- Testing without microphone
- Debugging pipeline issues
- Running in headless environments

### With Verbose Logging

```bash
python jarvis.py --verbose
```

Log files are written to `logs/jarvis.log`

### Running Specific Tests

```bash
# Test all tools
python test_tools.py

# Test full pipeline scenarios
python test_pipeline.py

# Run migration verification
python migrate.py
```

---

## Adding New Tools

### Step 1: Create Tool File

Create a new file in the appropriate category folder under `jarvis/tools/`:

```
jarvis/tools/
├── system/      # System operations
├── apps/        # Application management
├── audio/       # Audio/volume control
├── files/       # File operations
├── network/     # Network/connectivity
├── screen/      # Screen capture/vision
├── input/       # Keyboard/mouse/clipboard
├── web/         # Web browsing
├── time/        # Time/date/alarms
├── settings/    # System settings
├── tasks/       # Task management
├── scripts/     # Script execution
└── data/        # Data manipulation (calc, notes, todos)
```

### Step 2: Implement Tool Class

```python
# jarvis/tools/example/my_tool.py

from jarvis.tools.base import BaseTool, ToolResult


class MyNewTool(BaseTool):
    """Description of what this tool does."""
    
    name = "my_new_tool"
    description = "Performs a specific action when requested"
    
    # Define parameters for LLM function calling
    parameters = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Description of param1"
            },
            "param2": {
                "type": "integer",
                "description": "Description of param2"
            }
        },
        "required": ["param1"]
    }
    
    def execute(self, param1: str, param2: int = 0) -> ToolResult:
        """Execute the tool logic."""
        try:
            # Your implementation here
            result_data = {"status": "success", "value": param2 * 2}
            return self.success(
                data=result_data,
                message=f"Completed action with {param1}"
            )
        except Exception as e:
            return self.fail(error=str(e))
```

### Step 3: Update Category `__init__.py`

```python
# jarvis/tools/example/__init__.py

from .my_tool import MyNewTool

__all__ = ['MyNewTool']
```

### Step 4: Auto-Discovery

The tool registry automatically discovers tools by:
1. Scanning all subdirectories in `jarvis/tools/`
2. Looking for classes ending with `Tool`
3. Verifying they inherit from `BaseTool`

No manual registration needed!

### Tool Best Practices

- **Single Responsibility**: Each tool does one thing well
- **Graceful Degradation**: Handle missing hardware/software gracefully
- **Clear Messages**: Provide human-readable success/error messages
- **Type Hints**: Use proper type annotations for parameters
- **Validation**: Validate inputs before executing

---

## Adding New Skills

### What is a Skill?

Skills are higher-level capabilities that may combine multiple tools and include planning, error recovery, and rollback capabilities.

### Step 1: Create Skill File

Create in `jarvis/skills/builtin/` or `jarvis/skills/learned/`:

```python
# jarvis/skills/builtin/my_skill.py

from jarvis.skills.base import BaseSkill, SkillStep, Recovery, RecoveryAction


class MyCustomSkill(BaseSkill):
    """Skill for performing a complex multi-step task."""
    
    name = "my_custom_skill"
    description = "Handles complex scenarios requiring coordination"
    
    def can_handle(self, task: str) -> float:
        """Return confidence 0.0-1.0 that this skill can handle the task."""
        keywords = ["keyword1", "keyword2", "complex task"]
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in keywords):
            return 0.9
        return 0.3
    
    def plan(self, task: str) -> list[SkillStep]:
        """Create ordered list of steps to accomplish the task."""
        return [
            SkillStep(
                id="step1",
                tool_or_skill="open_app",
                params={"app_name": "notepad"},
                depends_on=[],
                success_criteria="Notepad is open",
                fallback_strategy="Try alternative text editor"
            ),
            SkillStep(
                id="step2",
                tool_or_skill="write_file",
                params={"content": "Hello"},
                depends_on=["step1"],
                success_criteria="Text is written",
                fallback_strategy="Report failure to user"
            )
        ]
    
    def handle_failure(self, step: SkillStep, error: Exception) -> Recovery:
        """Determine how to recover from a failure."""
        return Recovery(
            action=RecoveryAction.RETRY,
            max_retries=2,
            alternative_step=None
        )
    
    def summarize(self) -> str:
        """One-sentence summary of what was accomplished."""
        return "Completed the custom task successfully."
```

### Step 2: Register Skill

Skills in `jarvis/skills/builtin/` are auto-discovered at startup.

For dynamic skills, use:

```python
from jarvis.skills.registry import get_skills_registry

registry = get_skills_registry()
registry.add_learned_skill(my_skill_instance)
```

### Skill vs Tool Decision Tree

```
Does it need multiple tools? 
    ├── No → Create a Tool
    └── Yes → Does it need planning/recovery?
              ├── No → Create a Tool that calls other tools
              └── Yes → Create a Skill
```

---

## Configuration

### Switching Between Cloud and Local Ollama

Edit `jarvis/config/config.py`:

```python
# Local Ollama (default)
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2"

# Cloud Ollama (if you have remote server)
OLLAMA_BASE_URL = "https://your-server.com:11434"
OLLAMA_API_KEY = "your-api-key"  # Optional authentication
```

### Configuring Voice and Wake Word

Edit `jarvis/profile/user_profile.json`:

```json
{
    "voice": {
        "wake_word": "hey jarvis",
        "tts_voice": "en-US-AriaNeural",
        "tts_rate": 1.0,
        "stt_language": "en-US"
    },
    "preferences": {
        "confirm_destructive_actions": true,
        "verbose_responses": false
    }
}
```

### Environment Variables

Create `.env` file in project root:

```bash
# Ollama Configuration
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# API Keys (if using cloud services)
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...

# Custom Paths
JARVIS_DATA_DIR=/path/to/data
JARVIS_LOG_LEVEL=INFO
```

---

## Troubleshooting

### Common Issues

#### 1. "Module not found" Errors

**Symptom**: `ImportError: No module named 'xyz'`

**Solution**:
```bash
pip install -r requirements_new.txt
```

#### 2. Ollama Connection Failed

**Symptom**: `Connection refused to localhost:11434`

**Solution**:
```bash
# Check if Ollama is running
ollama list

# If not running, start it
ollama serve

# Pull required model
ollama pull llama3.2
```

#### 3. Audio Not Working

**Symptom**: No sound output or microphone not detected

**Solution**:
- Windows: Check default playback/recording devices
- Linux: `sudo apt install portaudio19-dev python3-pyaudio`
- macOS: Check System Preferences → Sound

#### 4. Tools Not Loading

**Symptom**: "Unknown tool" errors for valid tools

**Solution**:
```bash
# Run migration to verify tools
python migrate.py

# Check tool registry directly
python -c "from jarvis.tools.registry import get_registry; r=get_registry(); r.load_all_tools(); print(r.get_tool_names())"
```

#### 5. Vision Analysis Failing

**Symptom**: `analyze_screen` returns errors

**Solution**:
```bash
# Verify vision model is available
ollama pull llava-llama3

# Check OpenCV installation
python -c "import cv2; print(cv2.__version__)"
```

### Debug Mode

Enable detailed logging:

```bash
# Set environment variable
export JARVIS_LOG_LEVEL=DEBUG

# Or run with verbose flag
python jarvis.py --verbose
```

Logs are written to `logs/jarvis.log`

### Running Diagnostics

```bash
# Full system diagnostic
python -c "
from jarvis.tools.system.info import SystemInfoTool
tool = SystemInfoTool()
result = tool.execute()
print(result.data)
"

# Test individual components
python test_tools.py --verbose
python test_pipeline.py --verbose
```

### Reset to Defaults

```bash
# Backup current data
cp jarvis_data/user_profile.json jarvis_data/user_profile.json.bak

# Remove generated files
rm -rf jarvis_data/*.json
rm -rf backup/

# Re-run migration
python migrate.py
```

---

## Support

For additional help:
1. Check logs in `logs/jarvis.log`
2. Run `python migrate.py` for system health check
3. Review test results from `test_tools.py` and `test_pipeline.py`
