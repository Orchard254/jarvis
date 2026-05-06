# Vision-Guided Automation Guide

## Leveraging Gemma4 for Accurate Screen Analysis

JARVIS uses **Gemma4 vision** to analyze the screen and locate UI elements. This guide explains how to get the best results when using vision-based tools.

---

## Key Insight: Why Vision Sometimes Fails

When you ask JARVIS to "find close button for notepad", the vision model sees **ALL close buttons** on screen:
- Notepad's close button (top-right of Notepad window)
- Chrome's close button (top-right of Chrome window)  
- Every other window's close button

Without proper context, Gemma4 returns coordinates for the **most prominent** or **first detected** close button, which may not be the one you want.

---

## Best Practices for Vision-Based Actions

### ✅ DO: Use Specialized Tools First

Before using `find_on_screen` + `click_at`, try these more reliable tools:

| Task | Preferred Tool | Why |
|------|---------------|-----|
| Close Notepad | `close_window(title="Notepad")` | Uses Windows API - 100% accurate |
| Close Chrome tab | `close_tab(query="grok.com")` | DOM-level control - precise |
| Minimize Chrome | `minimize_window(title="Chrome")` | Windows API - reliable |
| Click web button | `click_element(selector="button.submit")` | Playwright - no coordinates needed |

### ✅ DO: Be Specific with Descriptions

When you MUST use `find_on_screen`:

❌ **Bad:** `"close button"` - Too vague, could match any window
✅ **Good:** `"the red X close button on the Notepad window"` - Specific window + visual detail
✅ **Better:** Use `window_context` parameter:
```python
find_on_screen(
    description="close button",
    window_context="Notepad"
)
```

### ✅ DO: Verify Before Critical Actions

For high-stakes clicks (closing windows), consider:
1. `analyze_screen(focus="windows")` - List all open windows
2. `find_on_screen(description="...", window_context="...")` - Locate element
3. Check the returned coordinates make sense
4. `click_at(x, y)` - Execute click

---

## Common Mistakes & Fixes

### Mistake 1: Closing Wrong Window

**User:** "find close button for notepad"  
**Result:** Closes Chrome instead of Notepad

**Why:** Both windows have close buttons at similar screen positions. Vision found Chrome's button first.

**Fix:** Use `close_window` tool directly:
```
close_window(title="Notepad")
```

### Mistake 2: Closing Entire Browser Instead of Tab

**User:** "close grok.com tab" → uses `find_on_screen` + `click_at`  
**Result:** Closes entire Chrome browser

**Why:** Coordinates targeted Chrome's main close button, not the tab's close button.

**Fix:** Use `close_tab` tool:
```
close_tab(query="grok.com")
```

### Mistake 3: Vague Element Description

**User:** "find minimize button"  
**Result:** May find wrong window's minimize button

**Fix:** Include window context:
```
find_on_screen(
    description="minimize button (horizontal line icon)",
    window_context="Chrome"
)
```

---

## How Gemma4 Vision Works

### The Vision Pipeline

1. **Screenshot Capture** - Full screen capture via MSS
2. **Image Encoding** - Converted to base64 for LLM processing
3. **Vision Analysis** - Gemma4 analyzes image with your description
4. **Coordinate Detection** - Returns (x, y) of most likely match
5. **Confidence Score** - Indicates how certain the model is

### Confidence Thresholds

- **≥90%** - Very confident, safe to click
- **70-89%** - Moderately confident, usually accurate
- **<70%** - Low confidence, verify before clicking (JARVIS logs warning)

---

## Advanced Techniques

### Technique 1: Multi-Step Verification

For critical operations:
```
1. analyze_screen(focus="windows") → See all windows
2. focus_window(title="Notepad") → Bring to foreground
3. close_window(title="Notepad") → Close safely
```

### Technique 2: Visual Confirmation

After finding coordinates:
```
1. find_on_screen(description="close button on Notepad") → Gets (1857, 27)
2. analyze_screen(focus="all") → Verify Notepad is at that location
3. click_at(x=1857, y=27) → Execute
```

### Technique 3: Browser Tab Control

For complex browser operations:
```
1. navigate_to_url(url="https://example.com") → Open page
2. click_element(selector="button.login") → Interact with page
3. close_tab(query="example.com") → Close specific tab
```

---

## Tool Decision Tree

```
Need to interact with UI?
│
├─ Is it a WINDOW operation? (close, minimize, maximize)
│  └─ Use: close_window / minimize_window / maximize_window
│
├─ Is it a BROWSER TAB operation?
│  └─ Use: close_tab / navigate_to_url / click_element
│
├─ Is it a WEB PAGE element? (buttons, links, forms)
│  └─ Use: click_element / type_in_field / get_page_content
│
└─ Is it a CUSTOM UI element? (game, specialized app)
   ├─ Can you describe it precisely?
   │  ├─ Yes → find_on_screen(description="...", window_context="...")
   │  └─ No → analyze_screen(focus="all") first to understand layout
   │
   └─ Then: click_at(x, y) with verified coordinates
```

---

## Examples: Right Way vs Wrong Way

### Example 1: Close Notepad

❌ **Wrong Approach:**
```
User: "find close button for notepad"
JARVIS: find_on_screen("close button") → (1857, 27)
JARVIS: click_at(1857, 27) → Closes Chrome! 😱
```

✅ **Right Approach:**
```
User: "close notepad"
JARVIS: close_window(title="Notepad") → Done! ✓
```

### Example 2: Close Specific Browser Tab

❌ **Wrong Approach:**
```
User: "close grok.com tab"
JARVIS: find_on_screen("close button on grok.com tab") → (1857, 27)
JARVIS: click_at(1857, 27) → Closes entire Chrome! 😱
```

✅ **Right Approach:**
```
User: "close grok.com tab"
JARVIS: close_tab(query="grok.com") → Done! ✓
```

### Example 3: Minimize Chrome

❌ **Wrong Approach:**
```
User: "find minimize button for chrome"
JARVIS: find_on_screen("minimize button") → Might find wrong window
JARVIS: click_at(...) → Minimizes wrong app!
```

✅ **Right Approach:**
```
User: "minimize chrome"
JARVIS: minimize_window(title="Chrome") → Done! ✓
```

OR with vision (if needed):
```
User: "find minimize button for chrome"
JARVIS: find_on_screen(
    description="minimize button (horizontal line)",
    window_context="Chrome"
) → (1268, 3) with 92% confidence
JARVIS: click_at(1268, 3) → Correctly minimizes Chrome ✓
```

---

## Troubleshooting

### Problem: "Vision keeps finding the wrong element"

**Solution:**
1. Add more descriptive details: "red X close button" vs just "close button"
2. Use `window_context` parameter to narrow focus
3. Bring target window to foreground first: `focus_window(title="...")`
4. Consider if a specialized tool exists (close_window, etc.)

### Problem: "Coordinates seem off"

**Solution:**
1. Check confidence score in the response (<70% = unreliable)
2. Take screenshot first: `analyze_screen()` to see current state
3. Verify window positions haven't changed
4. Try again with enhanced description

### Problem: "Action affects wrong application"

**Solution:**
This is the #1 issue! Always:
1. Use specialized tools when available (close_window > find_on_screen+click_at)
2. Focus target window first: `focus_window(title="Target")`
3. Verify with `analyze_screen(focus="windows")` before critical actions

---

## Summary: Golden Rules

1. **Specialized Tools First** - Always prefer `close_window`, `close_tab`, `minimize_window` over coordinate clicking
2. **Be Specific** - Include window name, visual details, and context in descriptions
3. **Verify High-Stakes Actions** - Check coordinates and confidence before clicking
4. **Focus Before Acting** - Bring window to foreground for better vision accuracy
5. **Trust but Verify** - Gemma4 is powerful but needs clear, specific instructions

---

**Remember:** Gemma4 vision is a powerful tool, but Windows API tools (`close_window`, `minimize_window`) and browser automation tools (`close_tab`, `click_element`) are **more reliable** because they don't depend on pixel-perfect coordinate detection.

Use vision for exploration and custom UI elements. Use specialized tools for standard operations.
