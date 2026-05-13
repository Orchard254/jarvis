# JARVIS Documentation

## Current Implementation Docs

| Doc | What It Covers | Status |
|-----|----------------|--------|
| `PHASE2_IMPLEMENTATION.md` | Reliability & Recovery (retry, circuit breaker, checkpointing) | Core concepts built into executor_pool.py |
| `PHASE3_IMPLEMENTATION.md` | Learning & Scalability (feedback_loop, skill_versioning, distributed_queue) | Modules exist, not wired |
| `PHASE4_IMPLEMENTATION.md` | UX & Observability (streaming, progress, observability) | Modules exist, WIRED into executor_pool |
| `PHASE5_IMPLEMENTATION.md` | Advanced Autonomy (self-reflection, prompt optimization, skill synthesis, multi-agent) | Modules exist, not wired (over-engineered for current usage) |
| `PHASE5B_IMPLEMENTATION.md` | Reliability & Resilience (parallel_executor, checkpoint_manager, circuit_breaker, feedback_collector) | circuit_breaker WIRED, rest exist not wired |
| `TIER1_IMPLEMENTATION_SUMMARY.md` | Tool caching, skill search, approval gate | Implemented and integrated |
| `TIER2_IMPLEMENTATION_SUMMARY.md` | Cross-platform abstraction, long-term memory (RAG) | long_term_memory now WIRED into orchestrator |
| `TIER3_IMPLEMENTATION_SUMMARY.md` | Multi-agent system (planner, coder, executor, supervisor) | Agents exist and integrated |
| `OPTIMIZATION_SUMMARY.md` | DB pooling, embedding cache | Implemented |
| `TTS_WINDOWS_FIX.md` | Windows audio configuration | Applied |
| `PENDING_TOOLS.md` | Tool implementations (ask_user, time_calendar, listen, etc.) | All implemented |
| `SAFETY_AUDIT_SUMMARY.md` | Safety policy calibration | Applied |
| `TASK_EXECUTION_IMPROVEMENT_AUDIT.md` | 15 improvement suggestions | Partially implemented |

## Archive (`archive/`)

Stale docs referencing code that has been removed or superseded:

| Doc | Why Archived |
|-----|-------------|
| `INTENT_ROUTING_AUDIT.md` | Entirely about the now-deleted intent routing system |
| `INTENT_REMOVAL_PLAN.md` | Plan was already executed (routing files deleted) |
| `INTENT_REMOVAL_SUMMARY.md` | Summary of completed removal |
| `PROFILING_ANALYSIS.md` | Profiling of deleted intent_router.py |
| `PHASE1_IMPLEMENTATION.md` | References deleted direct_dispatcher.py, intent_router.py |
| `ARCHITECTURE_SUMMARY.md` | Architecture diagram references deleted components |
| `AI_AGENT_FEATURE_AUDIT.md` | References deleted routing files |
| `MULTITASKING_AUDIT.md` | References deleted direct_dispatcher |
