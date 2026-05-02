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

## Current Limitations

1. **Platform Specificity** — Tools are Windows-specific (PowerShell execution)
2. **External LLM Dependency** — Requires Ollama cloud API; no local fallback
3. **Audio Hardware** — Full voice mode requires microphone
4. **Multi-step Complexity** — Complex sequences may fail mid-execution
5. **Parameter Recovery** — Limited recovery from subtle parameter errors

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
