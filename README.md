# JARVIS — Autonomous Windows Desktop AI Agent

An autonomous AI agent that controls your Windows PC through voice commands and text input. Powered by Ollama LLMs with a ReAct-style tool loop, JARVIS can launch apps, browse the web, manage files, write code, and remember things across sessions.

## Architecture

```
User (voice/text)
    │
    ▼
┌──────────────┐     ┌──────────────┐
│  Perception  │     │    Safety    │
│  (STT, VAD,  │     │ (audit log,  │
│  wake word)  │     │  guards,     │
│              │     │  gates)      │
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌─────────────────────────────────────┐
│           Orchestrator              │
│  (planner → tool loop → verifier)  │
└──────────────┬──────────────────────┘
               │
       ┌───────┼───────┬───────┬───────┬───────┐
       ▼       ▼       ▼       ▼       ▼       ▼
   screen   input   window  browser  exec   memory
```

### 6 Core Tools

| Tool | Actions | Purpose |
|------|---------|---------|
| `screen` | capture, find, tree, query, ocr | Perception — see the screen, find UI elements, read text |
| `input` | click, type, hotkey, scroll, drag | Interaction — mouse and keyboard control |
| `window` | open, close, focus, list, minimize, maximize, state | App/window management + live desktop state |
| `browser` | navigate, click, type, read_page, screenshot, scroll | Web browsing via Playwright |
| `exec` | run, read, write | Code execution (Python/PowerShell) + file I/O |
| `memory` | store, recall, search | Persistent key-value memory with semantic search |

### Key Modules

- **brain/** — LLM client, prompt builder, context manager, ReAct tool loop
- **core/** — Orchestrator, circuit breaker, health checks, feedback collection
- **agents/** — Multi-agent system (planner, coder, executor, supervisor)
- **memory/** — Episodic (SQLite) + long-term semantic memory (ChromaDB)
- **safety/** — Audit logging, confidence gates, path guards, tool guards
- **skills/** — Learnable skill store with embedding-based retrieval
- **perception/** — Voice activity detection, wake word, speech-to-text
- **indexer/** — PC file and app indexing for local search
- **autonomous/** — Task queue, scheduler, ambient monitoring

## Setup

### Prerequisites

- Python 3.8+
- Windows 10/11 (some tools use Win32 APIs)
- [Ollama](https://ollama.com/) account for cloud models, or a local Ollama instance

### Installation

```bash
# Clone the repository
git clone https://github.com/Orchard254/jarvis.git
cd jarvis

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy the environment config
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac
```

### Configuration

Edit `.env` with your settings:

```ini
# Required: Ollama API key (get from https://ollama.com/settings/api-keys)
OLLAMA_API_KEY=your_key_here

# LLM model (cloud or local)
OLLAMA_MODEL=gpt-oss:120b-cloud
OLLAMA_VISION_MODEL=gemma3:27b-cloud

# Mode: cloud / local / auto
OLLAMA_MODE=auto
```

See `.env.example` for the full list of configuration options including audio, safety, voice, and model settings.

### Running

```bash
python jarvis.py
```

JARVIS starts in CLI mode. Type commands or say them aloud (if voice is enabled).

## Usage Examples

```
> open notepad and type hello world
> search the web for python tutorials
> take a screenshot
> remember that my favorite color is blue
> what's running on my desktop right now?
> close chrome
```

## Project Structure

```
jarvis/
├── jarvis.py              # Entry point
├── settings.py            # All configuration (loads from .env)
├── tools/                 # 6 core tools + primitives
│   ├── __init__.py        # Tool registry + JSON schemas
│   ├── screen.py          # Perception facade
│   ├── input.py           # Mouse/keyboard facade
│   ├── window.py          # Window management facade
│   ├── browser.py         # Playwright web automation
│   ├── exec.py            # Code execution facade
│   ├── mem.py             # Memory facade
│   ├── capture_screen.py  # Screenshot primitive
│   ├── control_input.py   # Input primitive (pyautogui)
│   ├── control_window.py  # Window primitive (Win32)
│   └── ...                # Other primitives
├── brain/                 # LLM integration
│   ├── ollama_client.py   # API client
│   ├── prompt_builder.py  # System prompt construction
│   ├── tool_loop.py       # ReAct loop
│   └── context_manager.py # Token budget management
├── core/                  # Orchestration
│   ├── orchestrator.py    # Main routing gate
│   ├── circuit_breaker.py # Failure resilience
│   └── health_check.py    # Startup diagnostics
├── agents/                # Multi-agent system
├── memory/                # Episodic + semantic memory
├── safety/                # Guardrails and audit
├── skills/                # Learnable skill store
├── perception/            # Voice I/O pipeline
├── indexer/               # PC file/app indexing
├── autonomous/            # Background task automation
├── verification/          # Action verification
└── docs/                  # Implementation docs
```

## Testing

```bash
# Syntax and schema validation
python test_syntax.py

# Settings validation
python test_settings.py

# Run all tests
pytest tests/
```

## License

MIT
