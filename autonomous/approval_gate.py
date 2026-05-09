"""
Approval Gate: Blocking confirmation flow for high-risk autonomous tasks.

High-confidence tasks (>= 0.95) are auto-approved.
All others prompt the user via CLI with a configurable timeout.
If the timeout expires without a response, the task is denied (fail-safe).
"""

import logging
import threading

from core.console import cli_input

logger = logging.getLogger(__name__)

# Words accepted as approval / denial
_APPROVE_WORDS = {"yes", "y", "approve", "ok", "sure"}
_DENY_WORDS = {"no", "n", "cancel", "deny", "reject", "skip"}

# Auto-approve threshold — tasks with confidence >= this skip the gate
AUTO_APPROVE_THRESHOLD = 0.95


class ApprovalGate:
    """
    Thread-safe, blocking approval gate for high-risk autonomous tasks.

    Usage::

        gate = ApprovalGate(timeout_seconds=60)
        approved = gate.request(task_id, command, confidence)
        if approved:
            run_task()
        else:
            cancel_task()
    """

    def __init__(self, timeout_seconds: int = 60):
        """
        Args:
            timeout_seconds: Seconds to wait for user input before auto-denying.
                             Default is 60 s to keep the scheduler responsive.
        """
        self.timeout = timeout_seconds

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def request(self, task_id: str, command: str, confidence: float) -> bool:
        """
        Request user approval for a high-risk autonomous task.

        Auto-approves when confidence >= AUTO_APPROVE_THRESHOLD so that
        routine, high-certainty tasks keep flowing without human intervention.

        For everything else the method **blocks** until the user types a
        response *or* ``self.timeout`` seconds elapse (deny on timeout).

        Args:
            task_id:    Unique identifier for the pending task.
            command:    The command / action about to be executed.
            confidence: Model confidence score in [0, 1].

        Returns:
            True  — approved (auto or manual)
            False — denied (user said no, or timeout expired)
        """
        # ── Fast path: high-confidence tasks auto-approve ──────────────
        if confidence >= AUTO_APPROVE_THRESHOLD:
            logger.info(
                f"approval_gate: task '{task_id[:8]}' auto-approved "
                f"(confidence={confidence:.2%})"
            )
            return True

        # ── Prompt the user ────────────────────────────────────────────
        _print_approval_prompt(task_id, command, confidence, self.timeout)

        approved = self._wait_for_input(task_id)

        if approved:
            logger.info(f"approval_gate: task '{task_id[:8]}' APPROVED by user")
        else:
            logger.warning(f"approval_gate: task '{task_id[:8]}' DENIED (user/timeout)")

        return approved

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _wait_for_input(self, task_id: str) -> bool:
        """
        Block until the user types a recognised response or the timeout fires.

        Uses a background thread so we can enforce the deadline even when
        ``input()`` is blocking.  The result is communicated via a
        ``threading.Event`` pair.
        """
        result_holder: list[bool] = []
        done_event = threading.Event()

        def _reader():
            try:
                raw = cli_input("> ").strip().lower()
                if raw in _APPROVE_WORDS:
                    result_holder.append(True)
                elif raw in _DENY_WORDS:
                    result_holder.append(False)
                else:
                    # Unrecognised input → deny (fail-safe)
                    print(
                        f"  ⚠  Unrecognised response '{raw}'. "
                        "Treating as NO (task denied)."
                    )
                    result_holder.append(False)
            except EOFError:
                # Non-interactive environment — deny silently
                result_holder.append(False)
            finally:
                done_event.set()

        reader_thread = threading.Thread(
            target=_reader, daemon=True, name="approval-reader"
        )
        reader_thread.start()

        timed_out = not done_event.wait(timeout=self.timeout)

        if timed_out:
            print(
                f"\n  ⏰  No response within {self.timeout}s — "
                "task DENIED (fail-safe timeout)."
            )
            logger.warning(
                f"approval_gate: task '{task_id[:8]}' timed out after "
                f"{self.timeout}s — denied"
            )
            return False

        return result_holder[0] if result_holder else False


# ------------------------------------------------------------------ #
#  Module-level helpers                                               #
# ------------------------------------------------------------------ #


def _print_approval_prompt(
    task_id: str, command: str, confidence: float, timeout: int
) -> None:
    """Print a clear, formatted approval prompt to stdout."""
    border = "─" * 56
    print(f"\n┌{border}┐")
    print(f"│  🤖  AUTONOMOUS TASK — APPROVAL REQUIRED{' ' * 15}│")
    print(f"├{border}┤")
    print(f"│  Task ID   : {task_id[:8]}{'':>42}│")
    # Wrap long commands across multiple lines
    for i, chunk in enumerate(_wrap(command, width=42)):
        label = "│  Command   : " if i == 0 else "│             "
        print(f"{label}{chunk:<42}│")
    print(f"│  Confidence: {confidence:.0%}{'':>42}│")
    print(f"│  Timeout   : {timeout}s{'':>43}│")
    print(f"├{border}┤")
    print(f"│  Type  yes / y / approve   to ALLOW the task{'':>9}│")
    print(f"│  Type  no  / n / cancel    to DENY  the task{'':>9}│")
    print(f"└{border}┘")


def _wrap(text: str, width: int) -> list[str]:
    """Split text into chunks of at most ``width`` characters."""
    chunks: list[str] = []
    while len(text) > width:
        chunks.append(text[:width])
        text = text[width:]
    chunks.append(text)
    return chunks
