# JARVIS — Local Desktop AI Agent

A desktop AI agent system that uses LLM inference to generate tool calls, with deterministic validation and execution layers. The system orchestrates voice input through intent classification to PC control actions.

**Note:** This is a development/testing version. The full system requires audio hardware and an external LLM API (Ollama cloud).

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        jarvis.py                              │
│                (orchestration + intent routing)            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   intent_classifier.py
                    │ (classifies user intent)
                    └─────────┬─────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                    │
    ┌──────▼──────┐    ┌───────▼─────┐    ┌───────▼─────┐
    │  brain.py   │    │control_plane│    │  stt.py    │
    │(LLM only)   │    │(validation) │    │  (input)   │
    └──────┬─────┘    └──────┬──────┘    └────────────┘
          │                 │
          │    ┌────────────▼────────────┐
          │    │      pc_control.py     │
          │    │     (execution only)    │
          │    └────────────────────────┘
          │                 │
          │    ┌────────────▼────────────┐
          │    │      tools.py           │
          │    │  (tool definitions)    │
          │    └────────────────────────┘
          │
    ┌─────▼──────┐
    │  tts.py     │
    │ (output)   │
    └────────────┘
```

## Execution Pipeline

```
user input → brain.py (LLM proposes tool) → intent_classifier.py (validate intent)
         → control_plane.py (validate parameters) → pc_control.py (execute)
         → result fed back to brain.py (agentic loop)
```

1. **brain.py** — Receives user text, returns text + tool_calls. LLM is proposer only, never executes.
2. **intent_classifier.py** — Classifies user intent to filter/validate LLM tool proposals.
3. **control_plane.py** — Validates tool parameters before execution. No execution here.
4. **pc_control.py** — Executes validated commands via PowerShell/subprocess. Returns structured results.

## Key Features

### Testing
- **stt_injector.py** — Text injection harness bypassing audio pipeline. For deterministic testing without microphone/wake word/TTS.
  ```bash
  python stt_injector.py            # interactive
  python stt_injector.py --test     # predefined test sequence
  ```

### Tool Execution
- LLM generates tool calls, system validates and executes
- Multi-step tool chains supported (e.g., open app + search web)
- Tool reliability tracking with success/failure decay

### Intent Classification
- Classifies user intent with confidence scores
- Filters LLM tool proposals against classified intent
- Safe passthrough for read-only queries (get_time, system_health, get_ip)

### Safety Model

**Command Filtering:**
- `_SAFE_PASSTHROUGH_TOOLS` — Read-only tools that bypass intent filtering (cannot cause harm)
- `_CHAT_ONLY_PATTERNS` — Phrases routed to conversational mode (no tool execution)
- `_TOOL_PATTERNS` — Phrases that trigger tool mode

**Destructive Action Prevention:**
- `control_plane.py` validates parameters before execution
- Intent mismatch handling: if LLM proposes tool that doesn't match classified intent, it's filtered out
- Abort listener for user interruption during long operations

**Validation Flow:**
```
LLM tool_call → intent alignment check → parameter validation → execution
                    │                         │
                    │                    ✗ rejected
                    │                         │
                 ✗ filtered               ✓ executed
```

## Current Limitations

1. **Intent classifier mismatch** — The LLM may propose valid tools that the intent classifier rejects. This is an active debugging area.

2. **Parameter recovery** — If the LLM generates a tool with incorrect parameters, the system lacks robust recovery. Validation catches obvious errors, but subtle parameter issues may slip through.

3. **External LLM dependency** — System requires Ollama cloud API. Network issues or timeout can interrupt operation. No local fallback model included.

4. **Multi-step execution limits** — While multi-tool chains are supported, complex sequences may fail mid-execution. The agentic loop supports retries but has a failure threshold.

5. **Platform-specific tools** — Tools are Windows-specific (PowerShell execution). Cross-platform support is not implemented.

6. **Audio hardware dependency** — Requires microphone for voice input. Testing harness (stt_injector.py) exists but full voice mode needs audio stack.

## Setup

### Requirements
- Python 3.10+
- Windows with PowerShell
- Internet access for Ollama API

### Installation
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables
Set in `.env` or environment:
```
OLLAMA_API_KEY=your_key_here
```

### Running
```powershell
# Full system (requires audio hardware)
python jarvis.py

# Text injection testing only
python stt_injector.py
python stt_injector.py --test
```

## File Inventory

| File | Purpose |
|------|---------|
| `jarvis.py` | Main orchestration loop |
| `brain.py` | LLM inference only |
| `control_plane.py` | Tool call validation |
| `pc_control.py` | Command execution |
| `intent_classifier.py` | Intent classification |
| `stt.py` | Speech-to-text (audio input) |
| `tts.py` | Text-to-speech (audio output) |
| `wake_word.py` | Wake word detection |
| `tools.py` | Tool schema definitions |
| `config.py` | Configuration |
| `user_profile.py` | User preferences |
| `stt_injector.py` | Testing harness |

## Design Philosophy

### Separation of Concerns
- **brain.py** — LLM inference only. Proposes tools, doesn't execute.
- **control_plane.py** — Validation only. Doesn't execute.
- **pc_control.py** — Execution only. No intelligence.
- **jarvis.py** — Orchestration only. Routes and coordinates.

### Deterministic Enforcement
The system enforces that the LLM is never in direct control of execution. Even if the LLM proposes a tool:
1. Intent must be classified
2. Parameters must validate
3. System executes, not the LLM

### Intent as Gate
- Intent classification is the gatekeeper
- LLM tool proposals must align with classified intent
- Safe tools bypass this gate (read-only queries)

## Debugging

Logs output to console and `logs/` directory. Key log markers:
- `[JARVIS][INTENT]` — Intent classification decisions
- `[JARVIS][FILTER]` — Tool filtering decisions
- `[JARVIS][CONFIDENCE]` — Confidence scoring
- `[JARVIS][SELECT]` — Tool selection (chains, conflicts)

## License

MIT