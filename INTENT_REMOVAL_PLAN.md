# Intent Router Removal Plan

## Decision
Remove the entire intent routing system in favor of direct LLM tool calling. Modern LLMs (GPT-4o, Claude 3.5, etc.) are capable enough to handle simple, complex, and ambiguous commands without a multi-tier routing cascade.

## Philosophy
**Trade-off accepted**: Prefer occasional LLM hallucination over 1,853 lines of routing complexity. The benefits of simplicity outweigh the latency optimization for most use cases.

## Files to Remove
1. `/workspace/core/intent_router.py` (535 lines)
2. `/workspace/core/direct_dispatcher.py` (105 lines)
3. `/workspace/core/intent_learner.py` (384 lines)
4. `/workspace/brain/intent_classifier.py` (544 lines)
5. `/workspace/brain/router_llm.py` (285 lines)

**Total: ~1,853 lines of code removed**

## Files to Modify

### 1. `/workspace/core/orchestrator.py`
**Changes needed:**
- Remove import: `from core.intent_router import route as intent_router_route`
- Remove lines 287-343 (entire intent routing block including direct_dispatch and social_chat handling)
- Remove `_routing_source` variable tracking (lines 347, 573, 619)
- Remove intent learner feedback loop (lines 602-622)
- Remove classifier warmup thread (lines 113-125)
- Simplify flow: user input → skill check → direct to tool_loop

**New simplified flow:**
```python
# After skill check fails, go directly to tool_loop
result = tool_loop_run(
    user_input=clean_input,
    history=self._history[-TOOL_LOOP_HISTORY_MESSAGES:],
    memory=self._memory,
    # ... other params
)
```

### 2. `/workspace/profile_performance.py`
- Remove intent router profiling benchmarks

### 3. `/workspace/tests/test_orchestrator.py`
- Update tests to not expect routing behavior

### 4. `/workspace/memory/semantic.py`
- Check if any intent-related methods need removal

### 5. `/workspace/brain/prompt_builder.py`
- Remove any routing-specific prompt logic

## What We Lose
1. **Latency optimization**: Volume/brightness commands will take 2-5s instead of <100ms
2. **Learned behavior**: No caching of successful tool patterns
3. **Social chat detection**: LLM might occasionally try to use tools for greetings
4. **Schema ordering optimization**: All tool schemas sent in default order every time

## What We Gain
1. **Simplicity**: ~1,800 fewer lines of code
2. **Better context**: Single LLM call has full conversation history
3. **Natural ambiguity handling**: LLM handles edge cases better than regex + classifiers
4. **Easier maintenance**: No routing bugs, no cache invalidation issues
5. **Unified decision making**: One brain makes all decisions with full context

## Migration Steps

### Phase 1: Prepare orchestrator
1. Create backup of current orchestrator
2. Remove intent router import and usage
3. Route all commands directly to tool_loop
4. Handle social/chat detection within tool_loop via LLM response

### Phase 2: Remove routing files
1. Delete the 5 routing-related files
2. Update imports in remaining files
3. Run tests to verify functionality

### Phase 3: Optimize single LLM call
1. Ensure tool_loop uses efficient prompting
2. Add temperature=0 for deterministic tool selection
3. Consider JSON mode for structured output
4. Add retry logic for hallucinated tool calls

## Risk Mitigation

### For Hallucinated Tool Calls:
- Use tool validation layer (already exists in safety/executor.py)
- Add confidence scoring to tool arguments
- Implement "ask before executing" for high-risk tools

### For Lost Performance:
- Keep ONE fast path: direct hardware control via OS-level hooks
- Or accept 2-5s latency for all commands as trade-off

### For Social Chat Wasting Tool Calls:
- Add system prompt instruction: "If user is greeting or chatting, respond conversationally without using tools"
- Post-process LLM response: if no tool called, return text directly

## Recommended Implementation Order

1. ✅ Audit complete (this document)
2. ⏳ Modify orchestrator.py to bypass router
3. ⏳ Test basic functionality
4. ⏳ Remove routing files
5. ⏳ Clean up remaining references
6. ⏳ Run full test suite
7. ⏳ Performance benchmarking

## Alternative: Hybrid Approach

If you want to keep SOME optimization:
- Keep only `direct_dispatcher.py` for volume/brightness (105 lines)
- Remove everything else (1,748 lines)
- This gives you 80% of the benefit with 6% of the code

Let me know which approach you prefer!
