"""
Notifier Module

Provides desktop notification capabilities for JARVIS.
Uses Windows toast notifications via subprocess.
"""

import logging
import subprocess
import sys
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def send_notification(title: str, message: str, duration_ms: int = 5000) -> bool:
    """
    Send a Windows toast notification.
    
    Args:
        title: Notification title
        message: Notification message body
        duration_ms: How long to show notification (milliseconds)
        
    Returns:
        True if notification was sent, False otherwise
    """
    try:
        # Use PowerShell to send a toast notification
        ps_script = f"""
$toastTitle = "{title}"
$toastMessage = "{message}"

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
    <visual>
        <binding template="ToastText02">
            <text id="1">{title}</text>
            <text id="2">{message}</text>
        </binding>
    </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)

$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("JARVIS").Show($toast)
"""
        
        result = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            logger.info(f"Notification sent: {title}")
            return True
        else:
            logger.warning(f"Notification failed: {result.stderr}")
            # Fallback: print to console
            print(f"[NOTIFICATION] {title}: {message}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Notification timed out")
        print(f"[NOTIFICATION] {title}: {message}")
        return False
        
    except Exception as e:
        logger.error(f"Notification error: {e}")
        print(f"[NOTIFICATION] {title}: {message}")
        return False


class Notifier:
    """
    Notification manager for JARVIS.
    
    Provides configurable notification settings and queuing.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize notifier.
        
        Args:
            config: Configuration dict with notification settings
        """
        self.config = config or {}
        self.enabled = self.config.get('notifications_enabled', True)
        self.default_duration = self.config.get('notification_duration_ms', 5000)
        
        logger.info(f"Notifier initialized (enabled={self.enabled})")
    
    def notify(self, title: str, message: str, duration_ms: Optional[int] = None) -> bool:
        """
        Send a notification.
        
        Args:
            title: Notification title
            message: Notification message
            duration_ms: Optional duration override
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Notifications disabled: {title}")
            return False
            
        duration = duration_ms or self.default_duration
        return send_notification(title, message, duration)
    
    def notify_success(self, action: str, result: str = "") -> bool:
        """Send a success notification."""
        title = "✓ Success"
        message = f"{action} completed" + (f": {result}" if result else "")
        return self.notify(title, message)
    
    def notify_error(self, action: str, error: str = "") -> bool:
        """Send an error notification."""
        title = "✗ Error"
        message = f"{action} failed" + (f": {error}" if error else "")
        return self.notify(title, message, duration_ms=8000)
    
    def notify_info(self, title: str, message: str) -> bool:
        """Send an info notification."""
        return self.notify(f"ℹ {title}", message)
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable notifications."""
        self.enabled = enabled
        logger.info(f"Notifications {'enabled' if enabled else 'disabled'}")
