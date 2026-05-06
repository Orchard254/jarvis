# JARVIS Long-Term Architecture Plan

## Executive Summary

This document outlines the strategic evolution of JARVIS from a basic command-response system to a **production-grade autonomous desktop agent** capable of reliable, complex task execution. The focus is on **visual awareness**, **state verification**, and **robust error recovery**.

---

## 🎯 Core Problems Identified

### Current Limitations
1. **Blind Execution**: Tools execute without verifying success (e.g., `search_web` opens browser but doesn't confirm results loaded)
2. **No Visual Feedback**: Agent cannot "see" what's on screen to verify UI states
3. **Repetitive Loops**: Without state tracking, AI repeats failed actions indefinitely
4. **Shallow Web Interaction**: Basic `webbrowser.open()` cannot interact with dynamic content
5. **No Memory of Actions**: Limited context about what was actually accomplished

---

## 🏗️ Architectural Pillars

### 1. **Visual Perception Layer** ✅ (Implemented)
**File**: `jarvis/core/vision.py`

```python
# Capabilities added:
- Screen capture with region selection
- OCR text extraction from screen
- Element visibility verification
- Visual context summarization for LLM
```

**Installation Required**:
```bash
pip install mss pillow pytesseract
# Windows: Install Tesseract OCR from https://github.com/UB-Mannheim/tesseract/wiki
```

**Usage Example**:
```python
from jarvis.core.vision import get_perceptor

perceptor = get_perceptor()
# Verify search results appeared
if perceptor.verify_element_visible("Search results", timeout=5):
    print("Search succeeded!")
```

---

### 2. **Advanced Web Automation** ✅ (Implemented)
**File**: `jarvis/tools/web/automation.py`

Replaces blind URL opening with DOM-level control:

| Tool | Purpose |
|------|---------|
| `navigate_to_url` | Load URL with wait-for-load verification |
| `click_element` | Click buttons/links by selector or text |
| `fill_input` | Type into forms with label detection |
| `extract_content` | Scrape prices, tables, links from pages |
| `wait_for_element` | Pause until dynamic content appears |
| `take_screenshot` | Capture page state for debugging/LLM vision |

**Installation Required**:
```bash
pip install playwright
playwright install chromium
```

**Example Task Flow**:
```python
# Instead of: "open jiji.co.ke" (blind)
# Now: Structured workflow
1. navigate_to_url("https://jiji.co.ke")
2. wait_for_element(".search-box")
3. fill_input("label:Search", "Toyota cars")
4. click_element("button.search-btn")
5. wait_for_element(".car-listing", timeout=10000)
6. extract_content(mode="prices", limit=20)
```

---

### 3. **Plan-Execute-Verify Loop** 📋 (Design)

Replace single-step tool calls with verified workflows:

```python
class TaskExecutor:
    def execute_with_verification(self, plan: List[Dict]) -> bool:
        for step in plan:
            # Execute
            result = tool.execute(**step['params'])
            
            # Verify
            if not self.verify_success(step, result):
                # Retry with fallback strategy
                if not self.retry_with_alternative(step):
                    return False
            
            # Update context memory
            self.memory.record_completion(step)
        
        return True
```

**Key Features**:
- Each action has explicit success criteria
- Automatic retry with alternative methods
- Context updates prevent repetition
- Timeout and circuit-breaker protection

---

### 4. **Enhanced Memory System** 🧠 (Recommended Implementation)

Add **sliding window summaries** to track completed actions:

```python
# In jarvis/core/memory.py - Add:

class ActionMemory:
    def __init__(self, max_history=10):
        self.completed_actions = deque(maxlen=max_history)
    
    def record(self, tool_name: str, params: dict, result: str):
        self.completed_actions.append({
            'timestamp': time.time(),
            'tool': tool_name,
            'params': params,
            'result_summary': result[:100]
        })
    
    def get_recent_context(self) -> str:
        """Generate summary for LLM to avoid repetition"""
        if not self.completed_actions:
            return ""
        
        summary = "Recently completed actions:\n"
        for action in self.completed_actions:
            summary += f"- {action['tool']}({action['params']}) → {action['result_summary']}\n"
        return summary
    
    def should_skip(self, tool_name: str, params: dict) -> bool:
        """Prevent repeating same action within 30 seconds"""
        cutoff = time.time() - 30
        for action in reversed(self.completed_actions):
            if action['timestamp'] < cutoff:
                break
            if (action['tool'] == tool_name and 
                action['params'] == params):
                return True
        return False
```

---

### 5. **Error Recovery Strategies** 🛡️ (Design)

Build automatic fallbacks for common failures:

| Failure Scenario | Primary Action | Fallback 1 | Fallback 2 |
|-----------------|----------------|------------|------------|
| Element not found | Wait + retry | Screenshot + analyze | Ask user for guidance |
| Navigation timeout | Increase timeout | Try mobile UA | Use direct API |
| Search returns 0 results | Refine query | Try alternative site | Report to user |
| Browser crashed | Restart browser | Use requests + BeautifulSoup | Abort gracefully |

**Implementation Pattern**:
```python
def execute_with_fallback(self, primary_tool, fallbacks, **params):
    for i, tool in enumerate([primary_tool] + fallbacks):
        try:
            result = tool.execute(**params)
            if result.success:
                return result
        except Exception as e:
            log.warning(f"Attempt {i+1} failed: {e}")
            continue
    
    return ToolResult.fail("All fallback strategies exhausted")
```

---

## 📦 Installation & Setup

### Dependencies for Production Use

```bash
# Core vision capabilities
pip install mss pillow pytesseract

# Advanced web automation
pip install playwright
playwright install chromium

# Optional: Enhanced OCR accuracy
# Windows: Download Tesseract installer
# Linux: sudo apt install tesseract-ocr

# Optional: Better text processing
pip install pdf2image opencv-python
```

### Updated requirements.txt additions:
```txt
# Visual perception
mss>=9.0.1
Pillow>=10.0.0
pytesseract>=0.3.10

# Web automation
playwright>=1.40.0

# Optional enhancements
opencv-python>=4.8.0
pdf2image>=1.16.0
```

---

## 🔧 Integration Guide

### Step 1: Register New Tools

Update tool loading in your initialization:

```python
# In jarvis/tools/web/__init__.py (already done)
from .automation import WEB_AUTOMATION_TOOLS
ALL_WEB_TOOLS = WEB_TOOLS + WEB_AUTOMATION_TOOLS
```

The registry auto-discovers these tools via naming convention (`*Tool` classes).

### Step 2: Enable Vision in Brain Context

Modify `jarvis/core/brain.py` to include visual context when available:

```python
def build_context(self, user_input: str) -> dict:
    context = {
        "user_input": user_input,
        "recent_actions": self.memory.get_recent_context(),
    }
    
    # Add visual context if relevant
    if self.needs_visual_verification(user_input):
        try:
            perceptor = get_perceptor()
            context["screen_state"] = perceptor.get_visual_context_summary()
        except:
            pass  # Vision not available, continue blind
    
    return context
```

### Step 3: Update System Prompt

Enhance AI instructions to use verification:

```python
SYSTEM_PROMPT = """
You are JARVIS, an autonomous desktop assistant.

IMPORTANT WORKFLOW:
1. Before acting, check recent_actions to avoid repetition
2. After each tool call, VERIFY the action succeeded:
   - For web actions: Use wait_for_element to confirm page loaded
   - For searches: Use extract_content to verify results exist
   - If unsure: Use take_screenshot and analyze
3. If an action fails twice, try an ALTERNATIVE approach
4. Never repeat the same action more than twice

AVAILABLE ADVANCED TOOLS:
- navigate_to_url: Opens URL and waits for load
- click_element: Clicks buttons by text or CSS selector
- fill_input: Types into form fields
- extract_content: Scrapes data from pages
- wait_for_element: Waits for dynamic content
- take_screenshot: Captures current state
"""
```

---

## 📈 Performance Metrics

Track these KPIs to measure improvement:

| Metric | Before | Target | Measurement |
|--------|--------|--------|-------------|
| Task Success Rate | ~40% | >90% | % of multi-step tasks completed |
| Repetition Rate | High | <5% | Same tool called twice in 30s |
| Avg Steps per Task | 2-3 | 5-8 | Complex tasks require more verified steps |
| User Corrections | Frequent | Rare | Times user must rephrase/retry |

---

## 🚀 Phase 2 Recommendations (Future)

### 1. **Native App Automation**
- Integrate `pywinauto` (Windows) or `pyautogui` for desktop apps
- Control Excel, Word, file explorer directly

### 2. **Voice + Vision Fusion**
- Real-time screen analysis during voice commands
- "Show me..." commands trigger screenshot + OCR

### 3. **Learning from Corrections**
- Store failed attempts and successful recoveries
- Fine-tune model on successful task trajectories

### 4. **Parallel Task Execution**
- Background monitoring while executing foreground tasks
- Multi-threaded tool execution with dependency graph

### 5. **API Integrations**
- Direct APIs for common services (Google, Amazon, etc.)
- Fallback to UI automation only when API unavailable

---

## 🎯 Immediate Next Steps

1. **Install Dependencies**:
   ```bash
   pip install mss pillow pytesseract playwright
   playwright install chromium
   ```

2. **Test Vision Module**:
   ```python
   from jarvis.core.vision import get_perceptor
   p = get_perceptor()
   print(p.read_screen_text())
   ```

3. **Test Web Automation**:
   ```python
   from jarvis.tools.web.automation import get_automation_engine
   engine = get_automation_engine()
   page = engine.ensure_browser()
   page.goto("https://google.com")
   ```

4. **Update Orchestrator** to use Plan-Execute-Verify pattern

5. **Monitor Logs** for repetitive patterns and add memory checks

---

## 📝 Conclusion

The foundation is now in place:
- ✅ Visual perception module created
- ✅ Advanced web automation tools implemented
- ✅ Tool registry updated to discover new tools

**Next priority**: Implement the Plan-Execute-Verify loop in the orchestrator and add action memory to prevent repetition. This transforms JARVIS from a reactive tool caller into a proactive, self-correcting autonomous agent.
