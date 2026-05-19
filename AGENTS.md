# JARVIS — Agent Architecture

## Core agents

| Agent | Module | Model | Role |
|-------|--------|-------|------|
| **Jarvis** | `agents/jarvis.py` | `LLM_MODEL` | Conversation, reasoning, planning, decides when to act, emits `BATCH_TOOL_PLAN` |
| **Execution** | `agents/execution.py` | `EXECUTOR_MODEL` (validation) + Python runtime | Validates and runs tool plans, auto-splits perception/interaction, retries (up to 2/call) |

**Contract**: Jarvis → Execution: `BATCH_TOOL_PLAN` → Execution → Jarvis: `BATCH_TOOL_RESULT` or error.

## Sub-agents (via `delegate_to_subagent`)

Six specialists handle domain work. Each has its own prompt file in `prompts/` and agent class in `agents/sub_agents/`.

| Agent | Module | Prompt | Best for |
|-------|--------|--------|----------|
| **Research** | `agents/sub_agents/research_agent.py` | `prompts/research.yaml` | Web search, page fetching, fact-finding |
| **File** | `agents/sub_agents/file_agent.py` | `prompts/file.yaml` | File read/write/search/move/organize |
| **System** | `agents/sub_agents/system_agent.py` | `prompts/system.yaml` | System stats, app control, hardware settings |
| **Perception** | `agents/sub_agents/perception_agent.py` | `prompts/perception.yaml` | Screen analysis, vision queries, UI detection, OCR |
| **Interaction** | `agents/sub_agents/interaction_agent.py` | `prompts/interaction.yaml` | Mouse clicks, typing, scrolling, keyboard actions |
| **Memory** | `agents/sub_agents/memory_agent.py` | `prompts/memory.yaml` | Store/retrieve/search user preferences and context |

Sub-agents use `_tool_ok()` (`agents/base_agent.py:154`) to call tools through the safety executor. The `_tool_ok` method unwraps the safety envelope so sub-agents see raw tool keys (answer, elements, text, etc.) directly.

## Routing

- `core/orchestrator.py` → `agents.jarvis.run()` (direct, no shims)
- Fast-path: `core/classifier.py`, special commands (no LLM)
- Jarvis delegates to sub-agents via `delegate_to_subagent` tool

## Tool system

- 60 tools — `tools/schemas.json` (schemas) + `tools/adapters.py` (implementations)
- Safety funnel: `safety/executor.py` — wraps every tool result in `{success, message, data, timestamp}` envelope
- Verification: `verification/verifier.py` (injected into Execution)

## Key files

- `agents/jarvis.py` — planning ReAct loop
- `agents/execution.py` — batch/native execution
- `agents/base_agent.py` — `SubAgentBase` class with `_tool()` / `_tool_ok()` helpers
- `agents/sub_agent_registry.py` — agent registry with `inject_into_agents()` for wiring
- `core/orchestrator.py` — top-level orchestration, `_execute_wrapper()`
- `prompts/jarvis.yaml` — Jarvis system prompt (includes subagent roster, tool hierarchy)
- `prompts/executor.yaml` — execution validator prompt
- `brain/ollama_client.py` — LLM client with retry, timeout, fallback to mock

## Memory and context

- `LOAD_CONVERSATION_HISTORY` (default `true`): episodic command/response pairs merge into Jarvis turns via `memory/conversation_history.py`.
- `memory_context`: preferences + frequent commands from `MemoryManager.get_context_summary()`.
- In-session `orchestrator._history` deque is merged with persisted session episodes (no duplicate tail).

## Lean Jarvis LLM payload

- `JARVIS_ATTACH_TOOL_SCHEMAS` (default `false`): no OpenAI `tools` array on Jarvis calls; tool names/descriptions stay in `prompts/jarvis.yaml`.
- Set `JARVIS_ATTACH_TOOL_SCHEMAS=true` only for legacy native `tool_calls` experiments.

## Execution behavior

- Validates every batch call before run (`validate_tool_call`)
- Retries failed calls up to 2× before reporting to Jarvis (sub-agent retries are separate)
- Auto-splits mixed perception + interaction plans (perception first; Jarvis plans interaction second)
- Fail-loop guard: same tool fails twice → block further retries

## Settings for vision

- `VISION_TIMEOUT` (env `OLLAMA_VISION_TIMEOUT`, default `60`): shorter timeout for cloud vision queries to fail fast on 524 errors.
- `LLM_VISION_MODEL` (env `OLLAMA_VISION_MODEL`, default `gemma3:27b-cloud`): model used by `vision_query()`.
- ollama_client retries 3× with exponential backoff (1s, 2s, 4s) before falling back to mock LLM.

## Legacy (removed)

- `brain/tool_loop.py`, `brain/tool_validator.py`, `brain/executor_agent.py` — removed; imports point directly to `agents.jarvis` / `agents.execution`
