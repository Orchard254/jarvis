"""
ask_user — blocking user dialog.

Pauses the tool loop and displays a dialog to the user, waits for their
response, then returns the answer as a string.  Jarvis calls this instead of
guessing whenever input is genuinely ambiguous (e.g. "I found 3 files named
'report' — which one do you want?").

Implementation strategy
-----------------------
- tkinter runs on the *main* thread on Windows, but tool calls run on a
  background thread.  We use a thread-safe queue to post the dialog work
  to the main thread's event loop via root.after_idle(), and block the
  calling thread until the answer arrives.
- If tkinter is unavailable (headless server / SSH session), we fall back to
  a plain console `input()` prompt so the tool still works.
- A configurable timeout prevents indefinite hangs: after `timeout_seconds`
  the dialog is closed and {"cancelled": True} is returned.

Thread safety note
------------------
Tkinter is NOT thread-safe. All Tk calls must happen on the main thread.
We use root.after() to schedule dialog creation on the main thread's event
loop and a queue.Queue to pass the result back to the calling thread.
"""

from __future__ import annotations

import logging
import queue
import threading

logger = logging.getLogger(__name__)

# ── tkinter availability check ────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import simpledialog

    _tk_available = True
except ImportError:
    _tk_available = False
    logger.warning("ask_user: tkinter not available — will use console fallback")


# ── internal helper: run dialog on main thread ────────────────────────────────

def _show_dialog(prompt: str, choices: list[str] | None, timeout_seconds: int,
                 root: "tk.Tk | None" = None) -> dict:
    """
    Display a dialog window.  Must be called from the Tk thread.

    Parameters
    ----------
    root : tk.Tk or None
        If provided, use this existing root (withdrawn) instead of creating
        a new one.  The root is NOT destroyed on exit.
    """
    own_root = False
    if root is None:
        root = tk.Tk()
        root.withdraw()
        root.title("JARVIS")
        root.attributes("-topmost", True)
        own_root = True

    result: dict = {"answer": None, "cancelled": False}

    def _on_timeout():
        result["cancelled"] = True
        result["answer"] = None
        root.quit()

    timer_id: int = root.after(timeout_seconds * 1000, _on_timeout)

    try:
        if choices:
            _choice_dialog(root, prompt, choices, result, timer_id)
        else:
            answer = simpledialog.askstring(
                "JARVIS needs input",
                prompt,
                parent=root,
            )
            if answer is None:
                result["cancelled"] = True
            else:
                result["answer"] = answer
    except Exception as exc:
        logger.error(f"ask_user dialog error: {exc}")
        result["cancelled"] = True
    finally:
        root.after_cancel(timer_id)
        if own_root:
            try:
                root.destroy()
            except Exception as e:
                logger.debug(f"destroy failed: {e}")

    return result


def _choice_dialog(root: "tk.Tk", prompt: str, choices: list[str],
                   result: dict, timer_id: int) -> None:
    """Show a simple button-choice dialog inside an existing Tk root."""
    dialog = tk.Toplevel(root)
    dialog.title("JARVIS")
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    tk.Label(dialog, text=prompt, wraplength=380, justify="left",
             padx=12, pady=8).pack()

    def _pick(c: str):
        root.after_cancel(timer_id)
        result["answer"] = c
        dialog.destroy()
        root.quit()

    frame = tk.Frame(dialog, padx=12, pady=8)
    frame.pack()
    for c in choices:
        tk.Button(frame, text=c, width=20,
                  command=lambda x=c: _pick(x)).pack(pady=2)

    dialog.protocol("WM_DELETE_WINDOW", lambda: _pick(None))
    root.mainloop()


# ── Persistent Tk root on a dedicated thread ─────────────────────────────────
# Tkinter is NOT thread-safe.  We keep one long-lived root window running on
# a dedicated Tk thread with its own mainloop, and schedule all dialog work
# via root.after().  Results are passed back through a queue.Queue.

_tk_root: "tk.Tk | None" = None
_tk_queue: "queue.Queue" = queue.Queue()
_tk_started = threading.Event()


def _tk_thread_main():
    """Run the persistent Tk event loop on a dedicated thread."""
    global _tk_root
    _tk_root = tk.Tk()
    _tk_root.withdraw()
    _tk_root.title("JARVIS")
    _tk_root.attributes("-topmost", True)
    _tk_root.protocol("WM_DELETE_WINDOW", _tk_root.withdraw)
    _tk_started.set()
    _tk_root.mainloop()


def _ensure_tk_thread():
    """Start the persistent Tk thread if not already running."""
    if not _tk_started.is_set():
        t = threading.Thread(target=_tk_thread_main, daemon=True)
        t.start()
        _tk_started.wait(timeout=5.0)


def _show_dialog_on_tk_thread(prompt, choices, timeout_seconds):
    """Schedule _show_dialog on the Tk thread and block for the result."""
    _ensure_tk_thread()
    q: "queue.Queue" = queue.Queue()

    def _task():
        try:
            result = _show_dialog(prompt, choices, timeout_seconds, root=_tk_root)
            q.put(result)
        except Exception as exc:
            q.put({"answer": None, "cancelled": True, "_error": str(exc)})

    _tk_root.after(0, _task)
    try:
        return q.get(timeout=timeout_seconds + 10)
    except queue.Empty:
        return {"answer": None, "cancelled": True}


# ── public API ────────────────────────────────────────────────────────────────

def ask_user(
    prompt: str,
    choices: list[str] | None = None,
    timeout_seconds: int = 60,
) -> dict:
    """
    Display a dialog and wait for the user's answer.

    Parameters
    ----------
    prompt : str
        The question to display.
    choices : list[str] | None
        If provided, show labelled buttons instead of a free-text field.
    timeout_seconds : int
        Seconds to wait before auto-cancelling (default 60).

    Returns
    -------
    dict
        ``{"success": True, "answer": <str|None>, "cancelled": <bool>}``
    """
    logger.info(f"ask_user: '{prompt}' (timeout={timeout_seconds}s)")

    # ── tkinter path ──────────────────────────────────────────────────────────
    if _tk_available:
        # If we're already on the main thread, run directly.
        # Otherwise use the persistent Tk thread.
        if threading.current_thread() is threading.main_thread():
            result = _show_dialog(prompt, choices, timeout_seconds)
        else:
            result = _show_dialog_on_tk_thread(prompt, choices, timeout_seconds)

        return {"success": True, "answer": result.get("answer"), "cancelled": result.get("cancelled", False)}

    # ── console fallback (headless / no tkinter) ──────────────────────────────
    logger.info("ask_user: using console fallback")
    try:
        if choices:
            lines = [prompt, ""]
            for i, c in enumerate(choices, 1):
                lines.append(f"  {i}. {c}")
            lines.append("")
            display = "\n".join(lines)
            raw = _timed_input(display, timeout_seconds)
            if raw is None:
                return {"success": True, "answer": None, "cancelled": True}
            # Accept index or text
            try:
                idx = int(raw.strip()) - 1
                if 0 <= idx < len(choices):
                    return {"success": True, "answer": choices[idx], "cancelled": False}
            except ValueError:
                pass
            # Match by prefix
            raw_l = raw.strip().lower()
            for c in choices:
                if c.lower().startswith(raw_l):
                    return {"success": True, "answer": c, "cancelled": False}
            return {"success": True, "answer": raw.strip(), "cancelled": False}
        else:
            answer = _timed_input(f"\n[JARVIS] {prompt}\n> ", timeout_seconds)
            if answer is None:
                return {"success": True, "answer": None, "cancelled": True}
            return {"success": True, "answer": answer.strip(), "cancelled": False}
    except Exception as exc:
        logger.error(f"ask_user console fallback error: {exc}")
        return {"success": False, "error": str(exc), "cancelled": True}


def _timed_input(prompt: str, timeout: int) -> str | None:
    """
    input() with a timeout using a background thread.
    Returns None on timeout.
    """
    result_slot: list[str | None] = [None]
    done = threading.Event()

    def _reader():
        try:
            result_slot[0] = input(prompt)
        except Exception:
            result_slot[0] = None
        done.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    done.wait(timeout=timeout)
    return result_slot[0]
