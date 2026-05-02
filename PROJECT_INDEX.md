# JARVIS Project Index

## Project Overview

**JARVIS** is a local desktop AI agent system that uses LLM inference (Ollama) to generate tool calls, with deterministic validation and execution layers. The system orchestrates voice input through intent classification to PC control actions.

### Key Characteristics
- **Architecture**: Flat modular architecture with 14 specialized modules
- **Language**: Python 3.10+
- **LLM Backend**: Ollama (cloud/local fallback)
- **Platform**: Windows-focused (with some cross-platform support)
- **Tools**: 58+ pre-built tools organized by category
- **Safety**: Multi-layer safety system (input filter, plan validator, tool guard)

---

## Directory Structure

```
/workspace/
├── jarvis.py                      # Main entry point
├── settings.py                    # Centralized configuration (single source of truth)
├── requirements.txt               # Python dependencies
├── README.md                      # Main documentation
├── PROJECT_INDEX.md              # This file
│
├── jarvis/                        # Main package
│   ├── core/                     # Core engine
│   │   ├── brain.py              # LLM inference coordinator
│   │   ├── orchestrator.py       # Main command orchestration loop
│   │   ├── memory.py             # Working memory & context management
│   │   └── context.py            # Conversation context tracking
│   │
│   ├── perception/               # Input processing
│   │   ├── stt.py                # Speech-to-text (Google Speech Recognition)
│   │   ├── vision.py             # Image analysis & OCR
│   │   ├── intent_classifier.py  # User intent detection
│   │   └── wake_word.py          # Voice activation ("Hey Jarvis")
│   │
│   ├── reasoning/                # Planning & decision making
│   │   ├── planner.py            # Multi-step plan generation (ExecutionGraph)
│   │   ├── critic.py             # Plan quality assessment (APPROVED/NEEDS_REVISION/BLOCKED)
│   │   ├── reflector.py          # Learning from completed tasks
│   │   └── strategy_selector.py  # Task complexity classification
│   │
│   ├── safety/                   # Safety layer
│   │   ├── input_filter.py       # Input content filtering
│   │   ├── plan_validator.py     # Risk assessment for plans
│   │   ├── tool_guard.py         # Tool execution validation
│   │   └── audit_log.py          # Security audit trail
│   │
│   ├── memory/                   # Memory systems
│   │   ├── manager.py            # Unified memory coordinator
│   │   ├── working.py            # Short-term working memory
│   │   ├── episodic.py           # Event-based memory storage
│   │   ├── semantic.py           # Facts & knowledge storage
│   │   └── procedural.py         # Skill & procedure memory
│   │
│   ├── tools/                    # Tool registry & execution (58+ tools)
│   │   ├── registry.py           # Tool discovery & registration (singleton)
│   │   ├── executor.py           # Tool execution engine
│   │   ├── base.py               # BaseTool abstract class
│   │   ├── apps/                 # Application management (launcher, window)
│   │   ├── audio/                # Volume control
│   │   ├── data/                 # Data manipulation (calc, notes, todo)
│   │   ├── files/                # File operations
│   │   ├── input/                # Keyboard/mouse/clipboard
│   │   ├── network/              # Network/connectivity
│   │   ├── screen/               # Screen capture & vision
│   │   ├── scripts/              # Dynamic script execution
│   │   ├── settings/             # System settings
│   │   ├── system/               # System operations (power, display, info)
│   │   ├── tasks/                # Task management
│   │   ├── time/                 # Time/date/alarms
│   │   └── web/                  # Web browsing
│   │
│   ├── skills/                   # High-level skill compositions
│   │   ├── base.py               # BaseSkill abstract class
│   │   ├── registry.py           # Skill discovery
│   │   └── builtin/              # Built-in skills
│   │       ├── task_executor.py
│   │       ├── system_optimizer.py
│   │       ├── morning_briefing.py
│   │       └── focus_mode.py
│   │
│   ├── execution/                # Dynamic script execution sandbox
│   │   ├── control_plane.py      # Plan execution coordinator
│   │   ├── tool_runner.py        # Tool execution wrapper
│   │   ├── skill_runner.py       # Skill execution wrapper
│   │   └── rollback.py           # Rollback manager
│   │
│   ├── output/                   # Output handling
│   │   ├── tts.py                # Text-to-speech
│   │   ├── notifier.py           # Desktop notifications
│   │   └── formatter.py          # Response formatting
│   │
│   ├── config/                   # Configuration management
│   │   ├── config.py             # Config loader (deprecated, backwards compat)
│   │   ├── prompts/              # System prompts
│   │   │   ├── jarvis_prompt.py
│   │   │   ├── planning_prompt.py
│   │   │   ├── critic_prompt.py
│   │   │   ├── reflection_prompt.py
│   │   │   ├── scripting_prompt.py
│   │   │   └── vision_prompt.py
│   │   └── schemas/              # Data schemas
│   │       └── tool_schemas.py
│   │
│   ├── models/                   # Data models & clients
│   │   ├── ollama_client.py      # Ollama API client with fallback
│   │   └── router.py             # Model routing logic
│   │
│   ├── monitoring/               # System health & performance
│   │   ├── ambient.py            # Background system monitoring
│   │   ├── health_check.py       # Health check utilities
│   │   └── reliability.py        # Tool reliability tracking
│   │
│   ├── data/                     # Persistent data storage
│   └── profile/                  # User profiles & preferences
│       ├── user_profile.py
│       ├── learning.py
│       └── routines.py
│
├── tests/                        # Test suite
│   ├── unit/                     # Unit tests
│   │   ├── test_dynamic_scripter.py
│   │   ├── test_stt_enhancements.py
│   │   ├── test_tts_voices.py
│   │   └── test_inject.py
│   ├── integration/              # Integration tests
│   │   ├── test_dynamic_integration.py
│   │   └── test_jarvis_integration.py
│   ├── test_phase3_safety.py     # Safety layer tests
│   └── test_phase4_memory.py     # Memory system tests
│
├── docs/                         # Documentation
│   ├── PHASE3_COMPLETE.md        # Safety layer integration
│   ├── DYNAMIC_SCRIPTING_COMPLETE.md
│   ├── DYNAMIC_INTEGRATION_COMPLETE.md
│   ├── STT_WHISPER_COMPLETE.md
│   ├── STT_ENHANCEMENTS.md
│   ├── MIGRATION_GUIDE.md
│   └── CLEANUP_SUMMARY.md
│
├── logs/                         # Log files
│   ├── jarvis.log
│   └── health_monitor.log
│
├── data/                         # Application data
│   └── procedural.json
│
└── jarvis_data/                  # User data storage
    ├── conversation_history.json
    ├── episodes/
    ├── procedural.json
    ├── semantic.json
    ├── tool_reliability.json
    └── user_profile.json
```

---

## Execution Pipeline

```
User Input (Voice/Text)
        ↓
┌───────────────────────┐
│  1. PERCEPTION        │
│  - STT (Speech→Text)  │
│  - Vision (if image)  │
│  - Intent Classification
└───────────────────────┘
        ↓
┌───────────────────────┐
│  2. SAFETY FILTER     │
│  - InputFilter        │
│  - Blocks harmful input
└───────────────────────┘
        ↓
┌───────────────────────┐
│  3. BRAIN (LLM)       │
│  - OllamaClient       │
│  - Proposes tools     │
│  - Function calling   │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  4. REASONING         │
│  - Planner (if complex)
│  - Critic review      │
│  - Strategy Selector  │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  5. SAFETY VALIDATION │
│  - PlanValidator      │
│  - ToolGuard          │
│  - Risk assessment    │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  6. EXECUTION         │
│  - ControlPlane       │
│  - ToolRunner         │
│  - SkillRunner        │
│  - RollbackManager    │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  7. MEMORY UPDATE     │
│  - WorkingMemory      │
│  - EpisodicMemory     │
│  - SemanticMemory     │
│  - ProceduralMemory   │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  8. OUTPUT            │
│  - TTS (Text→Speech)  │
│  - Notifications      │
│  - Formatted response │
└───────────────────────┘
        ↓
┌───────────────────────┐
│  9. REFLECTION        │
│  - OutcomeReflector   │
│  - Learn from results │
│  - Update procedures  │
└───────────────────────┘
```

---

## Key Components Reference

### Core Modules

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Brain** | `jarvis/core/brain.py` | LLM inference coordinator | `Brain` |
| **Orchestrator** | `jarvis/core/orchestrator.py` | Main event loop & pipeline controller | `Orchestrator`, `TTSManager` |
| **Memory** | `jarvis/core/memory.py` | Core memory interface | `CoreMemory` |
| **Context** | `jarvis/core/context.py` | Conversation context assembly | `ContextAssembler` |

### Perception

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **STT** | `jarvis/perception/stt.py` | Speech-to-text conversion | `SpeechToText`, `STTResult` |
| **Vision** | `jarvis/perception/vision.py` | Image analysis & OCR | `VisionAnalyzer` |
| **Intent** | `jarvis/perception/intent_classifier.py` | User intent detection | `IntentClassifier` |
| **Wake Word** | `jarvis/perception/wake_word.py` | Voice activation | `WakeWordDetection` |

### Reasoning

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Planner** | `jarvis/reasoning/planner.py` | Multi-step plan generation | `TaskPlanner`, `ExecutionGraph`, `ExecutionStep` |
| **Critic** | `jarvis/reasoning/critic.py` | Plan quality assessment | `PlanCritic`, `CriticResult`, `CriticDecision` |
| **Reflector** | `jarvis/reasoning/reflector.py` | Learning from outcomes | `OutcomeReflector` |
| **Strategy** | `jarvis/reasoning/strategy_selector.py` | Task complexity classification | `StrategySelector` |

### Safety

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Input Filter** | `jarvis/safety/input_filter.py` | Content filtering | `InputFilter`, `FilterResult` |
| **Plan Validator** | `jarvis/safety/plan_validator.py` | Risk assessment | `PlanValidator`, `PlanValidationResult`, `PlanRiskLevel` |
| **Tool Guard** | `jarvis/safety/tool_guard.py` | Parameter validation | `ToolGuard` |
| **Audit Log** | `jarvis/safety/audit_log.py` | Security trail | `AuditLog` |

### Memory

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Manager** | `jarvis/memory/manager.py` | Unified memory coordinator | `MemoryManager`, `ProceduralMemory` |
| **Working** | `jarvis/memory/working.py` | Short-term memory | `WorkingMemory` |
| **Episodic** | `jarvis/memory/episodic.py` | Event storage | `EpisodicMemory` |
| **Semantic** | `jarvis/memory/semantic.py` | Knowledge base | `SemanticMemory` |

### Tools

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Registry** | `jarvis/tools/registry.py` | Tool discovery (singleton) | `ToolRegistry` |
| **Executor** | `jarvis/tools/executor.py` | Tool execution engine | `ToolExecutor` |
| **Base** | `jarvis/tools/base.py` | Abstract base class | `BaseTool`, `ToolResult` |

### Skills

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Base** | `jarvis/skills/base.py` | Abstract base class | `BaseSkill`, `SkillStep`, `Recovery` |
| **Registry** | `jarvis/skills/registry.py` | Skill discovery | `SkillsRegistry` |

### Execution

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Control Plane** | `jarvis/execution/control_plane.py` | Plan execution coordinator | `ControlPlane`, `PlanExecutionResult` |
| **Tool Runner** | `jarvis/execution/tool_runner.py` | Tool execution wrapper | `ToolRunner` |
| **Skill Runner** | `jarvis/execution/skill_runner.py` | Skill execution wrapper | `SkillRunner` |
| **Rollback** | `jarvis/execution/rollback.py` | Rollback management | `RollbackManager`, `RollbackAction` |

### Models

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Ollama Client** | `jarvis/models/ollama_client.py` | LLM API client | `OllamaClient`, `OllamaUnavailableError` |
| **Router** | `jarvis/models/router.py` | Model selection | `ModelRouter` |

### Monitoring

| Module | File | Purpose | Key Classes |
|--------|------|---------|-------------|
| **Ambient** | `jarvis/monitoring/ambient.py` | System monitoring | `AmbientMonitor`, `SystemState` |
| **Health Check** | `jarvis/monitoring/health_check.py` | Health utilities | `HealthChecker` |
| **Reliability** | `jarvis/monitoring/reliability.py` | Tool reliability tracking | `ReliabilityTracker` |

---

## Configuration

### Settings Module (`settings.py`)

All configuration goes through `settings.py` - **do not use `os.environ.get()` directly**.

Key settings categories:
- **LLM**: `OLLAMA_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_TEMPERATURE`, etc.
- **TTS**: `TTS_ENGINE`, `KOKORO_VOICE`, `TTS_ENABLED`
- **STT**: `STT_ENGINE`, `STT_LANGUAGE`, `WAKE_WORD`
- **Memory**: `MAX_HISTORY`, `WORKING_MEMORY_MAX_MESSAGES`
- **Monitoring**: `BATTERY_WARN_THRESHOLD`, `CPU_SPIKE_THRESHOLD`
- **Paths**: `LOG_DIR`, `DATA_DIR`, `NOTES_DIR`

### Environment Variables

Create a `.env` file in the project root:
```bash
OLLAMA_API_KEY=your_key_here
OLLAMA_MODEL=nemotron-3-nano:30b-cloud
TTS_ENABLED=true
WAKE_WORD="Hey Jarvis"
```

---

## Tool Categories

The system includes 58+ tools organized into 13 categories:

| Category | Location | Tools |
|----------|----------|-------|
| **Apps** | `jarvis/tools/apps/` | launcher, window management |
| **Audio** | `jarvis/tools/audio/` | volume control |
| **Data** | `jarvis/tools/data/` | calculator, notes, todo lists |
| **Files** | `jarvis/tools/files/` | create, delete, move, copy, search |
| **Input** | `jarvis/tools/input/` | clipboard, keyboard, mouse |
| **Network** | `jarvis/tools/network/` | connectivity checks, IP info |
| **Screen** | `jarvis/tools/screen/` | screenshots, vision analysis |
| **Scripts** | `jarvis/tools/scripts/` | dynamic Python execution |
| **Settings** | `jarvis/tools/settings/` | Windows settings |
| **System** | `jarvis/tools/system/` | power, display, system info |
| **Tasks** | `jarvis/tools/tasks/` | background tasks |
| **Time** | `jarvis/tools/time/` | clock, alarms, timers |
| **Web** | `jarvis/tools/web/` | browser automation, search |

---

## Adding New Components

### Adding a New Tool

1. Create file in appropriate category: `jarvis/tools/<category>/<tool_name>.py`
2. Inherit from `BaseTool` and implement:
   - `name`, `description`, `category`, `parameters`
   - `validate()`, `execute()`, `rollback()`
3. Update category `__init__.py` to export the class
4. Auto-discovered by `ToolRegistry`

### Adding a New Skill

1. Create file in `jarvis/skills/builtin/` or `jarvis/skills/learned/`
2. Inherit from `BaseSkill` and implement:
   - `get_system_prompt()`, `can_handle()`, `plan()`, `execute()`
3. Register in skill registry

### Adding a New Prompt

1. Create file in `jarvis/config/prompts/`
2. Define prompt template function
3. Import in orchestrator or relevant component

---

## Testing

### Run All Tests
```bash
pytest tests/ -v
```

### Run by Category
```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Safety tests
pytest tests/test_phase3_safety.py -v

# Memory tests
pytest tests/test_phase4_memory.py -v
```

---

## Running the System

### Standard Mode (Voice)
```bash
python jarvis.py
```

### Text-Only Mode
```bash
python jarvis.py --text-mode
```

### Debug Mode
```bash
python jarvis.py --debug
```

### Health Monitoring
```bash
python health_check_runner.py              # Continuous (60s interval)
python health_check_runner.py --once       # Single check
python health_check_runner.py -i 30        # 30-second interval
```

---

## Design Principles

### 1. Separation of Concerns
Each module has a single, well-defined responsibility:
- **Perception** handles input only
- **Brain** handles LLM inference only (proposes, never executes)
- **Safety** handles validation only
- **Execution** handles tool running only
- **Memory** handles persistence only

### 2. Deterministic Enforcement
The LLM is never in direct control of execution:
1. User input is classified for intent
2. LLM proposes tools based on intent
3. Safety layer validates the proposal
4. Only validated tools are executed
5. Results are fed back for agentic loops

### 3. Defense in Depth
Multiple safety layers protect against harmful operations:
1. Input filtering (before LLM)
2. Intent validation (after classification)
3. Plan review (before execution)
4. Parameter validation (per tool)
5. Audit logging (all operations)

### 4. Graceful Degradation
- Cloud/local LLM fallback
- Optional hardware (microphone, camera)
- Tool failures don't crash the system
- Comprehensive error handling

---

## Key Files Quick Reference

| File | Purpose |
|------|---------|
| `/workspace/jarvis.py` | Main entry point |
| `/workspace/settings.py` | Configuration (single source of truth) |
| `/workspace/jarvis/core/orchestrator.py` | Main event loop |
| `/workspace/jarvis/core/brain.py` | LLM coordination |
| `/workspace/jarvis/tools/registry.py` | Tool registry singleton |
| `/workspace/jarvis/memory/manager.py` | Memory coordinator |
| `/workspace/jarvis/safety/plan_validator.py` | Plan safety checks |
| `/workspace/jarvis/reasoning/planner.py` | Multi-step planning |
| `/workspace/jarvis/models/ollama_client.py` | LLM API client |

---

## Documentation

- **[README.md](README.md)** - Main documentation with setup and usage
- **[docs/PHASE3_COMPLETE.md](docs/PHASE3_COMPLETE.md)** - Safety layer integration
- **[docs/DYNAMIC_SCRIPTING_COMPLETE.md](docs/DYNAMIC_SCRIPTING_COMPLETE.md)** - Dynamic script execution
- **[docs/STT_ENHANCEMENTS.md](docs/STT_ENHANCEMENTS.md)** - Speech-to-text improvements
- **[docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md)** - Upgrade guide

---

## Dependencies

Key dependencies from `requirements.txt`:
- **LLM**: `ollama>=0.4.0`
- **STT**: `SpeechRecognition`, `webrtcvad`, `noisereduce`
- **TTS**: `edge-tts`, `pyttsx3`, `pydub`
- **Audio**: `sounddevice`, `pyaudio`, `soundfile`
- **Vision**: `Pillow`, `opencv-python`, `mss`
- **System**: `psutil`, `pynput`, `pyautogui`
- **Testing**: `pytest`, `pytest-mock`

---

*Generated: Project Analysis Complete*
