# JARVIS Bug Fix Plan

## Summary
20 bugs identified (3 critical, 4 high, 8 medium, 5 low). All patches will be applied to the extracted codebase at `jarvis-analysis-new/jarvis/`.

## Execution Order
Patches are grouped by file to minimize conflicts. Files are ordered by dependency (foundational first).

---

### Phase 1: Critical & High (Security/Correctness)

| # | Bug | File(s) | Fix |
|---|-----|---------|-----|
| 1 | ToolGuard never receives registry | `core/orchestrator.py` | Pass registry to ToolGuard in `__init__` |
| 2 | Dynamic tool gen runs code in-process | `core/react_agent.py` | Execute generated code in subprocess, not `exec_module()` |
| 3 | Vault plaintext fallback | `security/vault.py` | Encrypt local vault with Fernet (base64-key from user machine ID) |
| 4 | ToolRegistry singleton conflict | `tools/registry.py` + `tools/registry_dynamic.py` | Merge into single registry; remove duplicate |
| 5 | Validation inconsistency | `tools/scripts/runner.py` + `safety/tool_guard.py` | Consolidate patterns; use ToolGuard as single source of truth |
| 6 | Hash collision in loop prevention | `core/orchestrator.py` | Use `hashlib.sha256` instead of `hash()` |
| 7 | `from settings import` breaks as package | `models/ollama_client.py` | Move settings import inside methods with lazy loading |

### Phase 2: Medium (Reliability/Logic)

| # | Bug | File(s) | Fix |
|---|-----|---------|-----|
| 8 | Thread-unsafe singletons | `safety/tool_guard.py`, `tools/registry.py` | Add threading.Lock |
| 9 | Idle monitor never tracks real idle | `core/orchestrator.py` | Hook into `last_activity` from process_command |
| 10 | Timer monitor is no-op | `core/orchestrator.py` | Remove thread or add actual timer logic |
| 11 | Protected path regex too broad | `safety/tool_guard.py` | Scope patterns to system directories |
| 12 | Streaming response parsing fragile | `models/ollama_client.py` | Add try/except per-line, dedup content accumulation |
| 13 | ReAct history unbounded | `core/react_agent.py` | Prune history to max token budget per iteration |
| 14 | `_contains_dangerous_content` vs `_validate_run_python` mismatch | `safety/tool_guard.py` | Unify dangerous pattern lists |
| 15 | `open_app` blocks easily bypassed | `safety/tool_guard.py` | Add cross-tool validation in orchestrator |

### Phase 3: Low (Code Quality)

| # | Bug | File(s) | Fix |
|---|-----|---------|-----|
| 16 | Nested parens in TOOL regex | `core/orchestrator.py` | Use non-greedy or balanced paren matching |
| 17 | Massive code duplication | `core/orchestrator.py` | Extract shared predictive planning method |
| 18 | Tool list truncated to 50 | `core/orchestrator.py` | Remove limit or make configurable |
| 19 | Test file committed to main root | Root `test_dynamic_execution.py` | Move to `tests/` and add to .gitignore |
| 20 | `pyc` files tracked | `.gitignore` | Ensure `__pycache__/` and `*.pyc` are excluded |

---

## Progress
- [ ] Phase 1: Critical & High
- [ ] Phase 2: Medium
- [ ] Phase 3: Low
