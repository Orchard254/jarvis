# Tool Selection Guide

## 6 Core Tools

| Tool | When to use |
|------|-------------|
| `window` | **START HERE for any app task.** open (launch OR focus if already running — ONE call does everything), close, focus, list, minimize, maximize, state (live desktop snapshot of windows + processes) |
| `screen` | **Eyes.** capture (screenshot; grid=true for coordinate overlay), find (locate+click UI element by text — UIA first, vision fallback), elements (list ALL clickable elements with coordinates), tree (UI tree), query (ask vision model about screen), ocr (read text) |
| `input` | **Hands.** click (at x,y coordinates), type (text), hotkey (keyboard shortcuts like ctrl+c), scroll, drag. Use AFTER screen(find) or screen(elements) gives you coordinates |
| `browser` | **Web.** navigate (go to URL — auto-launches browser), click (CSS selector), type (into field), read_page, screenshot, scroll. Auto-connects via CDP port 9222. Supports Brave, Opera, Firefox, Chrome |
| `exec` | **Escape hatch (last resort).** run (Python/PowerShell code), read (file), write (file). Only use when no dedicated tool covers the task |
| `memory` | **Persistent brain.** store (key+value), recall (by key), search (semantic query) |

## Decision Tree (follow top to bottom)

1. **Open/close/focus an app?** → `window(action="open|close|focus")`. Done.
2. **Go to a URL or web page?** → `browser(action="navigate")`. Done.
3. **Click a button/element inside an app?** → `screen(action="find", text="Button Name", click=true)`. Done.
4. **UIA can't find it (web content, Electron)?** → `screen(action="elements")` → `input(action="click", x=..., y=...)`.
5. **Type text or press keys?** → `input(action="type|hotkey")`. Done.
6. **Read/write a file?** → `exec(action="read|write")`. Done.
7. **Remember something?** → `memory(action="store")`. Done.
8. **Volume/brightness?** → `input(action="hotkey", keys="volumeup|volumedown")`. For precise levels, use screen interaction to click the slider. Do NOT use PowerShell/Python scripts.
9. **None of the above?** → Respond conversationally. No tool needed.

## How to Interact with Any App

1. **Native Windows apps** (Notepad, Explorer, Settings): `screen(find, text="Button Name", click=true)` — UIA is fast and precise.
2. **Web content in Chrome/Brave/etc**: Use `browser(click, selector="...")` if you know the CSS selector. Or use `screen(elements)` to discover elements, then `input(click, x=..., y=...)`.
3. **Unknown/complex apps**: Call `screen(elements)` to list all clickable elements with coordinates. Then `input(click, x=..., y=...)` to interact.
4. **When nothing else works**: `screen(capture, grid=true)` → `screen(query, question="where is the X button?")` → `input(click, x=..., y=...)`.

## Common Task Examples

| User says | Correct tool call |
|-----------|------------------|
| "open notepad" | `window(action="open", app_name="notepad")` |
| "close chrome" | `window(action="close", window_title="Chrome")` |
| "go to google.com" | `browser(action="navigate", url="https://google.com")` |
| "click Save button" | `screen(action="find", text="Save", click=true)` |
| "type hello world" | `input(action="type", text="hello world")` |
| "press ctrl+s" | `input(action="hotkey", keys="ctrl+s")` |
| "set volume to 50" | `input(action="hotkey", keys="volumeup")` (use media keys, NOT scripts) |
| "what's running" | `window(action="state")` |
| "remember my name" | `memory(action="store", key="user_name", value="...")` |

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
- ❌ `exec(run)` for volume/brightness → use `input(hotkey)` with media keys or screen interaction
- ❌ `window(open, "chrome")` then `browser(navigate)` → just `browser(navigate)`, it auto-launches
- ❌ `window(state)` then `window(open)` → `window(open)` already checks if running
- ❌ `screen(find)` then `input(click)` → use `screen(find, click=true)` in ONE call
- ❌ `screen(query)` just to verify → tool results already say success/fail
- ❌ `input(click)` on known elements without coordinates → use `screen(find, click=true)` for UIA targeting
- ❌ Calling `window(state)` multiple times → call once, it returns everything
- ❌ Guessing coordinates blindly → use `screen(elements)` or `screen(capture, grid=true)` first
- ❌ Adding extra "verify" steps → tool results already confirm success/fail
