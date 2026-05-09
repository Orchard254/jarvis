"""
ask_user — blocking user dialog.

Pauses the tool loop and displays a dialog to the user, waits for their
response, then returns the answer as a string.  Jarvis calls this instead of
guessing whenever input is genuinely ambiguous (e.g. "I found 3 files named
'report' — which one do you want?").

Implementation strategy
-----------------------
- tkinter runs on the *main* thread on Windows, but tool calls run on a
  background thread.  We therefore post the dialog work to the main thread
  via a threading.Event + result-slot pattern, and block the calling thread
  until the answer arrives.
- If tkinter is unavailable (headless server / SSH session), we fall back to
  a plain console `input()` prompt so the tool still works.
- A configurable timeout prevents indefinite hangs: after `timeout_seconds`
  the dialog is closed and {"cancelled": True} is returned.

Thread safety note
------------------
`_run_on_main_thread()` is called only when the caller is NOT already on the
main thread.  If Jarvis is running in a purely single-threaded console mode,
the dialog is shown directly.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# ── tkinter availability check ────────────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import simpledialog, messagebox

    _tk_available = True
except ImportError:
    _tk_available = False
    logger.warning("ask_user: tkinter not available — will use console fallback")


# ── internal helper: run dialog on main thread ────────────────────────────────

def _show_dialog(prompt: str, choices: list[str] | None, timeout_seconds: int) -> dict:
    """
    Actually display the dialog window.  Must be called from the main thread
    (or from any thread when tkinter is used in a non-GUI-main context — this
    works fine on Windows as long as a new Tk root is created per call).
    """
    root = tk.Tk()
    root.withdraw()
    root.title("JARVIS")
    root.attributes("-topmost", True)

    result: dict = {"answer": None, "cancelled": False}

    # Auto-close after timeout
    def _on_timeout():
        result["cancelled"] = True
        result["answer"] = None
        root.quit()

    timer_id = root.after(timeout_seconds * 1000, _on_timeout)

    try:
        if choices:
            # Multiple-choice: show buttons
            _choice_dialog(root, prompt, choices, result, timer_id)
        else:
            # Free-text input
            answer = simpledialog.askstring(
                "JARVIS needs input",
                prompt,
                parent=root,
            )
            root.after_cancel(timer_id)
            if answer is None:
                result["cancelled"] = True
            else:
                result["answer"] = answer
    except Exception as exc:
        logger.error(f"ask_user dialog error: {exc}")
        result["cancelled"] = True
    finally:
        try:
            root.destroy()
        except Exception:
            pass

    return result


def _choice_dialog(root: "tk.Tk", prompt: str, choices: list[str],
                   result: dict, timer_id: str) -> None:
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
        # Otherwise use a threading Event to hand off work and wait.
        if threading.current_thread() is threading.main_thread():
            result = _show_dialog(prompt, choices, timeout_seconds)
        else:
            _done = threading.Event()
            _result_slot: dict = {}

            def _worker():
                _result_slot.update(_show_dialog(prompt, choices, timeout_seconds))
                _done.set()

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            _done.wait(timeout=timeout_seconds + 5)
            result = _result_slot if _result_slot else {"answer": None, "cancelled": True}

        return {"success": True, **result}

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
