# User Information Extraction & JSON Leak Fix - Summary

## Problem Analysis

From the logs, two critical issues were identified:

### Issue 1: JSON Leakage After Failed Commands
When the command "open notepad and write my name" failed (because the LLM didn't know the user's name), the system:
1. Predictive planner returned empty steps with `needs_clarification: true`
2. Fell back to ReAct agent
3. **ReAct agent leaked raw JSON** to the user instead of natural language
4. Subsequent commands also returned JSON structures

Example of broken output:
```
JARVIS: {
    "goal": "Open Notepad and type the user's name",
    "corrections": [],
    "confidence": "medium",
    "needs_clarification": true,
    "steps": []
}
```

### Issue 2: No User Memory Persistence
When user said "my name is orchard", the system:
1. Responded nicely: "Nice to meet you, Orchard!"
2. **But didn't store the name anywhere**
3. Next time "write my name" was requested, the LLM had no access to this information
4. Caused the same failure again

## Root Causes

1. **Missing user info extraction**: Chat messages containing personal info weren't being parsed and stored
2. **No profile integration**: User profile existed but wasn't being populated from conversations
3. **JSON sanitization gaps**: ReAct agent and chat handlers didn't properly convert structured responses to natural language
4. **Context not passed to planner**: Even if user info was stored, it wasn't being included in planning prompts

## Fixes Applied

### 1. User Information Extraction (`orchestrator.py`)

Added `_extract_user_info_from_chat()` method that:
- Parses chat messages for patterns like "my name is X", "I am X", "call me X"
- Extracts email, location, and other personal info
- Stores in persistent user profile via `UserProfileManager`
- Logs extracted information for debugging

```python
def _extract_user_info_from_chat(self, command: str) -> None:
    # Patterns for name, email, location extraction
    patterns = {
        'name': [r'\bmy\s+name\s+is\s+(\w+)\b', r'\bi\s+am\s+(\w+)\b', ...],
        'email': [r'\bmy\s+email\s+is\s+([^\s]+@[^\s]+)\b', ...],
        'location': [r'\bi\s+live\s+in\s+([^\.,]+)', ...],
    }
    # Store in profile manager for persistence
```

### 2. Profile Integration in Planner (`predictive_planner.py`)

Modified `generate_plan()` to:
- Load user profile context before generating plans
- Include user's name, location in the prompt context
- Enable LLM to use stored info for commands like "write my name"

```python
# Add user profile context to prompt
user_ctx = profile_mgr.current_profile.context
if user_ctx.name:
    context_section += f"\n\nUSER PROFILE CONTEXT:\n- User's name: {user_ctx.name}\n"
```

### 3. Enhanced Prompt Instructions (`predictive_planner.py`)

Added Rule #14 to PLAN_PROMPT:
```
14. USER CONTEXT: Check if user profile contains relevant information (name, preferences, etc.) 
    that should be used in the plan. For example, if the user asks to "write my name" and their 
    name is stored in the profile, use that name directly.
```

### 4. Existing JSON Sanitization (Already Present)

The code already had JSON leak prevention in:
- `_handle_chat_only()`: Detects and parses JSON responses, extracts natural language
- `_handle_chat_request()`: Similar sanitization for chat requests
- `react_agent.py`: Checks for `needs_clarification` flag and converts to natural questions

## Expected Behavior After Fix

### First Run (User Provides Name)
```
You: my name is orchard
JARVIS: Nice to meet you, Orchard! How can I assist you today?
[System stores "Orchard" in user profile]
```

### Second Run (Using Stored Name)
```
You: open notepad and write my name
[System loads "Orchard" from profile]
[LLM generates plan with type_text("Orchard")]
JARVIS: Opening notepad. Typed 7 characters
```

### If Name Not Known (Proper Clarification)
```
You: open notepad and write my name
JARVIS: I need clarification to complete: Open Notepad and type the user's name. 
        Could you provide more details?
```

## Testing Checklist

- [ ] Start fresh JARVIS instance
- [ ] Say "my name is [YourName]"
- [ ] Verify log shows: "Extracted user name from chat: [YourName]"
- [ ] Check `jarvis_data/user_profile.json` contains the name
- [ ] Say "open notepad and write my name"
- [ ] Verify notepad opens and name is typed
- [ ] Restart JARVIS
- [ ] Say "write my name in notepad" again
- [ ] Verify it still works (profile persists)

## Files Modified

1. `/workspace/jarvis/core/orchestrator.py`
   - Added `_extract_user_info_from_chat()` method
   - Integrated extraction into `_handle_chat_only()`

2. `/workspace/jarvis/core/predictive_planner.py`
   - Added user profile context loading in `generate_plan()`
   - Added Rule #14 to PLAN_PROMPT about using user context

## Architecture Improvement

Before: User info → LLM response → Lost after conversation
After:  User info → UserProfile → Persistent storage → Available to all planners

This creates a proper memory system where the assistant learns about the user and retains that knowledge across sessions.
