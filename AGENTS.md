# Tool Selection Guide

## 6 Core Tools

| Tool | When to use |
|------|-------------|
| `screen` | See the screen: capture (screenshot, grid=true for coordinate overlay), find (UIA element lookup + vision fallback), tree (UI tree), elements (list ALL interactive elements from UIA + vision), query (vision Q&A), ocr (read text) |
| `input` | Send input: click (mouse), type (keyboard), hotkey (shortcuts like ctrl+c), scroll, drag |
| `window` | Manage apps/windows: open (launch or focus if running), close, focus, list, minimize, maximize, state (live desktop snapshot) |
| `browser` | Interactive web via Playwright (auto-connects to existing Chrome via CDP port 9222): navigate, click, type, read_page, screenshot, scroll |
| `exec` | Code execution + file I/O: run (Python/PowerShell), read file, write file |
| `memory` | Persistent facts: store, recall, search |

## How to Interact with Any App

1. **Native Windows apps** (Notepad, Explorer, Settings): `screen(find, text="Button Name", click=true)` — UIA is fast and precise.
2. **Web content in Chrome**: Use `browser(click, selector="...")` if you know the CSS selector. Or use `screen(elements)` to discover elements, then `input(click, x=..., y=...)`.
3. **Unknown/complex apps**: Call `screen(elements)` to list all clickable elements with coordinates. Then `input(click, x=..., y=...)` to interact.
4. **When nothing else works**: `screen(capture, grid=true)` → `screen(query, question="where is the X button?")` → `input(click, x=..., y=...)`.

## CDP Browser Connection

To connect `browser()` to your existing Chrome (instead of launching a separate one):
```
chrome.exe --remote-debugging-port=9222
```
The browser tool auto-detects CDP on port 9222 and connects to your session.

## Anti-Patterns

- ❌ `exec(run)` to launch apps → use `window(open)`
- ❌ `exec(run)` for web browsing → use `browser(navigate)`
- ❌ `screen(query)` just to verify → tool results already say success/fail
- ❌ `input(click)` on known elements without coordinates → use `screen(find, click=true)` for UIA targeting
- ❌ Calling `window(state)` multiple times → call once, it returns everything
- ❌ Guessing coordinates blindly → use `screen(elements)` or `screen(capture, grid=true)` first
