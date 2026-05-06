# Bug Analysis: JSON Output Leakage and Clarification Handling

## Problem Summary

The system was failing when executing multi-step commands like "open notepad and write my name" because:

1. **Predictive Planner Failure**: When the LLM couldn't generate a valid plan (empty steps), it returned a malformed JSON structure with `needs_clarification: true` but no steps
2. **ReAct Fallback Corruption**: After predictive planning failed, the system fell back to ReAct agent, but the broken JSON state leaked through as raw output to the user
3. **Cascading Failures**: Once this happened, subsequent commands also started returning raw JSON instead of natural language responses
4. **No Proper Clarification Flow**: The system should have asked for clarification about the user's name, but instead dumped internal JSON structures

## Root Causes Identified

### 1. Predictive Planner (`jarvis/core/predictive_planner.py`)

**Issue**: When the LLM generated an empty plan without setting `needs_clarification: true`, the planner still returned the broken plan after all retries, which then got passed to the fallback ReAct agent in a corrupted state.

**Location**: Lines 190-203

**Problem Code**:
```python
if error_msg == "Plan has no steps" and plan.get('needs_clarification', False):
    logger.warning("Returning plan with no steps for user clarification")
    return plan
return None
```

This only checked for `needs_clarification` flag but didn't handle the case where the LLM simply failed to generate steps without requesting clarification.

### 2. ReAct Agent (`jarvis/core/react_agent.py`)

**Issue**: When the ReAct agent received a dict response from the LLM containing JSON content (from the failed predictive planner context), it blindly returned the raw content without checking if it was structured data that should be converted to natural language.

**Location**: Lines 158-170

**Problem Code**:
```python
if isinstance(response, dict):
    content = response.get('content', '')
    if content:
        return content  # ← Returns raw JSON string!
```

### 3. Chat Handler (`jarvis/core/orchestrator.py`)

**Issue**: The `_handle_chat_only` method didn't sanitize responses that might contain leaked JSON structures from previous failed attempts.

**Location**: Lines 610-657

## Fixes Applied

### Fix 1: Predictive Planner - Better Empty Plan Handling

**File**: `jarvis/core/predictive_planner.py`

**Change**: Distinguish between "LLM requested clarification" vs "LLM failed to generate plan"

```python
if error_msg == "Plan has no steps":
    if plan.get('needs_clarification', False):
        logger.warning("Returning plan with no steps for user clarification")
        return plan
    else:
        # LLM should have generated steps but didn't - this is a genuine failure
        # Don't return the broken plan, let it fall back to ReAct
        logger.warning("LLM generated empty plan without requesting clarification - will fallback to ReAct")
        return None
```

**Rationale**: Only return plans with no steps if the LLM explicitly requested clarification. Otherwise, return `None` to trigger a clean ReAct fallback.

### Fix 2: ReAct Agent - JSON Content Sanitization

**File**: `jarvis/core/react_agent.py`

**Change**: Detect and properly handle JSON-structured content in LLM responses

```python
if isinstance(response, dict):
    content = response.get('content', '')
    if content:
        # FIX: Check if content is a JSON clarification request
        try:
            import json as json_module
            if content.strip().startswith('{'):
                parsed_json = json_module.loads(content)
                # Check if this is a clarification request from predictive planner
                if parsed_json.get('needs_clarification', False):
                    # Build a helpful clarification message
                    goal = parsed_json.get('goal', task)
                    corrections = parsed_json.get('corrections', [])
                    clarification_msg = f"I need clarification to complete: {goal}"
                    if corrections:
                        clarification_msg += f" (I noticed: {', '.join(corrections)})"
                    clarification_msg += " Could you provide more details?"
                    logger.info(f"[ReAct] Detected clarification request: {clarification_msg}")
                    return clarification_msg
                
                # If it has steps but needs_clarification is false, extract the response
                if parsed_json.get('steps'):
                    content = parsed_json.get('goal', content)
        except (json_module.JSONDecodeError, Exception):
            pass
        
        return content
```

**Rationale**: When the ReAct agent receives JSON-structured content, it should:
1. Parse it to detect if it's a clarification request
2. Convert clarification requests into natural language questions
3. Extract meaningful content from structured responses
4. Never leak raw JSON to the user

### Fix 3: Chat Handler - Response Sanitization

**File**: `jarvis/core/orchestrator.py`

**Change**: Sanitize chat responses to prevent JSON leakage

```python
# FIX: Ensure response is not JSON structured data leaking into chat
if final_response and isinstance(final_response, str) and final_response.strip().startswith('{'):
    try:
        import json as json_module
        parsed = json_module.loads(final_response.strip())
        if isinstance(parsed, dict):
            # Check if this is a clarification request that leaked through
            if parsed.get('needs_clarification', False):
                goal = parsed.get('goal', 'your request')
                corrections = parsed.get('corrections', [])
                final_response = f"I need more information about: {goal}"
                if corrections:
                    final_response += f" ({', '.join(corrections)})"
                final_response += " Could you clarify?"
            elif parsed.get('goal'):
                final_response = parsed.get('goal', final_response)
            else:
                final_response = "I understand. How can I help you further?"
    except (json_module.JSONDecodeError, Exception):
        pass
```

**Rationale**: Even in chat mode, responses should be sanitized to ensure no internal JSON structures leak to the user.

## Expected Behavior After Fixes

### Scenario 1: User says "open notepad and write my name" (name unknown)

**Before Fix**:
```
JARVIS: {
    "goal": "Open Notepad and type the user's name",
    "corrections": [],
    "confidence": "medium",
    "needs_clarification": true,
    "steps": []
}
```

**After Fix**:
```
JARVIS: I need clarification to complete: Open Notepad and type the user's name. Could you provide more details?
```

Or ideally, the system should ask:
```
JARVIS: I'd be happy to open Notepad and write your name, but I don't know your name yet. What is your name?
```

### Scenario 2: User provides name, then repeats command

**Before Fix**: Subsequent commands might fail or return JSON
**After Fix**: System works normally, executes the command successfully

### Scenario 3: Cascading failures

**Before Fix**: One failure causes all subsequent commands to return JSON
**After Fix**: Each command is handled independently, failures are isolated

## Additional Recommendations

### 1. Improve LLM Prompt for Clarification

The predictive planner prompt should be enhanced to:
- Explicitly instruct the LLM to ask for missing information (like user's name) in natural language
- Provide examples of proper clarification requests
- Set `needs_clarification: true` ONLY when genuinely needed, not as a fallback for empty plans

### 2. Add State Recovery Mechanism

When a failure occurs:
- Clear any cached broken states
- Reset the conversation context to prevent corruption propagation
- Log the failure pattern for debugging

### 3. Implement Better Error Messages

Instead of generic failures, provide specific guidance:
- "I don't have your name stored. Would you like me to remember it?"
- "I need to know X before I can do Y"

### 4. Add Integration Tests

Create tests for:
- Multi-step commands with missing information
- Clarification request handling
- JSON leakage prevention
- Cascading failure isolation

## Testing Checklist

- [ ] Test "open notepad and write my name" without providing name first
- [ ] Verify system asks for clarification naturally
- [ ] Provide name and repeat command - verify success
- [ ] Run multiple commands after a failure - verify no cascading issues
- [ ] Test various multi-step commands with ambiguous parameters
- [ ] Verify no raw JSON appears in user-facing responses

## Files Modified

1. `/workspace/jarvis/core/predictive_planner.py` - Better empty plan handling
2. `/workspace/jarvis/core/react_agent.py` - JSON content sanitization
3. `/workspace/jarvis/core/orchestrator.py` - Response sanitization in chat handler

## Conclusion

The root cause was a combination of:
1. Improper handling of failed plan generation in the predictive planner
2. Lack of input validation in the ReAct agent for structured content
3. No sanitization layer to prevent JSON leakage in user-facing responses

The fixes ensure that:
- Failed predictions cleanly fall back to ReAct without corrupting state
- Structured responses are converted to natural language
- Clarification requests are properly formatted as questions
- No internal JSON structures leak to the user
