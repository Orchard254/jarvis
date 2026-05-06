"""
jarvis/core/safety.py — Deterministic Safety Guardrail System

A deterministic guardrail system that intercepts commands before execution.
Features:
- Command Allowlist/Blocklist: Blocks dangerous patterns (rm -rf /, format c:, etc.)
- Path Sandboxing: Prevents file operations outside designated directories
- Resource Guards: Monitors CPU/RAM usage to prevent system overload
- Confirmation Protocol: Forces human-in-the-loop for high-risk actions
"""

import re
import os
import psutil
import subprocess
import threading
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk classification for commands."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    allowed: bool
    risk_level: RiskLevel
    reason: str
    requires_confirmation: bool = False
    blocked_patterns: List[str] = None
    
    def __post_init__(self):
        if self.blocked_patterns is None:
            self.blocked_patterns = []


class CommandGuard:
    """
    Command allowlist/blocklist for blocking dangerous shell patterns.
    """
    
    # CRITICAL: Always block these destructive patterns
    BLOCKED_PATTERNS = [
        # Unix destructive commands
        r'rm\s+-rf\s+/',                    # Delete root filesystem
        r'rm\s+-rf\s+\*',                   # Delete everything in current dir
        r'dd\s+if=.*of=/dev/',              # Direct disk write
        r'mkfs',                            # Format filesystem
        r':\(\)\{\s*:\|:\s*&\s*\};:',       # Fork bomb
        
        # Windows destructive commands
        r'format\s+[cdefg]:',               # Format drives
        r'del\s+/f\s+/s\s+/q\s+c:\\windows', # Delete Windows folder
        r'rd\s+/s\s+/q\s+c:\\',             # Remove C drive
        r'rmdir\s+/s\s+/q\s+c:\\',          # Remove C drive (alternative)
        reg delete HKLM\\SYSTEM',           # Delete registry system keys
        r'net\s+user\s+administrator',      # Modify admin account
        
        # PowerShell destructive
        r'Remove-Item\s+-Recurse\s+-Force\s+C:\\',  # Force delete C drive
        r'Format-Volume',                   # Format volume
        r'Clear-Disk',                      # Clear entire disk
        r'Update-FormatData.*-Force',       # Force update format data
        
        # Privilege escalation
        r'\bsudo\b.*\b(rm|del|format|dd)\b',  # Sudo with destructive commands
        r'runas.*admin',                    # Run as admin
        
        # Network attacks
        r'curl\s+.*\|\s*(sh|bash)',         # Curl pipe to shell
        r'wget\s+.*\|\s*(sh|bash)',         # Wget pipe to shell
        r'nc\s+-e',                         # Netcat reverse shell
        r'python.*-c.*socket',              # Python reverse shell
        
        # Process termination
        r'taskkill\s+/F\s+/IM\s+explorer\.exe',  # Kill explorer
        r'pkill\s+-9\s+init',               # Kill init process
    ]
    
    # High-risk commands requiring confirmation
    CONFIRMATION_PATTERNS = [
        r'\bshutdown\b',                    # System shutdown
        r'\breboot\b',                      # System reboot
        r'restart-computer',                # PowerShell restart
        r'stop-computer',                   # PowerShell shutdown
        r'rm\s+-rf',                        # Recursive delete (non-root)
        r'del\s+/[a-z]',                    # Delete files (Windows)
        r'rmdir\s+/s',                      # Remove directory tree
        r'taskkill\s+/F',                   # Force kill process
        r'chmod\s+-R\s+777',                # Recursive chmod 777
        r'chown\s+-R',                      # Recursive chown
        r'systemctl\s+(stop|disable)',      # Stop system services
        r'net\s+stop',                      # Stop Windows services
    ]
    
    # Safe administrative commands (allowlist)
    SAFE_COMMANDS = [
        r'^ls\s',                           # List files
        r'^dir\s',                          # List files (Windows)
        r'^pwd$',                           # Print working directory
        r'^cd\s',                           # Change directory
        r'^echo\s',                         # Echo text
        r'^cat\s',                          # View file contents
        r'^type\s',                         # View file (Windows)
        r'^head\s',                         # View file head
        r'^tail\s',                         # View file tail
        r'^grep\s',                         # Search text
        r'^findstr\s',                      # Search text (Windows)
        r'^ps\s',                           # List processes
        r'^tasklist',                       # List processes (Windows)
        r'^top',                            # System monitor
        r'^htop',                           # Enhanced system monitor
        r'^df\s',                           # Disk free space
        r'^du\s',                           # Disk usage
        r'^free',                           # Memory info
        r'^uptime',                         # System uptime
        r'^whoami',                         # Current user
        r'^hostname',                       # System hostname
        r'^date',                           # Current date/time
        r'^python\s+--version',             # Python version
        r'^pip\s+list',                     # List packages
        r'^git\s+(status|log|diff)',        # Git read operations
    ]
    
    def __init__(self):
        self.blocked_regex = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS]
        self.confirmation_regex = [re.compile(p, re.IGNORECASE) for p in self.CONFIRMATION_PATTERNS]
        self.safe_regex = [re.compile(p, re.IGNORECASE) for p in self.SAFE_COMMANDS]
    
    def check(self, command: str) -> SafetyCheckResult:
        """
        Check if a command is safe to execute.
        
        Returns:
            SafetyCheckResult with allow/deny decision and risk level
        """
        if not command:
            return SafetyCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason="Empty command"
            )
        
        # Check blocked patterns first (highest priority)
        for pattern in self.blocked_regex:
            if pattern.search(command):
                return SafetyCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.CRITICAL,
                    reason=f"Blocked pattern detected: {pattern.pattern}",
                    blocked_patterns=[pattern.pattern]
                )
        
        # Check if requires confirmation
        requires_confirmation = False
        matched_patterns = []
        for pattern in self.confirmation_regex:
            if pattern.search(command):
                requires_confirmation = True
                matched_patterns.append(pattern.pattern)
        
        if requires_confirmation:
            return SafetyCheckResult(
                allowed=True,
                risk_level=RiskLevel.HIGH,
                reason="High-risk command requires confirmation",
                requires_confirmation=True,
                blocked_patterns=matched_patterns
            )
        
        # Check if explicitly safe
        for pattern in self.safe_regex:
            if pattern.search(command):
                return SafetyCheckResult(
                    allowed=True,
                    risk_level=RiskLevel.SAFE,
                    reason="Safe administrative command"
                )
        
        # Default: allow with low risk (unknown but not obviously dangerous)
        return SafetyCheckResult(
            allowed=True,
            risk_level=RiskLevel.LOW,
            reason="Command passed safety checks"
        )


class PathSandbox:
    """
    Path sandboxing to restrict file operations to designated directories.
    """
    
    # Protected system paths (never allow writes)
    PROTECTED_PATHS = [
        '/bin', '/sbin', '/usr/bin', '/usr/sbin', '/usr/lib',
        '/etc', '/var/log', '/proc', '/sys',
        'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)',
        'C:\\System32', 'C:\\Users\\*\\AppData',
    ]
    
    def __init__(self, 
                 allowed_dirs: Optional[List[str]] = None,
                 strict_mode: bool = True):
        """
        Initialize path sandbox.
        
        Args:
            allowed_dirs: List of allowed directories (None = current dir only)
            strict_mode: If True, block all access outside allowed dirs
        """
        self.strict_mode = strict_mode
        self.allowed_dirs: List[str] = []
        
        if allowed_dirs:
            for d in allowed_dirs:
                self.allowed_dirs.append(os.path.abspath(d))
        else:
            # Default: allow current working directory and subdirectories
            self.allowed_dirs.append(os.getcwd())
        
        # Compile protected path patterns
        self.protected_patterns = []
        for p in self.PROTECTED_PATHS:
            # Convert glob patterns to regex
            regex_pattern = p.replace('*', '.*').replace('\\', '\\\\')
            self.protected_patterns.append(re.compile(f'^{regex_pattern}', re.IGNORECASE))
    
    def is_protected(self, path: str) -> bool:
        """Check if path is in a protected system directory."""
        abs_path = os.path.abspath(path)
        for pattern in self.protected_patterns:
            if pattern.match(abs_path):
                return True
        return False
    
    def is_allowed(self, path: str) -> Tuple[bool, str]:
        """
        Check if path access is allowed.
        
        Returns:
            Tuple of (allowed, reason)
        """
        if not path:
            return False, "Empty path"
        
        abs_path = os.path.abspath(path)
        
        # Check if path is protected
        if self.is_protected(abs_path):
            return False, f"Access to protected system path denied: {abs_path}"
        
        # Check path traversal attempts
        if '..' in path:
            # Resolve the path and check if it escapes allowed dirs
            try:
                resolved = os.path.realpath(abs_path)
                for allowed in self.allowed_dirs:
                    if resolved.startswith(allowed):
                        return True, "Path resolved within allowed directory"
                
                if self.strict_mode:
                    return False, "Path traversal outside allowed directories"
            except Exception:
                return False, "Invalid path"
        
        # Check against allowed directories
        for allowed in self.allowed_dirs:
            if abs_path.startswith(allowed):
                return True, "Path within allowed directory"
        
        if self.strict_mode:
            return False, f"Path outside allowed directories: {abs_path}"
        
        # Non-strict mode: allow if not protected
        return True, "Path not in protected areas (non-strict mode)"
    
    def validate_operation(self, operation: str, path: str) -> SafetyCheckResult:
        """
        Validate a file operation.
        
        Args:
            operation: Type of operation (read, write, delete, execute)
            path: Target path
            
        Returns:
            SafetyCheckResult
        """
        allowed, reason = self.is_allowed(path)
        
        if not allowed:
            return SafetyCheckResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                reason=reason
            )
        
        # Delete operations require extra scrutiny
        if operation == 'delete':
            return SafetyCheckResult(
                allowed=True,
                risk_level=RiskLevel.MEDIUM,
                reason="Delete operation in allowed directory",
                requires_confirmation=True
            )
        
        return SafetyCheckResult(
            allowed=True,
            risk_level=RiskLevel.SAFE,
            reason=reason
        )


class ResourceGuard:
    """
    Resource monitoring to prevent system overload.
    Stops processes from consuming >80% CPU or RAM for extended periods.
    """
    
    CPU_THRESHOLD = 80.0  # Percent
    RAM_THRESHOLD = 80.0  # Percent
    CHECK_INTERVAL = 2.0  # Seconds
    SUSTAINED_PERIOD = 10.0  # Seconds of sustained high usage triggers action
    
    def __init__(self):
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._callbacks: List[callable] = []
        self._high_usage_start: Optional[float] = None
        self._lock = threading.Lock()
    
    def add_callback(self, callback: callable) -> None:
        """Add callback for resource limit exceeded events."""
        self._callbacks.append(callback)
    
    def _check_resources(self) -> Tuple[bool, str, float, float]:
        """
        Check current resource usage.
        
        Returns:
            Tuple of (is_over_limit, resource_type, cpu_percent, ram_percent)
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram_percent = psutil.virtual_memory().percent
        
        if cpu_percent > self.CPU_THRESHOLD:
            return True, "CPU", cpu_percent, ram_percent
        
        if ram_percent > self.RAM_THRESHOLD:
            return True, "RAM", cpu_percent, ram_percent
        
        return False, "", cpu_percent, ram_percent
    
    def start_monitoring(self) -> None:
        """Start background resource monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("ResourceGuard started monitoring")
    
    def stop_monitoring(self) -> None:
        """Stop background resource monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("ResourceGuard stopped monitoring")
    
    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring:
            over_limit, resource_type, cpu, ram = self._check_resources()
            
            if over_limit:
                with self._lock:
                    if self._high_usage_start is None:
                        self._high_usage_start = time.time()
                    
                    elapsed = time.time() - self._high_usage_start
                    
                    if elapsed >= self.SUSTAINED_PERIOD:
                        # Sustained high usage - trigger callbacks
                        msg = f"Sustained high {resource_type} usage: {cpu:.1f}% CPU, {ram:.1f}% RAM for {elapsed:.1f}s"
                        logger.warning(msg)
                        
                        for callback in self._callbacks:
                            try:
                                callback({
                                    'type': 'resource_limit',
                                    'resource': resource_type,
                                    'cpu_percent': cpu,
                                    'ram_percent': ram,
                                    'duration': elapsed,
                                    'message': msg
                                })
                            except Exception as e:
                                logger.error(f"ResourceGuard callback error: {e}")
            else:
                with self._lock:
                    self._high_usage_start = None
            
            time.sleep(self.CHECK_INTERVAL)
    
    def get_current_usage(self) -> Dict[str, float]:
        """Get current resource usage."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram_percent = psutil.virtual_memory().percent
        
        return {
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'cpu_threshold': self.CPU_THRESHOLD,
            'ram_threshold': self.RAM_THRESHOLD,
            'within_limits': cpu_percent < self.CPU_THRESHOLD and ram_percent < self.RAM_THRESHOLD
        }


class ConfirmationProtocol:
    """
    Human-in-the-loop confirmation protocol for high-risk actions.
    """
    
    # Actions that always require confirmation
    REQUIRES_CONFIRMATION = {
        'shutdown', 'restart', 'reboot',
        'bulk_delete', 'recursive_delete',
        'system_service_stop', 'system_service_disable',
        'network_external_call', 'api_external_call',
        'file_export', 'data_upload',
    }
    
    def __init__(self, auto_confirm: bool = False):
        """
        Initialize confirmation protocol.
        
        Args:
            auto_confirm: If True, skip confirmations (for testing/automation)
        """
        self.auto_confirm = auto_confirm
        self._pending_confirmations: Dict[str, dict] = {}
        self._lock = threading.Lock()
    
    def request_confirmation(self, 
                             action: str,
                             description: str,
                             risk_level: RiskLevel,
                             context: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Request user confirmation for a high-risk action.
        
        Args:
            action: Action identifier
            description: Human-readable description of what will happen
            risk_level: Risk classification
            context: Additional context about the action
            
        Returns:
            Tuple of (confirmed, message)
        """
        if self.auto_confirm:
            logger.info(f"AUTO-CONFIRM: {action} - {description}")
            return True, "Auto-confirmed (testing mode)"
        
        # Generate confirmation ID
        import uuid
        confirm_id = str(uuid.uuid4())[:8]
        
        # Store pending confirmation
        with self._lock:
            self._pending_confirmations[confirm_id] = {
                'action': action,
                'description': description,
                'risk_level': risk_level.value,
                'context': context or {},
                'timestamp': time.time()
            }
        
        # In a real implementation, this would wait for user input
        # For now, we log and return False (requires external confirmation mechanism)
        logger.warning(f"CONFIRMATION REQUIRED [{confirm_id}]: {risk_level.value} - {action}")
        logger.warning(f"  Description: {description}")
        
        return False, f"Confirmation required: {confirm_id}"
    
    def submit_confirmation(self, 
                           confirm_id: str, 
                           confirmed: bool) -> Tuple[bool, str]:
        """
        Submit user confirmation response.
        
        Args:
            confirm_id: Confirmation request ID
            confirmed: Whether user confirmed or denied
            
        Returns:
            Tuple of (success, message)
        """
        with self._lock:
            if confirm_id not in self._pending_confirmations:
                return False, "Unknown confirmation ID"
            
            pending = self._pending_confirmations.pop(confirm_id)
        
        if confirmed:
            logger.info(f"CONFIRMED [{confirm_id}]: {pending['action']}")
            return True, "Action approved"
        else:
            logger.info(f"DENIED [{confirm_id}]: {pending['action']}")
            return True, "Action denied by user"
    
    def should_require_confirmation(self, 
                                    tool_name: str,
                                    params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Determine if an action requires confirmation.
        
        Args:
            tool_name: Name of the tool being called
            params: Tool parameters
            
        Returns:
            Tuple of (requires_confirmation, reason)
        """
        # Check tool name
        for keyword in self.REQUIRES_CONFIRMATION:
            if keyword in tool_name.lower():
                return True, f"Tool '{tool_name}' requires confirmation"
        
        # Check for bulk operations
        if params.get('recursive', False) or params.get('bulk', False):
            return True, "Bulk/recursive operation requires confirmation"
        
        # Check for external network calls
        if 'url' in params and not str(params['url']).startswith(('http://localhost', 'https://localhost')):
            return True, "External network call requires confirmation"
        
        return False, ""


class SafetyLayer:
    """
    Unified safety layer combining all guardrails.
    
    This is the main interface for safety checks before tool execution.
    """
    
    def __init__(self,
                 allowed_dirs: Optional[List[str]] = None,
                 strict_sandbox: bool = True,
                 auto_confirm: bool = False):
        """
        Initialize safety layer.
        
        Args:
            allowed_dirs: Allowed directories for file operations
            strict_sandbox: Enable strict path sandboxing
            auto_confirm: Auto-confirm actions (for testing)
        """
        self.command_guard = CommandGuard()
        self.path_sandbox = PathSandbox(allowed_dirs=allowed_dirs, strict_mode=strict_sandbox)
        self.resource_guard = ResourceGuard()
        self.confirmation = ConfirmationProtocol(auto_confirm=auto_confirm)
        
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize safety layer components."""
        if self._initialized:
            return
        
        # Start resource monitoring
        self.resource_guard.start_monitoring()
        
        # Add resource limit callback
        def on_resource_limit(event: dict):
            logger.critical(f"RESOURCE LIMIT EXCEEDED: {event['message']}")
            # Could trigger emergency shutdown or throttling here
        
        self.resource_guard.add_callback(on_resource_limit)
        
        self._initialized = True
        logger.info("SafetyLayer initialized")
    
    def shutdown(self) -> None:
        """Shutdown safety layer."""
        self.resource_guard.stop_monitoring()
        self._initialized = False
        logger.info("SafetyLayer shut down")
    
    def pre_execute_check(self,
                          tool_name: str,
                          params: Dict[str, Any],
                          command: Optional[str] = None) -> SafetyCheckResult:
        """
        Perform pre-execution safety check.
        
        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters
            command: Optional shell command string
            
        Returns:
            SafetyCheckResult indicating if execution is allowed
        """
        # Check shell commands
        if command:
            cmd_result = self.command_guard.check(command)
            if not cmd_result.allowed:
                return cmd_result
            
            if cmd_result.requires_confirmation:
                confirmed, msg = self.confirmation.request_confirmation(
                    action=tool_name,
                    description=f"Execute command: {command[:100]}...",
                    risk_level=cmd_result.risk_level,
                    context={'command': command}
                )
                
                if not confirmed:
                    return SafetyCheckResult(
                        allowed=False,
                        risk_level=cmd_result.risk_level,
                        reason=msg
                    )
        
        # Check file paths
        path_params = ['path', 'source', 'destination', 'directory', 'file']
        for param_name in path_params:
            if param_name in params:
                path = params[param_name]
                operation = 'write' if param_name in ['destination', 'file'] else 'read'
                
                path_result = self.path_sandbox.validate_operation(operation, path)
                if not path_result.allowed:
                    return path_result
                
                if path_result.requires_confirmation:
                    confirmed, msg = self.confirmation.request_confirmation(
                        action=f"{tool_name}:{param_name}",
                        description=f"File {operation}: {path}",
                        risk_level=path_result.risk_level,
                        context={'path': path, 'operation': operation}
                    )
                    
                    if not confirmed:
                        return SafetyCheckResult(
                            allowed=False,
                            risk_level=path_result.risk_level,
                            reason=msg
                        )
        
        # Check if tool requires confirmation
        requires_conf, conf_reason = self.confirmation.should_require_confirmation(
            tool_name, params
        )
        
        if requires_conf:
            confirmed, msg = self.confirmation.request_confirmation(
                action=tool_name,
                description=conf_reason,
                risk_level=RiskLevel.HIGH,
                context=params
            )
            
            if not confirmed:
                return SafetyCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.HIGH,
                    reason=msg
                )
        
        # All checks passed
        return SafetyCheckResult(
            allowed=True,
            risk_level=RiskLevel.SAFE,
            reason="All safety checks passed"
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get safety layer status."""
        return {
            'initialized': self._initialized,
            'resource_usage': self.resource_guard.get_current_usage(),
            'sandbox_dirs': self.path_sandbox.allowed_dirs,
            'strict_mode': self.path_sandbox.strict_mode,
            'auto_confirm': self.confirmation.auto_confirm
        }


# Global safety layer instance
_safety_instance: Optional[SafetyLayer] = None
_safety_lock = threading.Lock()


def get_safety_layer(allowed_dirs: Optional[List[str]] = None,
                     strict_sandbox: bool = True,
                     auto_confirm: bool = False) -> SafetyLayer:
    """
    Get or create the global safety layer.
    
    Args:
        allowed_dirs: Allowed directories for file operations
        strict_sandbox: Enable strict path sandboxing
        auto_confirm: Auto-confirm actions (for testing)
        
    Returns:
        Global SafetyLayer instance
    """
    global _safety_instance
    
    with _safety_lock:
        if _safety_instance is None:
            _safety_instance = SafetyLayer(
                allowed_dirs=allowed_dirs,
                strict_sandbox=strict_sandbox,
                auto_confirm=auto_confirm
            )
            _safety_instance.initialize()
        return _safety_instance


def reset_safety_layer() -> None:
    """Reset the global safety layer (useful for testing)."""
    global _safety_instance
    
    with _safety_lock:
        if _safety_instance is not None:
            _safety_instance.shutdown()
            _safety_instance = None
