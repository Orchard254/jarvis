# JARVIS Documentation

## Current Architecture

JARVIS uses **6 consolidated tools** (screen, input, window, browser, exec, memory).
See `AGENTS.md` at the repo root for the tool selection guide.

## Active Docs

| Doc | What It Covers |
|-----|----------------|
| `PENDING_TOOLS.md` | Tool implementations and status |
| `SAFETY_AUDIT_SUMMARY.md` | Safety policy calibration |
| `OPTIMIZATION_SUMMARY.md` | DB pooling, embedding cache |
| `TASK_EXECUTION_IMPROVEMENT_AUDIT.md` | 15 improvement suggestions (partially implemented) |

## Archived Docs

Phase implementation docs have been moved to `docs/archive/`. These were written
during development and some reference components that have since been removed or
consolidated (e.g., intent router, 8-tool system, speak/system tools).

| Doc | Phase |
|-----|-------|
| `archive/PHASE2_IMPLEMENTATION.md` | Reliability & Recovery |
| `archive/PHASE3_IMPLEMENTATION.md` | Learning & Scalability |
| `archive/PHASE4_IMPLEMENTATION.md` | UX & Observability |
| `archive/PHASE5_IMPLEMENTATION.md` | Advanced Autonomy |
| `archive/PHASE5B_IMPLEMENTATION.md` | Reliability & Resilience |
| `archive/TIER1_IMPLEMENTATION_SUMMARY.md` | Tool caching, skill search |
| `archive/TIER2_IMPLEMENTATION_SUMMARY.md` | Cross-platform, long-term memory |
| `archive/TIER3_IMPLEMENTATION_SUMMARY.md` | Multi-agent system |
| `archive/TTS_WINDOWS_FIX.md` | Windows audio fix |
