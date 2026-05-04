# Chrome Debug Port Integration Guide

## Overview
JARVIS now supports connecting to existing Chrome browser instances instead of always launching a new session. This prevents CAPTCHA triggers and preserves your login sessions.

## How It Works

### 1. Chrome Launcher Enhancement (`jarvis/tools/apps/launcher.py`)
When you ask JARVIS to open Chrome:
- If Chrome is **not running**: Opens Chrome with `--remote-debugging-port=9222` flag
- If Chrome **is running without debug port**: Restarts Chrome with debug port enabled
- If Chrome **is running with debug port**: Uses the existing instance

### 2. Web Automation Engine (`jarvis/tools/web/automation.py`)
The `WebAutomationEngine` now:
1. Scans for existing Chrome processes with `--remote-debugging-port`
2. Checks common debug ports (9222-9225) for active connections
3. Connects to existing Chrome via Chrome DevTools Protocol (CDP)
4. Falls back to launching a new instance if no existing Chrome found

## Benefits
- ✅ No more "I'm not a robot" CAPTCHA prompts
- ✅ Preserves your logged-in sessions (Google, Amazon, etc.)
- ✅ Opens new tabs in your existing browser window
- ✅ Maintains your browsing history and cookies
- ✅ Faster execution (no need to launch new browser)

## Usage Example
```
You: open chrome search kilimall then open the site and search refurbished phones

Previous behavior:
❌ Launched new Chrome session → CAPTCHA on Kilimall

New behavior:
✅ Detects your running Chrome → Opens new tab → Navigates to Kilimall → Searches
```

## Technical Details

### Debug Port Detection
The system checks for existing Chrome in this order:
1. Socket connection test on ports 9222, 9223, 9224, 9225
2. Process inspection for `--remote-debugging-port=` in command line args
3. If none found, launches Chrome with port 9222

### Connection Flow
```
User Command
    ↓
OpenAppTool (opens Chrome with --remote-debugging-port=9222)
    ↓
SearchAndNavigateTool
    ↓
WebAutomationEngine.ensure_browser(use_existing=True)
    ↓
find_existing_chrome() → finds port 9222
    ↓
connect_over_cdp("http://127.0.0.1:9222")
    ↓
Opens new tab in YOUR existing Chrome
    ↓
Navigates and performs actions
```

## Manual Chrome Launch (Optional)
If you want to manually start Chrome with debug mode before using JARVIS:

**Windows:**
```cmd
chrome.exe --remote-debugging-port=9222 --no-first-run --no-default-browser-check
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222 --no-first-run --no-default-browser-check
```

Then JARVIS will automatically detect and use this instance.

## Troubleshooting

### Issue: Still getting CAPTCHA
**Solution:** Ensure Chrome was launched with debug port. Check Task Manager for Chrome process with `--remote-debugging-port=9222` in command line.

### Issue: "Failed to connect to existing Chrome"
**Solution:** 
1. Close all Chrome windows
2. Let JARVIS restart Chrome with proper flags
3. Or manually launch Chrome with debug port as shown above

### Issue: Multiple Chrome windows opening
**Solution:** This shouldn't happen now. The system connects to existing Chrome and opens new tabs. If it occurs, check logs for connection failures.

## Files Modified
- `jarvis/tools/apps/launcher.py` - Enhanced OpenAppTool for Chrome debug port
- `jarvis/tools/web/automation.py` - Added CDP connection support in WebAutomationEngine
