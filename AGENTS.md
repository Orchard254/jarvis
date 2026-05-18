# JARVIS — Agent Session Context

## Architecture
- **Two agents**: Director (CEO, `gpt-oss:120b-cloud`) decides and summarises; Execution (Ops, `nemotron-3-nano:30b-cloud`) acts.
- `agents/director.py` — Single-pass CEO agent with one `delegate` tool (native function-calling). Decides whether a task needs tools or is pure chat.
- `agents/execution.py` — Ops agent using native tool-calling (56 tool schemas). No conversation, no expanders, no hardcoded Python sequences.
- `core/orchestrator.py` — Routes: admin fast-path → Director → (if delegate) → Execution → Director summary.

## Tool System
- **56 registered tools** across 4 levels (hierarchy in `prompts/jarvis.yaml`).
- Single source of truth: `tools/schemas.json` — validated against adapter functions at startup.
- Output envelope: `{success, message, data, timestamp}` via `safety/executor.py`.
- Verification with polling (6×0.5s) for app launches in `verification/verifier.py`.

## Known Fixes (don't re-break)
1. **open_app**: `_resolve_exe()` falls back to `shutil.which()`. Verifier strips prefixes (`"launched "`, `"focused "`) from app_name. Three-attempt strategy: `os.startfile()` → `shutil.which()` → DB path.
2. **vision_query**: No consent gate. `image_b64` stripped from nested `data` dict in tool_loop before sending to LLM.
3. **press_keys**: Single-char keys (e.g., `"/"`) use `pyautogui.write()` — `hotkey()` only accepts named keys (`ctrl`, `shift`, etc.).
4. **click / move_mouse**: Temporarily disable `pyautogui.FAILSAFE` during execution (screen-corner coordinates are valid targets for vision-guided automation).
5. **LLM 400 errors**: Caused by `image_b64` embedded in executor's `data` dict not being stripped before sending tool results to LLM.
6. **System prompt must always be included** — LLM API calls are stateless. History from memory is NOT loaded at startup.
7. **list_installed_apps**: Includes apps with null `path` (previously dropped silently).

## Key Files
- `core/orchestrator.py` — Main routing, lazy_init, Director→Execution→Director flow
- `agents/director.py` — CEO agent (JarvisAgent.process, JarvisAgent.summarize)
- `agents/execution.py` — Ops agent (ExecutionAgent.execute_task)
- `brain/prompt_builder.py` — Prompt construction, 60s cache for Director prompt
- `tools/adapters.py` — All tool adapter functions (56 tools)
- `tools/schemas.json` — Tool definitions
- `safety/executor.py` — Tool output envelope, try/except wrapper
- `verification/verifier.py` — OS-level state verification with polling
- `prompts/jarvis.yaml` — Director system prompt (1121 chars)
- `prompts/executor.yaml` — Execution system prompt (~3896 chars)
- `indexer/db/pc_index.db` — PC app index (1,237 apps, 904 null exe_path)

## Important Behaviors
- Background threads (indexer, scheduler) are deferred to `_lazy_init()` — start on first `handle()` call, not at import time.
- Director receives `tools=[delegate_tool]`; Execution receives `tools=TOOL_SCHEMAS` (56 tools).
- Chat-only inputs: 1 LLM call (Director). Action tasks: 3 calls max (Director → Execution → Director).
- Memory is read-only (for system state, app index). No episode history loaded into LLM context.
- Wait tool is state-aware: `_execute_wrapper` checks SystemState before calling wait (skips polling if already satisfied).
- Admin fast-path handles: `summary`, `skills_status`, `status`, `stop`, `shutdown`, `help`, `history`, `clear` — no LLM call needed.
- Structured logging captures: tool_call, tool_retry, guard_triggered, loop_iteration, loop_complete.
