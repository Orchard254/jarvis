# JARVIS — Local Desktop AI Agent

A desktop AI agent system that uses LLM inference to generate tool calls, with deterministic validation and execution layers. The system orchestrates voice input through intent classification to PC control actions.

**Note:** This is a development/testing version. The full system requires audio hardware and an external LLM API (Ollama cloud).

## Architecture Overview

JARVIS uses a **flat modular architecture** with all components organized as top-level packages:

```
workspace/
├── core/           # Core engine (Brain, Orchestrator, Memory, Context)
├── perception/     # Input processing (STT, Vision, Intent, Wake Word)
├── reasoning/      # Planning & decision making (Planner, Critic, Strategy)
├── safety/         # Safety layer (Input Filter, Plan Validator, Tool Guard, Audit)
├── memory/         # Memory systems (Working, Episodic, Semantic, Procedural)
├── tools/          # Tool registry & execution (58+ tools organized by category)
├── skills/         # High-level skill compositions
├── execution/      # Dynamic script execution sandbox
├── output/         # Output handling (TTS, Notifications, Formatting)
├── config/         # Configuration management
├── models/         # Data models & schemas
├── monitoring/     # System health & performance monitoring
├── data/           # Persistent data storage
└── profile/        # User profiles & preferences
```

### Component Responsibilities

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `core/brain.py` | LLM inference & tool call generation | `Brain` |
| `core/orchestrator.py` | Main command orchestration loop | `Orchestrator` |
| `core/memory.py` | Working memory & context management | `MemoryManager` |
| `core/context.py` | Conversation context tracking | `ContextManager` |
| `perception/stt.py` | Speech-to-text conversion | `SpeechToText`, `STTResult` |
| `perception/vision.py` | Image analysis & OCR | `VisionAnalyzer` |
| `perception/intent_classifier.py` | User intent detection | `IntentClassifier` |
| `perception/wake_word.py` | Voice activation detection | `WakeWordDetection` |
| `reasoning/planner.py` | Multi-step plan generation | `Planner` |
| `reasoning/critic.py` | Plan quality assessment | `Critic` |
| `safety/input_filter.py` | Input content filtering | `InputFilter`, `FilterResult` |
| `safety/plan_validator.py` | Risk assessment for plans | `PlanValidator`, `PlanRiskLevel` |
| `safety/tool_guard.py` | Tool execution validation | `ToolGuard` |
| `safety/audit_log.py` | Security audit trail | `AuditLog` |
| `memory/working.py` | Short-term working memory | `WorkingMemory` |
| `memory/episodic.py` | Event-based memory storage | `EpisodicMemory` |
| `memory/semantic.py` | Fact & knowledge storage | `SemanticMemory` |
| `memory/procedural.py` | Skill & procedure memory | `ProceduralMemory` |
| `tools/executor.py` | Tool registration & execution | `ToolExecutor`, `ToolRegistry` |
| `output/tts.py` | Text-to-speech output | `TTSManager`, `speak()` |
| `output/notifier.py` | Desktop notifications | `NotificationManager` |
| `output/formatter.py` | Response formatting | `ResponseFormatter` |

## Execution Pipeline

```
user input → perception (STT/Vision) → intent classification → safety filter
         → brain (LLM proposes tools) → plan validator → tool guard
         → tool executor → result → memory update → output (TTS/Notification)
```

### Pipeline Stages

1. **Perception** — Converts raw input (audio, text, images) into structured data
2. **Intent Classification** — Determines user intent with confidence scores
3. **Safety Layer** — Filters harmful input and validates execution plans
4. **Brain (LLM)** — Generates tool calls based on intent and context
5. **Tool Execution** — Executes validated tools in sandboxed environment
6. **Memory Update** — Stores experiences for future reference
7. **Output** — Delivers results via TTS, notifications, or formatted text

## Key Features

### Modular Architecture
- Clean separation of concerns across 14 specialized modules
- Easy to extend with new tools, skills, or perception capabilities
- Lazy loading for optional components (wake word detection, vision)

### Tool System
- 58+ pre-built tools organized by category (apps, audio, data, files, network, system, web)
- Dynamic tool registration and discovery
- Tool reliability tracking with success/failure decay
- Sandboxed execution for untrusted code

### Memory System
- **Working Memory** — Short-term context for active conversations
- **Episodic Memory** — Time-stamped event storage
- **Semantic Memory** — Facts and knowledge base
- **Procedural Memory** — Learned skills and procedures

### Safety Layer
- **Input Filter** — Blocks harmful or inappropriate requests
- **Plan Validator** — Assesses risk level of proposed action sequences
- **Tool Guard** — Validates tool parameters before execution
- **Audit Log** — Complete security trail of all operations

### Intent Classification
- Multi-class intent detection with confidence scoring
- Safe passthrough for read-only queries (time, system health, IP)
- Intent-to-tool alignment validation

## Setup

### Requirements
- Python 3.10+
- Windows with PowerShell (for system tools)
- Internet access for Ollama API
- Optional: Microphone for voice input, camera for vision

### Installation
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables
Create a `.env` file:
```
OLLAMA_API_KEY=your_key_here
```

### Running
```bash
# Full system (requires audio hardware for voice mode)
python jarvis.py

# Text injection testing (no audio required)
python test_inject.py

# Run integration tests
pytest test_jarvis_integration.py -v
```

## Testing

### Integration Tests
```bash
# Full test suite
pytest test_jarvis_integration.py -v

# Specific test categories
pytest test_phase3_safety.py -v    # Safety layer tests
pytest test_phase4_memory.py -v    # Memory system tests
pytest test_dynamic_integration.py -v  # Dynamic scripting tests
```

### Interactive Testing
```bash
# Text injection harness for deterministic testing
python test_inject.py

# Test specific tools
python -c "from tools.executor import ToolExecutor; e = ToolExecutor(); print(e.list_tools())"
```

## Project Structure

```
/workspace/
├── jarvis/                 # Main package
│   ├── core/              # Brain, Orchestrator, Memory, Context
│   ├── perception/        # STT, Vision, Intent, Wake Word
│   ├── reasoning/         # Planner, Critic, Strategy Selector
│   ├── safety/            # Input Filter, Plan Validator, Tool Guard, Audit
│   ├── memory/            # Working, Episodic, Semantic, Procedural
│   ├── tools/             # 58+ tools in categorized subdirectories
│   ├── skills/            # High-level skill compositions
│   ├── execution/         # Dynamic script sandbox
│   ├── output/            # TTS, Notifications, Formatting
│   ├── config/            # Configuration management
│   ├── models/            # Data schemas
│   ├── monitoring/        # Health & performance
│   ├── data/              # Persistent storage
│   └── profile/           # User preferences
├── jarvis.py              # Entry point script
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
├── test_*.py             # Test suites
└── README.md             # This file
```

## Design Philosophy

### Separation of Concerns
Each module has a single, well-defined responsibility:
- **Perception** handles input only
- **Brain** handles LLM inference only (proposes, never executes)
- **Safety** handles validation only
- **Execution** handles tool running only
- **Memory** handles persistence only

### Deterministic Enforcement
The LLM is never in direct control of execution:
1. User input is classified for intent
2. LLM proposes tools based on intent
3. Safety layer validates the proposal
4. Only validated tools are executed
5. Results are fed back for agentic loops

### Defense in Depth
Multiple safety layers protect against harmful operations:
1. Input filtering (before LLM)
2. Intent validation (after classification)
3. Plan review (before execution)
4. Parameter validation (per tool)
5. Audit logging (all operations)

---

## Enhanced Architecture

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

### Enhanced Component Responsibilities

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

### Health Monitoring

Run the health check runner alongside JARVIS to monitor system status:

```bash
python health_check_runner.py              # Continuous monitoring (60s interval)
python health_check_runner.py --once       # Single check
python health_check_runner.py -i 30        # 30-second interval
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

### Skill vs Tool Decision Tree

```
Does it need multiple tools? 
    ├── No → Create a Tool
    └── Yes → Does it need planning/recovery?
              ├── No → Create a Tool that calls other tools
              └── Yes → Create a Skill
```

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

---

## Current Limitations

1. **Platform Specificity** — Tools are Windows-specific (PowerShell execution)
2. **External LLM Dependency** — Requires Ollama cloud API; no local fallback
3. **Audio Hardware** — Full voice mode requires microphone
4. **Multi-step Complexity** — Complex sequences may fail mid-execution
5. **Parameter Recovery** — Limited recovery from subtle parameter errors

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

## Debugging

Logs output to console and `jarvis/logs/` directory. Key log markers:
- `[JARVIS][INTENT]` — Intent classification decisions
- `[JARVIS][SAFETY]` — Safety layer validations
- `[JARVIS][TOOL]` — Tool execution events
- `[MEMORY]` — Memory operations
- `[BRAIN]` — LLM interactions

## Contributing

When adding new components:
1. Follow the modular structure (add to appropriate subdirectory)
2. Register tools via `ToolRegistry`
3. Add safety validations for new capabilities
4. Include unit tests in `test_*.py` files
5. Update this README with new modules

## License

MIT
