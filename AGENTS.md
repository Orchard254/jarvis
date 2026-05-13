# Tool Selection Guide

## 6 Core Tools

| Tool | When to use |
|------|-------------|
| `screen` | See the screen: capture (screenshot), find (UIA element lookup), tree (UI tree), query (vision Q&A), ocr (read text) |
| `input` | Send input: click (mouse), type (keyboard), hotkey (shortcuts like ctrl+c), scroll, drag |
| `window` | Manage apps/windows: open (launch or focus if running), close, focus, list, minimize, maximize, state (live desktop snapshot) |
| `browser` | Interactive web: navigate, click, type, read_page, screenshot, scroll |
| `exec` | Code execution + file I/O: run (Python/PowerShell), read file, write file |
| `memory` | Persistent facts: store, recall, search |

## Anti-Patterns

- ❌ `exec(run)` to launch apps → use `window(open)`
- ❌ `exec(run)` for web browsing → use `browser(navigate)`
- ❌ `screen(query)` just to verify → tool results already say success/fail
- ❌ `input(click)` on known elements without coordinates → use `screen(find, click=true)` for UIA targeting
- ❌ Calling `window(state)` multiple times → call once, it returns everything
