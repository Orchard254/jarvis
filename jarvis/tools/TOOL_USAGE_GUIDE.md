# JARVIS Tool Usage Guide - Window & Tab Management

## Overview

This guide clarifies the proper usage of window management, browser tab, and screen interaction tools to prevent confusion and incorrect tool selection.

---

## 🔴 CRITICAL DISTINCTIONS

### 1. Closing Windows vs Tabs vs Browser

| Action | Correct Tool | DO NOT Use |
|--------|-------------|------------|
| Close Notepad/Calculator app | `close_window(title="Notepad")` | ❌ `click_at`, `find_on_screen` |
| Close a browser tab (e.g., grok.com) | `close_tab(query="grok.com")` | ❌ `close_window`, `click_at`, `close_browser` |
| Close entire Chrome/Firefox browser | `close_browser(browser="chrome")` | ❌ `close_tab` (only closes one tab) |

### 2. Minimizing Windows

| Action | Correct Tool | DO NOT Use |
|--------|-------------|------------|
| Minimize Chrome/Notepad window | `minimize_window(title="Chrome")` | ❌ `click_at`, `find_on_screen` |
| Minimize ALL windows (show desktop) | `minimize_windows()` | ❌ Individual minimize calls |

### 3. Finding vs Clicking Elements

| Action | Correct Tool | Notes |
|--------|-------------|-------|
| Locate where a button is | `find_on_screen(description="close button")` | Returns coordinates only |
| Click at known coordinates | `click_at(x=100, y=50)` | Use AFTER find_on_screen |
| Close a window | `close_window(title="...")` | Don't find+click, just close! |

---

## 📋 Tool Reference by Category

### Window Management Tools (`jarvis.tools.apps.window`)

#### `close_window(title: str)`
- **Purpose**: Close application windows gracefully using WM_CLOSE message
- **Use for**: Notepad, Calculator, File Explorer, any app window
- **NOT for**: Browser tabs (use `close_tab`)
- **Example**: `close_window(title="Untitled - Notepad")`

#### `minimize_window(title: str)`
- **Purpose**: Minimize a specific window
- **Use for**: Chrome, Notepad, any minimizable window
- **NOT for**: Clicking minimize buttons manually
- **Example**: `minimize_window(title="Google Chrome")`

#### `focus_window(title: str)`
- **Purpose**: Bring window to foreground
- **Use for**: Activating inactive windows
- **Example**: `focus_window(title="Chrome")`

#### `get_window_list()`
- **Purpose**: List all open windows with titles and positions
- **Use for**: Discovering available windows
- **Returns**: List of window titles, PIDs, and positions

#### `minimize_windows()`
- **Purpose**: Minimize ALL windows (Win+D equivalent)
- **Use for**: Showing desktop
- **Example**: `minimize_windows()`

---

### Browser Tab Tools (`jarvis.tools.web.automation`)

#### `close_tab(query: str)`
- **Purpose**: Close a specific browser tab by title or URL match
- **Use for**: Closing individual tabs like "grok.com", "YouTube"
- **NOT for**: Closing entire browser (use `close_browser`)
- **NOT for**: Closing app windows (use `close_window`)
- **Example**: `close_tab(query="grok.com")`

#### `navigate_to_url(url: str)`
- **Purpose**: Navigate browser to URL
- **Use for**: Opening websites
- **Example**: `navigate_to_url(url="https://example.com")`

#### `click_element(selector: str)`
- **Purpose**: Click web page elements (buttons, links)
- **Use for**: Interacting with webpage content
- **NOT for**: Desktop window controls
- **Example**: `click_element(selector="button.submit")`

---

### Browser Process Tools (`jarvis.tools.web.browser`)

#### `close_browser(browser: str = "all")`
- **Purpose**: Kill entire browser process(es)
- **Use for**: Completely exiting Chrome, Firefox, Edge
- **NOT for**: Closing single tabs (use `close_tab`)
- **Options**: "chrome", "firefox", "edge", "all"
- **Example**: `close_browser(browser="chrome")`

#### `search_web(query: str)`
- **Purpose**: Search Google in browser
- **Use for**: Web searches
- **Example**: `search_web(query="weather today")`

#### `open_url(url: str)`
- **Purpose**: Open URL in default browser
- **Use for**: Simple URL opening
- **Example**: `open_url(url="https://example.com")`

---

### Screen Interaction Tools (`jarvis.tools.screen.capture`)

#### `find_on_screen(description: str)`
- **Purpose**: LOCATE element using AI vision, returns coordinates
- **Use for**: Finding where UI elements are positioned
- **NOT for**: Clicking or interacting (just locates)
- **NOT for**: Closing windows (use `close_window`)
- **Returns**: Coordinates (x, y)
- **Example**: `find_on_screen(description="save button")` → `(1200, 50)`

#### `click_at(x: int, y: int, button: str = "left")`
- **Purpose**: Click at exact pixel coordinates
- **Use for**: Low-level clicking AFTER find_on_screen
- **NOT for**: High-level actions when specialized tools exist
- **Priority**: LAST RESORT - prefer `close_window`, `close_tab`, `minimize_window`, `click_element`
- **Example**: `click_at(x=1200, y=50)`

#### `analyze_screen(focus: str = "all")`
- **Purpose**: Analyze screen content using AI vision
- **Use for**: Understanding what's on screen
- **Focus options**: "all", "windows", "text", "elements"
- **Example**: `analyze_screen(focus="windows")`

#### `screenshot()`
- **Purpose**: Capture screenshot
- **Use for**: Saving screen state
- **Example**: `screenshot()`

---

## 🎯 Decision Tree

### "I want to close something"
```
├─ Is it an application window (Notepad, Calculator)?
│  └─→ Use `close_window(title="...")`
│
├─ Is it a browser tab?
│  └─→ Use `close_tab(query="...")`
│
└─ Is it the entire browser?
   └─→ Use `close_browser(browser="chrome")`
```

### "I want to minimize something"
```
├─ Single window?
│  └─→ Use `minimize_window(title="...")`
│
└─ All windows (show desktop)?
   └─→ Use `minimize_windows()`
```

### "I want to click something"
```
├─ Is it a webpage element?
│  └─→ Use `click_element(selector="...")`
│
├─ Is it a window control (close/minimize)?
│  └─→ DON'T CLICK! Use `close_window()` or `minimize_window()`
│
├─ Do you know the coordinates?
│  └─→ Use `click_at(x=..., y=...)`
│
└─ Need to find it first?
   ├─→ Use `find_on_screen(description="...")` to get coordinates
   └─→ Then use `click_at(x=..., y=...)`
```

---

## ⚠️ Common Mistakes & Fixes

### Mistake 1: Using click_at to close Notepad
```python
# ❌ WRONG - Unreliable, may click wrong thing
find_on_screen(description="close button on Notepad")
click_at(x=1857, y=27)

# ✅ CORRECT - Direct and reliable
close_window(title="Notepad")
```

### Mistake 2: Using close_window to close a browser tab
```python
# ❌ WRONG - Closes entire browser
close_window(title="grok.com")

# ✅ CORRECT - Closes only the tab
close_tab(query="grok.com")
```

### Mistake 3: Using close_browser to close one tab
```python
# ❌ WRONG - Closes ALL tabs in browser
close_browser(browser="chrome")

# ✅ CORRECT - Closes only matching tab
close_tab(query="grok.com")
```

### Mistake 4: Using click_at to minimize Chrome
```python
# ❌ WRONG - May click wrong coordinates
find_on_screen(description="minimize button on Chrome")
click_at(x=1268, y=3)

# ✅ CORRECT - Direct API call
minimize_window(title="Chrome")
```

---

## 🧠 Best Practices

1. **Always prefer high-level tools** over low-level coordinate clicking
2. **Use specialized tools** for their intended purpose
3. **Reserve `click_at`** for when no other tool works
4. **Verify window/tab names** before closing
5. **Test with `get_window_list()`** to see available windows

---

## 📝 Example Workflows

### Workflow 1: Close Notepad after saving
```python
# Check if Notepad is open
get_window_list()
# Output shows: "Untitled - Notepad"

# Close it gracefully
close_window(title="Notepad")
```

### Workflow 2: Close specific browser tab
```python
# Close grok.com tab without affecting other tabs
close_tab(query="grok.com")
```

### Workflow 3: Minimize Chrome
```python
# Minimize Chrome window
minimize_window(title="Chrome")
```

### Workflow 4: Clean up everything
```python
# Close all browser tabs one by one
close_tab(query="youtube.com")
close_tab(query="grok.com")

# Close Notepad
close_window(title="Notepad")

# Minimize remaining windows
minimize_windows()
```

---

## Summary

| Task | Primary Tool | Fallback |
|------|-------------|----------|
| Close app window | `close_window` | None needed |
| Close browser tab | `close_tab` | None needed |
| Close browser | `close_browser` | None needed |
| Minimize window | `minimize_window` | None needed |
| Click web element | `click_element` | None needed |
| Find UI element | `find_on_screen` | None needed |
| Click at coords | N/A | `click_at` (last resort) |

Remember: **Specialized tools are always better than generic coordinate clicking!**
