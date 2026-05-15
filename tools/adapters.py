"""
Tool adapters — maps clean schema tool names to Python implementations.
Each function accepts **kwargs (unpacked by safety executor), returns dict.
"""
import os
import re
import subprocess
import glob as glob_mod
import shutil
import webbrowser
from pathlib import Path

import psutil
import pyautogui
import pygetwindow as gw

from tools.system.execute_code import execute_code as _run_code
from tools.comm.schedule_tool import schedule as _schedule
from tools.voice.listen import listen as _listen
from tools.comm.time_calendar import time_calendar as _time_calendar


def open_app(**kwargs) -> dict:
    name = kwargs.get("name", "")
    try:
        os.startfile(name) if os.name == "nt" else subprocess.Popen([name])
        return {"success": True, "status": f"launched {name}"}
    except Exception:
        pass
    # Fallback: search installed apps via PC index DB
    try:
        db_path = Path(__file__).parent.parent / "indexer" / "db" / "pc_index.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                cur = conn.execute("SELECT name, exe_path FROM apps WHERE name LIKE ?", (f"%{name}%",))
                rows = cur.fetchall()
            finally:
                conn.close()
            for row_name, exe_path in rows:
                resolved = _resolve_exe(exe_path, row_name)
                if resolved:
                    os.startfile(resolved)
                    return {"success": True, "status": f"launched {name}", "path": resolved}
    except Exception:
        pass
    return {"success": False, "error": f"could not find {name}. try list_installed_apps first."}


def _resolve_exe(exe_path: str, app_name: str) -> str | None:
    """Resolve a DB path to an actual executable. Handles folders, quoted paths, and .lnk files."""
    cleaned = exe_path.strip().strip('"')
    p = Path(cleaned)
    if p.suffix.lower() == ".exe" and p.exists():
        return str(p)
    if p.suffix.lower() == ".lnk" and p.exists():
        return str(p)
    if p.is_dir():
        exe_candidate = p / f"{app_name}.exe"
        if exe_candidate.exists():
            return str(exe_candidate)
        for f in p.iterdir():
            if f.suffix.lower() == ".exe":
                return str(f)
    return None


def close_app(**kwargs) -> dict:
    name = kwargs.get("name", "")
    force = kwargs.get("force", False)
    if not re.match(r"^[a-zA-Z0-9._\-, ]+$", name):
        return {"success": False, "error": f"Invalid process name: {name!r}"}
    try:
        args = ["taskkill", "/IM", f"{name}.exe"]
        if force:
            args.append("/F")
        subprocess.run(args, capture_output=True, timeout=5)
        return {"success": True, "status": f"closed {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_active_window(**kwargs) -> dict:
    try:
        win = gw.getActiveWindow()
        if win:
            return {"success": True, "title": win.title, "process": "unknown"}
        return {"success": True, "title": "", "process": ""}
    except Exception as e:
        return {"success": False, "error": str(e)}


def focus_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "")
    try:
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            if target.isMinimized:
                target.restore()
            target.activate()
            # Win32 fallback for reliable foreground switching
            try:
                import ctypes
                hwnd = target._hWnd
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return {"success": True, "status": f"focused {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_running_apps(**kwargs) -> dict:
    try:
        windows = []
        for w in gw.getAllWindows():
            if w.title.strip():
                windows.append({"title": w.title, "visible": w.visible})
        return {"success": True, "windows": windows[:50]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_system_stats(**kwargs) -> dict:
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/" if os.name != "nt" else "C:\\")
        battery = psutil.sensors_battery()
        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_free_gb": round(ram.available / 1e9, 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1e9, 1),
            "battery_percent": round(battery.percent, 1) if battery else None,
            "battery_plugged": battery.power_plugged if battery else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def screenshot(**kwargs) -> dict:
    try:
        region = kwargs.get("region")
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        import io, base64
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return {"success": True, "image_b64": b64, "width": img.width, "height": img.height}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_screen(**kwargs) -> dict:
    try:
        import pytesseract
        from PIL import Image
        region = kwargs.get("region")
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        text = pytesseract.image_to_string(img)
        return {"success": True, "text": text.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click(**kwargs) -> dict:
    try:
        x, y = kwargs.get("x"), kwargs.get("y")
        button = kwargs.get("button", "left")
        pyautogui.click(x, y, button=button)
        return {"success": True, "status": f"clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def type_text(**kwargs) -> dict:
    try:
        text = kwargs.get("text", "")
        pyautogui.write(text)
        if kwargs.get("enter"):
            pyautogui.press("enter")
        return {"success": True, "typed": len(text)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def press_keys(**kwargs) -> dict:
    try:
        keys = kwargs.get("keys", "").lower().replace(" ", "").split("+")
        pyautogui.hotkey(*keys)
        return {"success": True, "keys": kwargs.get("keys")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def scroll(**kwargs) -> dict:
    try:
        clicks = kwargs.get("clicks", -3)
        pyautogui.scroll(clicks)
        return {"success": True, "clicks": clicks}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_files(**kwargs) -> dict:
    try:
        pattern = kwargs.get("pattern", "")
        location = kwargs.get("location", str(Path.home() / "Desktop"))
        # Prevent path traversal
        location_resolved = Path(location).resolve()
        home = Path.home().resolve()
        if not str(location_resolved).startswith(str(home)):
            return {"success": False, "error": f"Location must be under user home directory: {home}"}
        max_results = kwargs.get("max_results", 20)
        matches = []
        search_path = location_resolved / "**" / pattern
        for f in glob_mod.glob(str(search_path), recursive=True)[:max_results]:
            p = Path(f)
            try:
                size = p.stat().st_size if p.is_file() else 0
            except OSError:
                size = 0
            matches.append({"name": p.name, "path": str(p), "size": size})
        return {"success": True, "results": matches, "count": len(matches)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        os.startfile(path)
        return {"success": True, "status": f"opened {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        max_chars = kwargs.get("max_chars", 5000)
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        return {"success": True, "content": content, "truncated": len(content) >= max_chars}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "status": f"wrote {len(content)} chars to {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        if os.path.isdir(path):
            try:
                os.rmdir(path)
            except OSError:
                return {"success": False, "error": f"Directory not empty: {path}. Use execute_code with caution for recursive deletes."}
        else:
            os.remove(path)
        return {"success": True, "status": f"deleted {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(**kwargs) -> dict:
    try:
        src = kwargs.get("source", "")
        dst = kwargs.get("destination", "")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.move(src, dst)
        return {"success": True, "status": f"moved {src} to {dst}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_python(**kwargs) -> dict:
    return _run_code(
        code=kwargs.get("code", ""),
        language="python",
        timeout=kwargs.get("timeout", 30),
    )


def execute_code(**kwargs) -> dict:
    return _run_code(
        code=kwargs.get("code", ""),
        language=kwargs.get("language", "python"),
        background=kwargs.get("background", False),
        action=kwargs.get("action", "run"),
        pid=kwargs.get("pid", 0),
        timeout=kwargs.get("timeout", 60),
    )


_WEB_SEARCH_TEMPLATE = """\
import json, urllib.request, urllib.parse
q = urllib.parse.quote({query_repr})
url = f"https://api.duckduckgo.com/?q={{q}}&format=json&no_html=1"
try:
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    results = []
    for topic in data.get("RelatedTopics", [])[:{n_repr}]:
        if "Text" in topic:
            results.append({{"title": topic.get("Text", "")[:100], "url": topic.get("FirstURL", "")}})
    print(json.dumps({{"results": results, "count": len(results)}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""


def web_search(**kwargs) -> dict:
    query = kwargs.get("query", "")
    n = kwargs.get("max_results", 5)
    code = _WEB_SEARCH_TEMPLATE.format(
        query_repr=repr(query),
        n_repr=repr(n),
    )
    return _run_code(code=code, language="python", timeout=15)


def open_url(**kwargs) -> dict:
    try:
        url = kwargs.get("url", "")
        webbrowser.open(url)
        return {"success": True, "status": f"opened {url}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


_FETCH_TEMPLATE = """\
import urllib.request, html.parser
class P(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
p = P()
try:
    resp = urllib.request.urlopen({url_repr}, timeout=10)
    p.feed(resp.read().decode("utf-8", errors="replace"))
    result = " ".join(p.text)[:{n_repr}]
    print(result)
except Exception as e:
    print(f"Error: {{e}}")
"""


def fetch_page(**kwargs) -> dict:
    url = kwargs.get("url", "")
    n = kwargs.get("max_chars", 10000)
    code = _FETCH_TEMPLATE.format(
        url_repr=repr(url),
        n_repr=repr(n),
    )
    return _run_code(code=code, language="python", timeout=15)


def store_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="store", key=kwargs.get("key"), value=kwargs.get("value"))


def retrieve_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="recall", key=kwargs.get("key"))


def forget_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="forget", key=kwargs.get("key"))


def search_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="search", query=kwargs.get("query"), limit=kwargs.get("limit", 10))


def send_message(**kwargs) -> dict:
    from tools.comm.send_message import send_message as _send
    return _send(
        to=kwargs.get("to", ""),
        subject=kwargs.get("subject", ""),
        body=kwargs.get("body", ""),
    )


def speak(**kwargs) -> dict:
    from tools.voice.speak import speak as _speak
    return _speak(text=kwargs.get("text", ""), blocking=True)


def minimize_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "")
    try:
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            target.minimize()
            return {"success": True, "status": f"minimized {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def maximize_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "")
    try:
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            target.maximize()
            return {"success": True, "status": f"maximized {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def double_click(**kwargs) -> dict:
    try:
        x, y = kwargs.get("x"), kwargs.get("y")
        pyautogui.doubleClick(x, y)
        return {"success": True, "status": f"double-clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def right_click(**kwargs) -> dict:
    try:
        x, y = kwargs.get("x"), kwargs.get("y")
        pyautogui.rightClick(x, y)
        return {"success": True, "status": f"right-clicked ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_mouse(**kwargs) -> dict:
    try:
        x, y = kwargs.get("x"), kwargs.get("y")
        pyautogui.moveTo(x, y)
        return {"success": True, "status": f"moved to ({x}, {y})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def drag(**kwargs) -> dict:
    try:
        sx, sy = kwargs.get("start_x"), kwargs.get("start_y")
        ex, ey = kwargs.get("end_x"), kwargs.get("end_y")
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy)
        return {"success": True, "status": f"dragged from ({sx},{sy}) to ({ex},{ey})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_volume(**kwargs) -> dict:
    level = kwargs.get("level", 0)
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        interface = devices.EndpointVolume
        interface.SetMasterVolumeLevelScalar(max(0, min(1, level / 100)), None)
        return {"success": True, "status": f"volume set to {level}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_process_info(**kwargs) -> dict:
    name = kwargs.get("name", "")
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]):
            if name.lower() in p.info["name"].lower():
                procs.append(p.info)
        return {"success": True, "processes": procs[:10], "count": len(procs)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def kill_process(**kwargs) -> dict:
    name = kwargs.get("name", "")
    if not re.match(r"^[a-zA-Z0-9._\-, ]+$", name):
        return {"success": False, "error": f"Invalid process name: {name!r}"}
    try:
        subprocess.run(["taskkill", "/IM", f"{name}.exe", "/F"], capture_output=True, timeout=5)
        return {"success": True, "status": f"killed {name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_file(**kwargs) -> dict:
    url = kwargs.get("url", "")
    path = kwargs.get("path", "")
    try:
        import urllib.request
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        urllib.request.urlretrieve(url, path)
        return {"success": True, "status": f"downloaded to {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def detect_ui_elements(**kwargs) -> dict:
    try:
        import pytesseract
        from PIL import Image
        region = kwargs.get("region")
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        elements = []
        for i in range(len(data["text"])):
            if data["text"][i].strip():
                elements.append({
                    "text": data["text"][i],
                    "x": data["left"][i], "y": data["top"][i],
                    "w": data["width"][i], "h": data["height"][i],
                })
        return {"success": True, "elements": elements, "count": len(elements)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_memory(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="store", key=kwargs.get("key"), value=kwargs.get("value"))


def summarize_session(**kwargs) -> dict:
    from tools.memory import memory
    return memory(action="summary", limit=kwargs.get("limit", 10))


def get_battery(**kwargs) -> dict:
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return {"success": True, "battery_percent": None, "plugged_in": None, "status": "No battery detected"}
        return {
            "success": True,
            "battery_percent": round(battery.percent, 1),
            "plugged_in": battery.power_plugged,
            "charging": battery.power_plugged if battery.power_plugged is not None else False,
            "status": f"{battery.percent:.0f}% {'plugged in' if battery.power_plugged else 'on battery'}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def switch_window(**kwargs) -> dict:
    title = kwargs.get("title", "")
    process = kwargs.get("process", "")
    try:
        target = None
        if title:
            for w in gw.getWindowsWithTitle(title):
                target = w; break
        if not target and process:
            for w in gw.getAllWindows():
                if process.lower() in w.title.lower():
                    target = w; break
        if target:
            target.activate()
            return {"success": True, "status": f"switched to {target.title}"}
        return {"success": False, "error": "window not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def lock_screen(**kwargs) -> dict:
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return {"success": True, "status": "screen locked"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def shutdown(**kwargs) -> dict:
    try:
        import ctypes
        # Confirm with user first — no silent shutdown
        confirmed = kwargs.get("_confirmed", False)
        if not confirmed:
            return {"success": False, "error": "Shutdown requires explicit user confirmation. Call again with _confirmed=True after asking the user."}
        ctypes.windll.user32.ExitWindowsEx(0x00000001 | 0x00000004, 0)  # EWX_SHUTDOWN | EWX_FORCE
        return {"success": True, "status": "shutting down"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def restart(**kwargs) -> dict:
    try:
        import ctypes
        confirmed = kwargs.get("_confirmed", False)
        if not confirmed:
            return {"success": False, "error": "Restart requires explicit user confirmation. Call again with _confirmed=True after asking the user."}
        ctypes.windll.user32.ExitWindowsEx(0x00000002 | 0x00000004, 0)  # EWX_REBOOT | EWX_FORCE
        return {"success": True, "status": "restarting"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(**kwargs) -> dict:
    try:
        path = kwargs.get("path", "")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            pass
        return {"success": True, "status": f"created {path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def data_analysis(**kwargs) -> dict:
    return _run_code(
        code=kwargs.get("data", "") + "\nimport pandas as pd\n" + kwargs.get("operations", "describe()"),
        language="python",
        timeout=30,
    )


def list_installed_apps(**kwargs) -> dict:
    query = kwargs.get("query", "")
    try:
        db_path = Path(__file__).parent.parent / "indexer" / "db" / "pc_index.db"
        if not db_path.exists():
            return {"success": False, "error": "app index not built yet - try again in a minute"}
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        try:
            if query:
                cur = conn.execute("SELECT name, exe_path, version FROM apps WHERE name LIKE ?", (f"%{query}%",))
            else:
                cur = conn.execute("SELECT name, exe_path, version FROM apps ORDER BY name")
            apps = []
            seen = set()
            for row_name, exe_path, version in cur.fetchall()[:100]:
                resolved = _resolve_exe(exe_path, row_name)
                if resolved and resolved not in seen:
                    seen.add(resolved)
                    apps.append({"name": row_name, "path": resolved, "version": version})
        finally:
            conn.close()
        return {"success": True, "apps": apps[:50], "count": len(apps)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_brightness(**kwargs) -> dict:
    level = max(0, min(100, int(kwargs.get("level", 50))))
    try:
        subprocess.run(
            ["powershell", "-command",
             f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"],
            capture_output=True, timeout=10
        )
        return {"success": True, "status": f"brightness set to {level}%"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def minimize_all_except(**kwargs) -> dict:
    exclude = [s.lower() for s in kwargs.get("exclude_titles", [])]
    try:
        minimized = 0
        skipped = 0
        for w in gw.getAllWindows():
            title = w.title.strip().lower()
            if not title:
                continue
            if any(excl in title for excl in exclude):
                skipped += 1
                continue
            try:
                w.minimize()
                minimized += 1
            except Exception:
                pass
        return {"success": True, "minimized": minimized, "skipped": skipped, "status": f"minimized {minimized} windows, kept {skipped} open"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def vision_query(**kwargs) -> dict:
    import base64, io
    question = kwargs.get("question", "")
    region = kwargs.get("region")
    # Require explicit opt-in for remote screen capture
    if not kwargs.get("_consent", False):
        return {"success": False, "error": "Screen capture requires user consent. Ask the user for permission and retry with _consent=True."}
    try:
        if region:
            img = pyautogui.screenshot(region=(region["left"], region["top"], region["width"], region["height"]))
        else:
            img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        import requests
        from settings import LLM_VISION_MODEL, LLM_BASE_URL, OLLAMA_API_KEY
        payload = {
            "model": LLM_VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": question,
                "images": [b64],
            }],
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if OLLAMA_API_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
        url = LLM_BASE_URL.rstrip("/")
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if "choices" in data:
            answer = data["choices"][0].get("message", {}).get("content", "")
        else:
            answer = data.get("message", {}).get("content", "")
        return {"success": True, "answer": answer.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def schedule(**kwargs) -> dict:
    return _schedule(
        action=kwargs.get("action", ""),
        command=kwargs.get("command"),
        when=kwargs.get("when"),
        task_id=kwargs.get("task_id"),
    )


def listen(**kwargs) -> dict:
    return _listen(
        prompt=kwargs.get("prompt"),
        timeout_seconds=kwargs.get("timeout_seconds", 10),
        speak_prompt=kwargs.get("speak_prompt", True),
    )


def time_calendar(**kwargs) -> dict:
    return _time_calendar(
        action=kwargs.get("action", ""),
        subject=kwargs.get("subject", ""),
        start=kwargs.get("start", ""),
        end=kwargs.get("end", ""),
        location=kwargs.get("location", ""),
        body=kwargs.get("body", ""),
        all_day=kwargs.get("all_day", False),
        days=kwargs.get("days", 7),
        date=kwargs.get("date", ""),
    )
