"""Utility helpers for reliable top-level application window enumeration.

Prevents tabbed applications (Notepad tabs, browser tabs) from being counted
as separate arrangeable windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

try:
    import win32con
    import win32gui
    import win32process
except Exception:  # pragma: no cover
    win32con = None
    win32gui = None
    win32process = None


IGNORED_TITLES = {
    "",
    "Program Manager",
    "Windows Input Experience",
}


@dataclass
class AppWindow:
    hwnd: int
    pid: int
    title: str
    process_name: str | None = None



def _is_real_top_level_window(hwnd: int) -> bool:
    if not win32gui.IsWindowVisible(hwnd):
        return False

    if win32gui.GetParent(hwnd) != 0:
        return False

    ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False

    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    if not (style & win32con.WS_CAPTION):
        return False

    title = win32gui.GetWindowText(hwnd).strip()
    if title in IGNORED_TITLES:
        return False

    try:
        rect = win32gui.GetWindowRect(hwnd)
        if (rect[2] - rect[0]) <= 0 or (rect[3] - rect[1]) <= 0:
            return False
    except Exception:
        return False

    return True



def enumerate_application_windows() -> List[AppWindow]:
    """Return one arrangeable window per application process."""

    if not all([win32gui, win32con, win32process]):
        return []

    discovered: List[AppWindow] = []

    def callback(hwnd, _):
        if not _is_real_top_level_window(hwnd):
            return True

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        title = win32gui.GetWindowText(hwnd).strip()

        discovered.append(
            AppWindow(
                hwnd=hwnd,
                pid=pid,
                title=title,
            )
        )
        return True

    win32gui.EnumWindows(callback, None)

    # Deduplicate by PID so tabbed apps count as one application.
    unique: List[AppWindow] = []
    seen_pids = set()

    for window in discovered:
        if window.pid in seen_pids:
            continue
        seen_pids.add(window.pid)
        unique.append(window)

    return unique
