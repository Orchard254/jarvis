# Vision Integration Refactoring Summary

## Overview
Refactored Gemma3 vision integration to enforce strict separation:
- **Gemma3 (4B)** = Perception ONLY via `vision_call()` gateway
- **GPT-OSS (120B)** = Planning + Decision making

---

## 1. vision_call() Implementation

**File:** `/workspace/jarvis/perception/vision.py`

```python
def vision_call(
    image_base64: str,
    task: Literal["detect_elements", "read_text", "describe_scene"],
    query: Optional[str] = None
) -> Dict[str, Any]:
    """
    The ONLY function that invokes Gemma3 for vision tasks.
    
    Returns structured outputs:
    - detect_elements: {"elements": [{"label": str, "text": str|null, "x": int, "y": int, "confidence": float}, ...]}
    - read_text: {"text": str}
    - describe_scene: {"summary": str}
    """
```

### Key Features:
- Single entry point for ALL Gemma3 calls
- Strict JSON output schemas enforced
- No free-text responses allowed
- Validates all outputs before returning

---

## 2. Allowed Vision Tools Registry

**File:** `/workspace/jarvis/tools/vision/tools.py`

Only these 4 tools can invoke Gemma3:

| Tool | Description | Output Schema |
|------|-------------|---------------|
| `screen.capture` | Capture screenshot | `{"image_base64": str}` |
| `vision.detect_elements` | Find UI elements | `{"elements": [...]}` |
| `vision.read_text` | Extract text | `{"text": str}` |
| `vision.describe_scene` | Scene summary | `{"summary": str}` |

### Removed/Disabled Patterns:
- ❌ No action tools like `click_button`, `login_with_vision`
- ❌ No direct Gemma3 calls outside `vision_call()`
- ❌ No free-form text parsing from vision outputs

---

## 3. Executor Patch

**File:** `/workspace/jarvis/tools/executor_vision_patch.py`

Routes all `vision.*` tool calls through validation:

```python
class VisionExecutionHandler:
    CONFIDENCE_THRESHOLD = 0.7
    MAX_RETRIES = 1
    
    def execute_with_validation(self, tool_name, arguments):
        # 1. Route through vision_call()
        result = vision_call(image, task, query)
        
        # 2. Validate structured output
        validated = self._validate_output(result["result"], task)
        
        # 3. Check confidence, retry if < 0.7
        if confidence < 0.7 and retries < MAX_RETRIES:
            return self.retry_with_region_capture(...)
        
        return ToolResult.ok(validated["data"])
```

---

## 4. UI Action Tools (Separate from Vision)

**File:** `/workspace/jarvis/tools/ui/actions.py`

These tools perform actions but DO NOT use Gemma3:

| Tool | Description |
|------|-------------|
| `ui.click(x, y)` | Click at coordinates |
| `ui.type_text(text)` | Type text |
| `ui.press_key(key)` | Press keyboard key |
| `ui.focus_window(name)` | Focus window by name |

---

## 5. Planner Contract (GPT-OSS)

Planner can call:
- `screen.capture` - Get screenshot
- `vision.*` tools - Perception queries  
- `ui.*` tools - Execute actions

**Planner MUST NOT:**
- Delegate decisions to vision
- Expect vision to make choices
- Use vision for anything other than perception

Vision outputs are INPUTS to later actions:
```
vision.detect_elements("login button") 
  → returns {x: 100, y: 200, confidence: 0.85}
  → planner decides to click
  → ui.click(100, 200)
```

---

## 6. Tool Hints for Planner

Only expose vision tools when:
- Task mentions UI ambiguity ("click", "find", "on screen")
- No deterministic tool exists for the task

Example hint logic:
```python
def should_use_vision(task: str) -> bool:
    vision_keywords = ["click", "find", "locate", "see", "on screen", "button", "visible"]
    return any(kw in task.lower() for kw in vision_keywords)
```

---

## 7. Example Plan: "Click Login Button"

```
Step 1: screen.capture()
  → Returns: base64_image

Step 2: vision.detect_elements(query="login button")
  → Calls: vision_call(base64_image, "detect_elements", "login button")
  → Returns: {
      "elements": [
        {"label": "button", "text": "Login", "x": 150, "y": 300, "confidence": 0.92}
      ]
    }

Step 3: Validate confidence >= 0.7 ✓

Step 4: ui.click(x=150, y=300)
  → Executes actual click
  → Returns: "Clicked left button at (150, 300)"
```

---

## File Structure

```
/workspace/jarvis/
├── perception/
│   └── vision.py              # vision_call() gateway + Gemma3PerceptionGateway
├── tools/
│   ├── vision/
│   │   ├── __init__.py
│   │   └── tools.py           # 4 allowed vision tools
│   ├── ui/
│   │   ├── __init__.py
│   │   └── actions.py         # UI action tools (no Gemma3)
│   ├── executor_vision_patch.py  # Vision execution handler
│   └── executor.py            # Updated to route vision.* calls
└── ...
```

---

## Structured Output Schemas

### detect_elements
```json
{
  "elements": [
    {
      "label": "button|input|link|icon|menu|text",
      "text": "visible label or null",
      "x": 150,
      "y": 300,
      "confidence": 0.92
    }
  ]
}
```

### read_text
```json
{
  "text": "all visible text as single string"
}
```

### describe_scene
```json
{
  "summary": "one sentence description of screen content"
}
```

---

## Migration Notes

### For Existing Code:
1. Replace direct Gemma3 calls with `vision_call()`
2. Update tool names to use `vision.*` prefix
3. Handle structured outputs instead of free text
4. Use `ui.*` tools for actions, not vision

### Deprecated (Backward Compatible):
- `VisionAnalyzer` class still works but wraps `vision_call()`
- `get_vision_analyzer()` available for legacy code
- Recommend migrating to direct `vision_call()` usage
