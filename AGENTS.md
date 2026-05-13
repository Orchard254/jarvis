# Tool Selection Guide

## 6 Core Tools

| Tool | When to use |
|------|-------------|
| `screen` | See the screen: capture (screenshot, grid=true for coordinate overlay), find (UIA element lookup + vision fallback), tree (UI tree), elements (list ALL interactive elements from UIA + vision), query (vision Q&A), ocr (read text) |
| `input` | Send input: click (mouse), type (keyboard), hotkey (shortcuts like ctrl+c), scroll, drag |
| `window` | Manage apps/windows: open (launch or focus if running), close, focus, list, minimize, maximize, state (live desktop snapshot) |
| `browser` | Interactive web via Playwright — supports Brave, Opera, Firefox, Chrome. Auto-connects via CDP (port 9222), or launches preferred browser (set BROWSER_PREFERRED): navigate, click, type, read_page, screenshot, scroll |
| `exec` | Code execution + file I/O: run (Python/PowerShell), read file, write file |
| `memory` | Persistent facts: store, recall, search |

## How to Interact with Any App

1. **Native Windows apps** (Notepad, Explorer, Settings): `screen(find, text="Button Name", click=true)` — UIA is fast and precise.
2. **Web content in Chrome**: Use `browser(click, selector="...")` if you know the CSS selector. Or use `screen(elements)` to discover elements, then `input(click, x=..., y=...)`.
3. **Unknown/complex apps**: Call `screen(elements)` to list all clickable elements with coordinates. Then `input(click, x=..., y=...)` to interact.
4. **When nothing else works**: `screen(capture, grid=true)` → `screen(query, question="where is the X button?")` → `input(click, x=..., y=...)`.

## Browser Configuration

Set `BROWSER_PREFERRED` env var to your browser of choice: `brave`, `opera`, `firefox`, `chrome`, or `auto` (default — tries Brave → Opera → Firefox → Chrome).

To connect `browser()` to your existing browser (instead of launching a new one), start it with remote debugging:
```
brave.exe --remote-debugging-port=9222
opera.exe --remote-debugging-port=9222
chrome.exe --remote-debugging-port=9222
firefox.exe -start-debugger-server 9222
```
The browser tool auto-detects CDP on port 9222 (configurable via `BROWSER_CDP_PORT`).

## Anti-Patterns

- ❌ `exec(run)` to launch apps → use `window(open)`
- ❌ `exec(run)` for web browsing → use `browser(navigate)`
- ❌ `screen(query)` just to verify → tool results already say success/fail
- ❌ `input(click)` on known elements without coordinates → use `screen(find, click=true)` for UIA targeting
- ❌ Calling `window(state)` multiple times → call once, it returns everything
- ❌ Guessing coordinates blindly → use `screen(elements)` or `screen(capture, grid=true)` first
