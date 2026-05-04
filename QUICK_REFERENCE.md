# JARVIS Quick Reference - Plan-Execute-Verify Loop

## 🚀 Quick Start (Windows)

```bash
# 1. Install dependencies
pip install playwright mss pillow pytesseract
playwright install chromium

# 2. Install Tesseract OCR (for visual verification)
# Download: https://github.com/UB-Mannheim/tesseract/wiki
# Add to PATH or configure in jarvis/core/vision.py
```

---

## 📋 Basic Usage Pattern

```python
from jarvis.execution import TaskExecutor, TaskStep, VerificationStrategy

# Initialize
executor = TaskExecutor(enable_visual_verification=True)

# Create plan
plan = executor.create_plan(
    task_id="my_task",
    description="What I want to accomplish"
)

# Add steps
executor.add_step(plan, 
    tool_name="navigate_to_url",
    parameters={"url": "https://example.com"},
    description="Open website",
    verification_strategy=VerificationStrategy.TOOL_RESULT
)

# Execute
result = executor.execute_plan(plan)

# Get summary
summary = executor.get_task_summary(plan)
print(f"Success: {summary['successful_steps']}/{summary['total_steps']}")
```

---

## 🛠️ Available Tools

### Web Automation
| Tool | Purpose | Example |
|------|---------|---------|
| `navigate_to_url` | Load webpage | `{"url": "https://jiji.co.ke"}` |
| `click_element` | Click button/link | `{"selector": "button.search"}` |
| `fill_input` | Type in form | `{"selector": "input[name='q']", "value": "cars"}` |
| `extract_content` | Scrape data | `{"mode": "prices", "limit": 20}` |
| `wait_for_element` | Wait for load | `{"selector": ".results", "timeout": 10000}` |
| `take_screenshot` | Capture page | `{"filename": "debug"}` |

### Verification Strategies
| Strategy | Use Case |
|----------|----------|
| `TOOL_RESULT` | Default - check tool success |
| `VISUAL` | Critical - verify on-screen text |
| `NONE` | Fast - no verification |
| `CUSTOM` | Advanced - custom function |

---

## 🎯 Real Example: Car Search

```python
from jarvis.execution import TaskExecutor, TaskStep, VerificationStrategy

executor = TaskExecutor()
plan = executor.create_plan(
    task_id="search_cars",
    description="Find Toyota cars 500k-1.5M on Jiji Kenya"
)

# Step 1: Navigate
executor.add_step(plan,
    tool_name="navigate_to_url",
    parameters={"url": "https://jiji.co.ke"},
    description="Open Jiji",
    verification_strategy=VerificationStrategy.VISUAL,
    verification_keyword="Jiji"
)

# Step 2: Search
executor.add_step(plan,
    tool_name="fill_input",
    parameters={"selector": "input[name='q']", "value": "Toyota"},
    description="Enter search term"
)

# Step 3: Submit
executor.add_step(plan,
    tool_name="click_element",
    parameters={"selector": "button.search-btn"},
    description="Click search"
)

# Step 4: Wait for results
executor.add_step(plan,
    tool_name="wait_for_element",
    parameters={"selector": ".car-listing", "timeout": 10000},
    description="Wait for listings"
)

# Step 5: Extract prices
executor.add_step(plan,
    tool_name="extract_content",
    parameters={"mode": "prices", "limit": 50},
    description="Get prices"
)

# Execute & report
result = executor.execute_plan(plan)
summary = executor.get_task_summary(plan)

print(f"\n{'='*50}")
print(f"Task: {summary['description']}")
print(f"Status: {summary['status']}")
print(f"Duration: {summary['duration_seconds']}s")
print(f"Steps: {summary['successful_steps']}/{summary['total_steps']} successful\n")

for step in summary['steps']:
    icon = "✓" if step['status'] == 'completed' else "✗"
    print(f"{icon} Step {step['step']}: {step['description']}")
    if step.get('error'):
        print(f"   Error: {step['error']}")
```

---

## 🔧 Key Features

### Loop Prevention
Automatically detects and stops duplicate actions within 60 seconds.

### Error Recovery
- Retry failed steps up to 2 times
- Exponential backoff (2s, 4s delays)
- Continue or stop on failure

### Visual Verification
```python
executor.add_step(plan,
    tool_name="navigate_to_url",
    parameters={"url": "https://example.com"},
    verification_strategy=VerificationStrategy.VISUAL,
    verification_keyword="Welcome"  # Text to find on screen
)
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Browser won't launch | `playwright install chromium` |
| Tesseract error | Install from GitHub, add to PATH |
| Visual verification fails | Increase timeout or disable |
| Stuck in loop | Check action history: `executor._action_history` |

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `jarvis/execution/task_executor.py` | Core Plan-Execute-Verify engine |
| `jarvis/tools/web/automation.py` | Web automation tools (already exists) |
| `jarvis/core/vision.py` | Screen perception (already exists) |
| `PLAN_EXECUTE_VERIFY_GUIDE.md` | Full documentation |
| `QUICK_REFERENCE.md` | This file |

---

## 💡 Pro Tips

1. **Disable visual verification** for speed on reliable sites:
   ```python
   executor = TaskExecutor(enable_visual_verification=False)
   ```

2. **Stop on first failure** for critical tasks:
   ```python
   result = executor.execute_plan(plan, stop_on_failure=True)
   ```

3. **Clear history** between unrelated tasks:
   ```python
   executor.clear_history()
   ```

4. **Debug with screenshots**:
   ```python
   executor.add_step(plan,
       tool_name="take_screenshot",
       parameters={"filename": "after_search"},
       description="Capture state"
   )
   ```

---

## ✅ What This Solves

**Before:** Blank responses, infinite loops, unreliable execution  
**After:** Verified steps, automatic recovery, clear summaries

Your JARVIS can now reliably automate daily computer tasks! 🎉
