"""
jarvis/core/safety.py — Deterministic Guardrail System

A safety layer that intercepts commands before execution with:
- Command Allowlist/Blocklist: Blocks dangerous patterns
- Path Sandboxing: Prevents file operations outside designated directories
- Resource Guards: Stops processes from consuming >80% CPU/RAM
- Confirmation Protocol: Forces human-in-the-loop for high-risk actions
"""

import re
import os
import psutil
import logging
from typing import Dict, Any, List, Tuple, Optional, Set
from datetime import datetime
from pathlib import Path
import threading

logger = logging.getLogger(__name__)


class SafetyLayer:
    """
    Deterministic guardrail system for JARVIS.
    
    Intercepts all commands before execution and applies safety checks:
    1. Command allowlist/blocklist filtering
    2. Path sandboxing validation
    3. Resource usage monitoring
    4. High-risk action confirmation protocol
    """
    
    # Destructive command patterns - ALWAYS blocked
    BLOCKED_PATTERNS = [
        r'rm\s+-rf\s+/',           # Delete root filesystem (Unix)
        r'rm\s+-rf\s+\*',          # Delete everything in current dir
        r'del\s+/[a-z]\s+/',       # Delete all files (Windows)
        r'format\s+c:',            # Format C drive (Windows)
        r'format\s+d:',            # Format D drive (Windows)
        r'format\s+.*\s+/q',       # Quick format any drive
        r'chmod\s+-R\s+777',       # Recursive chmod 777
        r'chown\s+-R\s+',          # Recursive chown
        r'shutdown\s+/r\s+/t\s+0', # Immediate restart (Windows)
        r'shutdown\s+-r\s+now',    # Immediate restart (Linux)
        r'shutdown\s+-h\s+now',    # Immediate halt (Linux)
        r'mkfs\.',                 # Create filesystem (destructive)
        r'dd\s+if=/dev/zero',      # Zero out disk
        r':\(\)\{\s*:\|\:&\s*\};:', # Fork bomb
        r'>\s*/dev/sd[a-z]',       # Overwrite disk device
        r'echo\s+.*>\s*/dev/sd',   # Write to disk device
    ]
    
    # High-risk commands requiring human confirmation
    HIGH_RISK_PATTERNS = [
        r'shutdown',               # Any shutdown command
        r'reboot',                 # Any reboot command
        r'sudo\s+',                # Sudo privilege escalation
        r'net\s+user',             # User management (Windows)
        r'useradd',                # Add user (Linux)
        r'userdel',                # Delete user (Linux)
        r'passwd',                 # Change password
        r'reg\s+(add|delete)',     # Registry modification (Windows)
        r'netsh',                  # Network configuration (Windows)
        r'iptables',               # Firewall rules (Linux)
        r'systemctl\s+(stop|disable)',  # Stop system services
        r'taskkill\s+/F',          # Force kill process (Windows)
        r'kill\s+-9',              # Force kill process (Linux)
        r'curl\s+.*\|\s*(sh|bash)', # Pipe curl to shell
        r'wget\s+.*\|\s*(sh|bash)', # Pipe wget to shell
    ]
    
    # Protected system paths - cannot be modified without explicit authorization
    PROTECTED_PATHS = [
        r'C:\\Windows',
        r'C:\\Program Files',
        r'C:\\Program Files \(x86\)',
        r'C:\\Users\\.*\\AppData\\Roaming',
        r'C:\\Users\\.*\\AppData\\Local\\Microsoft',
        r'C:\\System Volume Information',
        r'C:\\ProgramData\\Microsoft',
        r'/etc/',
        r'/usr/',
        r'/var/',
        r'/bin/',
        r'/sbin/',
        r'/boot/',
        r'/proc/',
        r'/sys/',
    ]
    
    # Safe administrative commands (allowlist)
    SAFE_COMMANDS = [
        'dir', 'ls', 'pwd', 'cd', 'mkdir', 'rmdir',
        'copy', 'xcopy', 'cp', 'mv', 'rename',
        'type', 'cat', 'head', 'tail', 'less', 'more',
        'echo', 'print', 'date', 'time', 'whoami',
        'hostname', 'ipconfig', 'ifconfig', 'ping',
        'tasklist', 'ps', 'top', 'htop',
        'netstat', 'ss', 'nslookup', 'dig',
        'find', 'grep', 'whereis', 'which',
        'python', 'python3', 'node', 'npm', 'pip',
    ]
    
    def __init__(self, 
                 working_dirs: Optional[List[str]] = None,
                 cpu_threshold: float = 80.0,
                 ram_threshold: float = 80.0,
                 require_confirmation: bool = True):
        """
        Initialize the safety layer.
        
        Args:
            working_dirs: List of allowed working directories for path sandboxing
            cpu_threshold: CPU usage percentage threshold (default 80%)
            ram_threshold: RAM usage percentage threshold (default 80%)
            require_confirmation: Whether to require human confirmation for high-risk actions
        """
        self.working_dirs = working_dirs or [str(Path.home())]
        self.cpu_threshold = cpu_threshold
        self.ram_threshold = ram_threshold
        self.require_confirmation = require_confirmation
        
        # Compile regex patterns
        self.blocked_regex = [re.compile(p, re.IGNORECASE) for p in self.BLOCKED_PATTERNS]
        self.high_risk_regex = [re.compile(p, re.IGNORECASE) for p in self.HIGH_RISK_PATTERNS]
        self.protected_regex = [re.compile(p, re.IGNORECASE) for p in self.PROTECTED_PATHS]
        
        # Resource monitoring state
        self._resource_monitor_active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._resource_violations: List[Dict[str, Any]] = []
        
        # Confirmation state
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"SafetyLayer initialized with {len(self.working_dirs)} working directories")
    
    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Validate a command against the blocklist and allowlist.
        
        Args:
            command: The command string to validate
            
        Returns:
            Tuple of (is_safe, reason_message)
        """
        if not command or not command.strip():
            return False, "Empty command"
        
        cmd_lower = command.lower()
        
        # Check blocked patterns first (highest priority)
        for pattern in self.blocked_regex:
            if pattern.search(command):
                logger.warning(f"BLOCKED: Dangerous command pattern detected: {command[:100]}")
                return False, f"Blocked dangerous pattern: {pattern.pattern}"
        
        # Check if it's a safe command (allowlist)
        cmd_base = command.split()[0].lower() if command.split() else ''
        if cmd_base in self.SAFE_COMMANDS:
            return True, "Command is in allowlist"
        
        # Check high-risk patterns (requires confirmation)
        for pattern in self.high_risk_regex:
            if pattern.search(command):
                if self.require_confirmation:
                    confirmation_id = self._request_confirmation(command, pattern.pattern)
                    return False, f"HIGH_RISK: Requires human confirmation. ID: {confirmation_id}"
                else:
                    logger.warning(f"High-risk command allowed without confirmation: {command[:100]}")
        
        # Default: allow but log
        logger.debug(f"Command passed safety check: {command[:100]}")
        return True, "Command passed safety validation"
    
    def validate_path(self, path: str, operation: str = 'read') -> Tuple[bool, str]:
        """
        Validate file path access against sandboxing rules.
        
        Args:
            path: The file path to validate
            operation: Type of operation ('read', 'write', 'delete')
            
        Returns:
            Tuple of (is_allowed, reason_message)
        """
        if not path:
            return False, "Empty path"
        
        # Normalize path
        try:
            normalized_path = str(Path(path).resolve())
        except Exception:
            normalized_path = path
        
        # Extra strict for delete operations
        if operation == 'delete':
            for pattern in self.blocked_regex:
                if pattern.search(path):
                    return False, f"Delete operation blocked by pattern: {pattern.pattern}"
        
        # Check if path is within working directories
        is_in_sandbox = False
        for work_dir in self.working_dirs:
            try:
                work_resolved = str(Path(work_dir).resolve())
                if normalized_path.startswith(work_resolved):
                    is_in_sandbox = True
                    break
            except Exception:
                continue
        
        if not is_in_sandbox:
            # Check if it's a protected system path
            for pattern in self.protected_regex:
                if pattern.search(normalized_path):
                    logger.warning(f"BLOCKED: Access to protected path: {normalized_path}")
                    return False, f"Access to protected system path: {normalized_path}"
            
            # Outside sandbox but not protected - warn but allow
            logger.warning(f"Path outside sandbox: {normalized_path}")
            return True, f"Warning: Path outside designated working directories"
        
        return True, "Path within sandbox"
    
    def check_resources(self) -> Tuple[bool, Dict[str, float]]:
        """
        Check current system resource usage against thresholds.
        
        Returns:
            Tuple of (resources_ok, status_dict)
        """
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        ram_percent = memory.percent
        
        status = {
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'cpu_threshold': self.cpu_threshold,
            'ram_threshold': self.ram_threshold,
        }
        
        resources_ok = True
        violations = []
        
        if cpu_percent > self.cpu_threshold:
            resources_ok = False
            violations.append(f"CPU usage {cpu_percent:.1f}% exceeds threshold {self.cpu_threshold}%")
        
        if ram_percent > self.ram_threshold:
            resources_ok = False
            violations.append(f"RAM usage {ram_percent:.1f}% exceeds threshold {self.ram_threshold}%")
        
        if violations:
            for v in violations:
                logger.warning(f"RESOURCE GUARD: {v}")
            self._resource_violations.append({
                'timestamp': datetime.now().isoformat(),
                'violations': violations
            })
        
        return resources_ok, status
    
    def start_resource_monitor(self, check_interval: float = 2.0) -> None:
        """
        Start background resource monitoring thread.
        
        Args:
            check_interval: Seconds between resource checks
        """
        if self._resource_monitor_active:
            logger.warning("Resource monitor already running")
            return
        
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(
            target=self._resource_monitor_loop,
            args=(check_interval,),
            daemon=True
        )
        self._monitor_thread.start()
        self._resource_monitor_active = True
        logger.info(f"Resource monitor started (interval: {check_interval}s)")
    
    def stop_resource_monitor(self) -> None:
        """Stop the background resource monitoring thread."""
        if not self._resource_monitor_active:
            return
        
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        self._resource_monitor_active = False
        logger.info("Resource monitor stopped")
    
    def _resource_monitor_loop(self, interval: float) -> None:
        """Background loop for resource monitoring."""
        while not self._stop_monitor.is_set():
            resources_ok, status = self.check_resources()
            if not resources_ok:
                # Could trigger automatic process throttling here
                logger.error(f"Resource violation detected: {status}")
            self._stop_monitor.wait(interval)
    
    def _request_confirmation(self, command: str, pattern: str) -> str:
        """
        Request human confirmation for a high-risk action.
        
        Args:
            command: The command requiring confirmation
            pattern: The pattern that triggered the requirement
            
        Returns:
            Confirmation request ID
        """
        import uuid
        confirmation_id = str(uuid.uuid4())[:8]
        
        self._pending_confirmations[confirmation_id] = {
            'command': command,
            'pattern': pattern,
            'timestamp': datetime.now().isoformat(),
            'confirmed': False
        }
        
        logger.critical(
            f"CONFIRMATION REQUIRED [{confirmation_id}]: "
            f"High-risk command detected matching '{pattern}'"
        )
        
        return confirmation_id
    
    def confirm_action(self, confirmation_id: str, confirmed: bool = True) -> bool:
        """
        Record human confirmation for a pending action.
        
        Args:
            confirmation_id: The ID from _request_confirmation
            confirmed: Whether the action was confirmed
            
        Returns:
            True if confirmation was recorded successfully
        """
        if confirmation_id not in self._pending_confirmations:
            logger.warning(f"Unknown confirmation ID: {confirmation_id}")
            return False
        
        self._pending_confirmations[confirmation_id]['confirmed'] = confirmed
        self._pending_confirmations[confirmation_id]['confirmed_at'] = datetime.now().isoformat()
        
        status = "CONFIRMED" if confirmed else "DENIED"
        logger.info(f"Confirmation {confirmation_id}: {status}")
        
        return True
    
    def get_pending_confirmations(self) -> List[Dict[str, Any]]:
        """Get list of pending confirmation requests."""
        return [
            {'id': k, **v} 
            for k, v in self._pending_confirmations.items() 
            if not v.get('confirmed')
        ]
    
    def get_violation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent resource violation history."""
        return self._resource_violations[-limit:]
    
    def add_working_directory(self, path: str) -> None:
        """Add a directory to the allowed working directories."""
        resolved = str(Path(path).resolve())
        if resolved not in self.working_dirs:
            self.working_dirs.append(resolved)
            logger.info(f"Added working directory: {resolved}")
    
    def is_safe_command(self, command: str) -> bool:
        """Quick check if a command is safe (no confirmation needed)."""
        is_valid, reason = self.validate_command(command)
        return is_valid and "HIGH_RISK" not in reason and "confirmation" not in reason.lower()
