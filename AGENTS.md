# Tool Selection Guide

## 8 Core Tools

| Tool | When to use |
|------|-------------|
| `screen` | See the screen: capture (screenshot), find (UIA element lookup), tree (UI tree), query (vision Q&A), watch (monitor over time), ocr (read text) |
| `input` | Send input: click (mouse), type (keyboard), hotkey (shortcuts like ctrl+c), scroll, drag, move |
| `window` | Manage apps/windows: open (launch or focus if running), close, focus, list, info, resize, minimize, maximize, restore |
| `system` | Query system: state (live windows/processes), search_app (installed), search_file (on disk), hardware (CPU/RAM/disk) |
| `browser` | Interactive web: navigate, click, type, read_page, screenshot, tabs, scroll, refresh |
| `memory` | Persistence: store/recall facts, schedule/cancel/list tasks |
| `exec` | Last resort code execution: run (Python/PowerShell), read/write file, clipboard, notify, search_web, fetch URL |
| `speak` | Voice I/O: speak (TTS), ask (dialog), listen (microphone) |

## Anti-Patterns

- ❌ `exec(run)` to launch apps → use `window(open)`
- ❌ `exec(run)` for web browsing → use `browser`
- ❌ `screen(query)` just to verify → tool results already say success/fail
- ❌ `system(search_app)` before `window(open)` → `window(open)` already finds the path
- ❌ Calling `system(state)` multiple times → call once, it returns everything
- ❌ `speak(speak)` for silent notifications → use `exec(notify)`
- ❌ `input(click)` on known elements without coordinates → use `screen(find, click=true)` for UIA targeting
