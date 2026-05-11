# JARVIS Performance Profiling Analysis

## Executive Summary

Performance profiling has been completed on the intent routing and classification system. The analysis reveals several key bottlenecks and optimization opportunities.

## Key Findings

### 1. Intent Router (`core/intent_router.py`) - **CRITICAL BOTTLENECK**
- **Total time**: 3.07 seconds for 100 calls (31ms per call)
- **Primary bottleneck**: Module imports consume **92% of execution time** (2.87s out of 3.14s)
  - `router_llm.py` import: 0.98s
  - `ollama_client.py` import: 0.97s  
  - `requests` library import: 0.96s
  - Python bytecode compilation: 0.93s

**Root Cause**: Lazy imports inside `_try_direct_dispatch()` are being re-executed on every call instead of being cached at module level.

### 2. Intent Classifier (`brain/intent_classifier.py`) - **MODERATE**
- **Total time**: 0.146 seconds for 100 calls (1.5ms per call)
- **Primary bottleneck**: Module initialization overhead (0.135s, 92% of time)
  - `skill_embedder.py` loading: 0.123s
  - `.env` file parsing: 0.080s

**Note**: Once initialized, actual classification is very fast (<0.01ms per call)

### 3. Cache Operations (`core/intent_learner.py`)
- Database operations are already optimized with batch queries
- SQLite connection management is efficient

### 4. Embedding Generation
- NumPy not available in current environment
- When available, cosine similarity calculations will be a consideration

## Recommended Optimizations (Priority Order)

### 🔴 HIGH PRIORITY - Import Caching

**File**: `/workspace/core/intent_router.py`

**Problem**: Functions like `_try_direct_dispatch()`, `_dispatch_volume_command()`, etc. perform lazy imports on EVERY call.

**Solution**: Move all lazy imports to module-level cached variables using a one-time initialization pattern.

```python
# Current (slow - imports every call):
def _try_direct_dispatch(text: str) -> Optional[Tuple[str, str]]:
    from tools.control_input import adjust_volume
    # ... rest of function

# Optimized (fast - import once):
_control_input_module = None

def _get_control_input():
    global _control_input_module
    if _control_input_module is None:
        from tools import control_input
        _control_input_module = control_input
    return _control_input_module

def _try_direct_dispatch(text: str) -> Optional[Tuple[str, str]]:
    control_input = _get_control_input()
    adjust_volume = control_input.adjust_volume
    # ... rest of function
```

**Expected Impact**: 80-90% reduction in router latency (from 31ms → 3-6ms per call)

---

### 🟡 MEDIUM PRIORITY - Pre-warm Critical Modules

**File**: `/workspace/core/intent_router.py` or startup script

**Problem**: First call to router suffers from cold-start import latency.

**Solution**: Add module pre-warming during system initialization:

```python
# At module load time, after imports:
def _prewarm_modules():
    """Pre-load critical modules to avoid cold-start latency."""
    try:
        # Trigger imports eagerly
        from tools import control_input
        from brain import router_llm
        from brain import ollama_client
        # Force actual function resolution
        _ = control_input.adjust_volume
        _ = router_llm.ask_llm_routing
    except Exception:
        pass  # Silent fail - will lazy-load later if needed

_prewarm_modules()
```

**Expected Impact**: Eliminates first-call latency spike

---

### 🟡 MEDIUM PRIORITY - Reduce .env Parsing Overhead

**File**: `/workspace/settings.py` or startup sequence

**Problem**: `.env` file is parsed multiple times (246 parse calls observed).

**Solution**: 
1. Cache loaded environment variables
2. Parse `.env` only once at application startup
3. Use `functools.lru_cache` for settings accessors

**Expected Impact**: 30-50% reduction in classifier initialization time

---

### 🟢 LOW PRIORITY - Embedding Optimization (Future)

When NumPy is available:
- Consider approximate nearest neighbor (ANN) search for large tool catalogs
- Increase LRU cache size for repeated queries
- Batch embedding computations when possible

---

## Implementation Plan

### Phase 1: Import Caching (Immediate - High Impact)
1. Audit all functions in `intent_router.py` with lazy imports
2. Implement module-level cached import helpers
3. Test performance improvement
4. Apply same pattern to other hot-path modules

### Phase 2: Startup Optimization (Short-term)
1. Add module pre-warming to initialization sequence
2. Optimize `.env` loading in `settings.py`
3. Profile cold-start vs warm performance

### Phase 3: Monitoring (Ongoing)
1. Add timing instrumentation to track real-world performance
2. Set up alerts for regression detection
3. Document baseline metrics for future comparison

## Metrics Summary

| Component | Current (per call) | Target (after optimization) | Improvement |
|-----------|-------------------|----------------------------|-------------|
| Intent Router | 31ms | 3-6ms | 80-90% |
| Intent Classifier (warm) | <0.01ms | <0.01ms | Already optimal |
| Classifier Init | 135ms | 70-90ms | 30-50% |
| Cache Lookup | ~1ms | ~1ms | Already optimal |

## Next Steps

1. ✅ Review this report
2. ⏳ Implement import caching in `intent_router.py`
3. ⏳ Re-run profiler to validate improvements
4. ⏳ Apply learnings to `tool_loop.py` and other hot paths
