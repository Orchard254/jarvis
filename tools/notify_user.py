"""
Primitive: notify_user(message, urgency)
Toast fallback to console.
"""

import logging
import warnings

from settings import DESKTOP_TOAST_ENABLED

logger = logging.getLogger(__name__)

_toast_available = False
_toaster = None

if DESKTOP_TOAST_ENABLED:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from win10toast import ToastNotifier

            _toaster = ToastNotifier()
            _toast_available = True
    except ImportError:
        pass


def notify_user(message: str, urgency: str = "normal") -> dict:
    logger.info(f"notify_user [{urgency}]: {message}")
    print(f"\n[JARVIS NOTIFICATION - {urgency.upper()}]: {message}\n")
    if _toast_available and _toaster:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _toaster.show_toast(
                    "JARVIS",
                    message,
                    duration={"low": 3, "normal": 5, "high": 10}.get(urgency, 5),
                    threaded=True,
                )
        except Exception as e:
            logger.warning(f"Toast failed: {e}")
    return {"success": True, "message": message, "urgency": urgency}
