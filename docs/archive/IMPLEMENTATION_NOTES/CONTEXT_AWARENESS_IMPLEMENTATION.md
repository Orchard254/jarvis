# Context Awareness Implementation - Complete ✅

## Overview
Enhanced JARVIS with context awareness in the predictive planning stage, enabling the LLM to see recent successful results and failed actions before generating execution plans.

## Changes Made

### 1. `/workspace/jarvis/core/orchestrator.py`

#### Added Context Tracking Attributes (Lines 210-214)
```python
# Context awareness - track recent results and failed actions
self._recent_results: List[Dict[str, Any]] = []  # Last 20 successful results
self._failed_actions: List[Dict[str, Any]] = []  # Last 10 failed actions
self._max_recent_results = 20
self._max_failed_actions = 10
```

#### Updated Predictive Planner Call (Lines 597-602)
```python
plan = self.predictive_planner.generate_plan(
    command, 
    tools_dict,
    recent_results=self._recent_results,
    failed_actions=self._failed_actions
)
```

#### Added Result Tracking After Execution (Lines 653-678)
```python
# Update context awareness tracking with results
for step in executed_plan.steps:
    if step.status.value == 'completed' and step.result:
        # Store successful result
        result_entry = {
            'tool': step.tool_name,
            'command': command[:100],
            'result': str(step.result.output if hasattr(step.result, 'output') else step.result),
            'timestamp': time.time()
        }
        self._recent_results.append(result_entry)
        # Keep only last N results
        if len(self._recent_results) > self._max_recent_results:
            self._recent_results.pop(0)
    elif step.status.value in ['failed', 'error'] and step.error_message:
        # Store failed action
        failure_entry = {
            'tool': step.tool_name,
            'command': command[:100],
            'error': step.error_message,
            'timestamp': time.time()
        }
        self._failed_actions.append(failure_entry)
        # Keep only last N failures
        if len(self._failed_actions) > self._max_failed_actions:
            self._failed_actions.pop(0)
```

### 2. `/workspace/jarvis/core/predictive_planner.py`

#### Updated PLAN_PROMPT (Lines 17-50)
Added two new rules and context section placeholder:
- **Rule 6**: CHECK RECENT RESULTS - If answer is already available, respond directly
- **Rule 7**: AVOID FAILED ACTIONS - DO NOT retry tools that failed with same parameters
- **Rule 8**: OUTPUT ONLY JSON (renumbered)
- **{context_section}**: Placeholder for dynamic context injection

#### Updated generate_plan() Signature (Lines 56-58)
```python
def generate_plan(self, user_request: str, available_tools: Dict[str, Any], 
                  recent_results: Optional[List[Dict[str, Any]]] = None,
                  failed_actions: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict]:
```

#### Added Context Building Logic (Lines 67-91)
```python
# Build context section with recent results and failed actions
context_section = ""
if recent_results or failed_actions:
    context_parts = []
    
    if recent_results:
        # Show last 5 successful results
        recent = recent_results[-5:] if len(recent_results) > 5 else recent_results
        results_text = "\n".join([
            f"  - {r['tool']} returned: {r['result'][:150]}..." if len(r['result']) > 150 else f"  - {r['tool']} returned: {r['result']}"
            for r in recent
        ])
        context_parts.append(f"[RECENT SUCCESSFUL RESULTS]:\n{results_text}")
    
    if failed_actions:
        # Show last 5 failed actions
        failed = failed_actions[-5:] if len(failed_actions) > 5 else failed_actions
        failed_text = "\n".join([
            f"  - {f['tool']} failed: {f['error'][:150]}... [DO NOT retry]" if len(f['error']) > 150 else f"  - {f['tool']} failed: {f['error']} [DO NOT retry]"
            for f in failed
        ])
        context_parts.append(f"[FAILED ACTIONS - AVOID]:\n{failed_text}")
    
    if context_parts:
        context_section = "\n\n".join(context_parts) + "\n\n"
```

#### Updated Prompt Formatting (Lines 93-97)
```python
prompt = PLAN_PROMPT.format(
    context_section=context_section,
    tools_description=tools_desc,
    user_request=user_request
)
```

## Expected Behavior

### Scenario 1: Answer Already Available
**User**: "What's my IP country?" → System runs `run_command` → Returns "Kenya"
**User**: "So which country am I from?"
- **Before**: Would re-execute IP geolocation tools
- **After**: LLM sees `[RECENT SUCCESSFUL RESULTS]: run_command returned: {...country_name: Kenya...}` and responds "You're from Kenya!"

### Scenario 2: Failed Action Avoidance
**User**: "Read file.txt" → Fails with "path parameter is required"
**User**: "Read file.txt again"
- **Before**: Would retry the same failing action
- **After**: LLM sees `[FAILED ACTIONS - AVOID]: read_file failed: path parameter is required [DO NOT retry]` and either asks for the path or suggests an alternative

## Defense-in-Depth Architecture

The system now has **two layers** of context awareness:

1. **General Context Assembly** (`jarvis/core/context.py`)
   - Tracks recent facts, procedural memories, conversation history
   - Injected into all LLM calls via system prompt

2. **Predictive Planning Context** (`jarvis/core/predictive_planner.py`)
   - Tracks recent tool execution results and failures
   - Injected specifically into planning prompts
   - Enables intelligent decision-making BEFORE tool execution

## Testing

Run the following test sequence:
```bash
python jarvis.py
# Then type:
1. "What's my battery status?"  # Runs tool, gets result
2. "Am I charging?"             # Should use cached result
3. "Open notepad"               # Opens successfully
4. "Close notepad"              # Closes successfully  
5. "Read file without path"     # Will fail
6. "Read file again"            # Should avoid same failure
```

## Files Modified
- `/workspace/jarvis/core/orchestrator.py` (+33 lines)
- `/workspace/jarvis/core/predictive_planner.py` (+34 lines)

## Backward Compatibility
✅ All changes are backward compatible
✅ Optional parameters default to None
✅ Existing functionality preserved
✅ No breaking changes to API
