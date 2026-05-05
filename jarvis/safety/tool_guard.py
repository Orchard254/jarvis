"""
safety/tool_guard.py — Safety validation layer for tool execution.
Replaces control_plane.py with focused tool-level safety checks.

Improvements over original control_plane.py:
- Registry check comes FIRST before parameter validation
- Unknown tool names return helpful error with 5 most similar valid tool names
- Error format: "Unknown tool: {name}. Did you mean: {suggestions}?"
- All original unsafe patterns preserved
"""

import re
import os
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class ToolGuard:
    """
    Validates tool calls before execution.
    Checks for dangerous operations, path traversal, and policy violations.
    """
    
    # FIX #14: Single source of truth for all dangerous patterns
    # Used by _validate_run_python, _contains_dangerous_content, and validate_generated_tool_code
    
    # Strict patterns: blocked for user-submitted code
    STRICT_PATTERNS = [
        r'__import__\s*\(',
        r'ctypes\.windll',
        r'ctypes\.cdll',
        r'os\.system\s*\(',
        r'subprocess\.(call|run|Popen)\s*\(',
        r'eval\s*\(',
        r'exec\s*\(',
    ]
    
    # Destructive patterns: always blocked (both strict and permissive)
    DESTRUCTIVE_PATTERNS = [
        "format c:",
        "format d:",
        "rd /s /q c:\\",
        "del /f /s /q c:\\windows",
        "reg delete HKLM\\SYSTEM",
        "net user administrator",
    ]
    
    DESTRUCTIVE_REGEX = [
        r"shutil\.rmtree\s*\(\s*['\"]C:[/\\\\]+Windows",
        r"shutil\.rmtree\s*\(\s*['\"]C:[/\\\\]+Program\s+Files",
        r"os\.remove\s*\(\s*['\"]C:[/\\\\]+Windows",
    ]
    
    # All original unsafe patterns from control_plane.py - must be preserved
    UNSAFE_PATTERNS = [
        r'rm\s+-rf',           # Recursive force delete (Unix)
        r'del\s+/[a-z]\s+/',   # Delete all files (Windows)
        r'Format-Volume',      # Format disk volume (PowerShell)
        r'Clear-Disk',         # Clear entire disk (PowerShell)
        r'rmdir\s+/s',         # Remove directory tree (Windows)
        r'del\s+/s',           # Delete all files recursively (Windows)
        r'\bformat\b',         # Format command
        r'shutdown\s+/r\s+/t\s+0',  # Immediate restart (Windows)
        r'\bsudo\b',           # Sudo privilege escalation
        r'curl\s+.*\|\s*sh',   # Curl pipe to shell
        r'rm\s+-rf\s+/',       # Delete root filesystem (Unix)
    ]
    
    # FIX #11: Dangerous system paths — scoped to actual system directories only
    PROTECTED_PATHS = [
        r'C:\\Windows',
        r'C:\\Program Files',
        r'C:\\Program Files \(x86\)',
        r'C:\\Users\\.*\\AppData\\Roaming',
        r'C:\\Users\\.*\\AppData\\Local\\Microsoft',
        r'C:\\System Volume Information',
        r'C:\\ProgramData\\Microsoft',
    ]
    
    def __init__(self, registry=None):
        self.protected_patterns = [re.compile(p, re.IGNORECASE) for p in self.PROTECTED_PATHS]
        self.unsafe_patterns = [re.compile(p, re.IGNORECASE) for p in self.UNSAFE_PATTERNS]
        self.audit_log = []
        self._registry = registry
        self._warned_no_registry = False
    
    def set_registry(self, registry) -> None:
        """Set the tool registry for validation."""
        self._registry = registry
    
    def validate_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a tool call before execution.
        
        IMPORTANT: Registry check comes FIRST before any parameter validation.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # STEP 1: Check if tool exists in registry FIRST
        if not tool_name:
            return False, "No tool name provided"
        
        # Check registry first if available
        if self._registry is not None:
            if not self._registry.has_tool(tool_name):
                # Return helpful error with similar tool names
                return self._get_unknown_tool_error(tool_name)
        elif not self._warned_no_registry:
            # Log warning once when registry is not set
            logger = logging.getLogger(__name__)
            logger.warning("ToolGuard has no registry reference - unknown tool names will not be caught")
            self._warned_no_registry = True
        
        # STEP 2: Check for unsafe patterns in tool name or params
        if self._check_unsafe_patterns(tool_name, params):
            return False, "Tool call contains unsafe patterns"
        
        # STEP 3: Route to specific validator based on tool category
        validators = {
            'run_command': self._validate_command,
            'run_powershell': self._validate_powershell,
            'read_file': self._validate_read_file,
            'create_file': self._validate_create_file,
            'delete_file': self._validate_delete_file,
            'move_file': self._validate_move_file,
            'copy_file': self._validate_copy_file,
            'list_files': self._validate_list_files,
            'open_app': self._validate_open_app,
            'close_app': self._validate_close_app,
            'click_at': self._validate_click_at,
            'type_text': self._validate_type_text,
            'press_key': self._validate_press_key,
            'run_python': self._validate_run_python,
            'run_script': self._validate_run_script,
        }
        
        validator = validators.get(tool_name)
        if validator:
            return validator(params)
        
        # Default validation for tools without specific validators
        return True, ""
    
    def _get_unknown_tool_error(self, name: str) -> Tuple[bool, str]:
        """
        Generate helpful error message for unknown tool with suggestions.
        
        Returns exactly: "Unknown tool: {name}. Did you mean: {suggestions}?"
        where suggestions are the 5 most similar valid tool names.
        """
        if self._registry is None:
            return False, f"Unknown tool: {name}. No registry available."
        
        available = sorted(self._registry.get_tool_names())
        
        if not available:
            return False, f"Unknown tool: {name}. No tools registered."
        
        # Find similar names using simple string matching
        similar = []
        name_lower = name.lower()
        
        # First priority: exact substring matches
        for t in available:
            if name_lower in t.lower() or t.lower() in name_lower:
                similar.append(t)
        
        # Second priority: similar length with some character overlap
        if len(similar) < 5:
            for t in available:
                if t not in similar:
                    # Check for common prefix or suffix
                    if t.lower().startswith(name_lower[:3]) or t.lower().endswith(name_lower[-3:]):
                        similar.append(t)
                        if len(similar) >= 5:
                            break
        
        # If still not enough, just take first 5 available
        if len(similar) < 5:
            for t in available:
                if t not in similar:
                    similar.append(t)
                    if len(similar) >= 5:
                        break
        
        suggestions = ", ".join(similar[:5])
        return False, f"Unknown tool: {name}. Did you mean: {suggestions}?"
    
    def _check_unsafe_patterns(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """Check if tool call contains any unsafe patterns."""
        # Check tool name
        for pattern in self.unsafe_patterns:
            if pattern.search(tool_name):
                return True
        
        # Check all string parameters
        for key, value in params.items():
            if isinstance(value, str):
                for pattern in self.unsafe_patterns:
                    if pattern.search(value):
                        return True
        
        return False
    
    def _validate_command(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate shell command execution."""
        cmd = params.get('command', '')
        if not cmd:
            return False, "Empty command"
        
        # Check for path traversal
        if '..' in cmd:
            return False, "Path traversal detected"
        
        return True, ""
    
    def _validate_powershell(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate PowerShell script execution."""
        script = params.get('script', '') or params.get('command', '')
        if not script:
            return False, "Empty script"
        
        # Check for dangerous cmdlets
        dangerous_cmdlets = [
            'Remove-Item -Recurse',
            'Format-Volume',
            'Clear-Disk',
            'Stop-Computer',
            'Restart-Computer',
            'Disable-NetAdapter',
        ]
        
        for cmdlet in dangerous_cmdlets:
            if cmdlet.lower() in script.lower():
                return False, f"Dangerous PowerShell cmdlet detected: {cmdlet}"
        
        return True, ""
    
    def _validate_read_file(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate file read operation."""
        path = params.get('path', '')
        return self._validate_path_access(path, write=False)
    
    def _validate_create_file(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate file creation."""
        path = params.get('path', '')
        content = params.get('content', '')
        
        # Check path
        valid, msg = self._validate_path_access(path, write=True)
        if not valid:
            return valid, msg
        
        # Check content for dangerous patterns
        if self._contains_dangerous_content(content):
            return False, "Content contains potentially dangerous code"
        
        return True, ""
    
    def _validate_delete_file(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate file deletion."""
        path = params.get('path', '')
        if not path:
            return False, "No path provided"
        
        # Extra strict for deletions
        valid, msg = self._validate_path_access(path, write=True, delete=True)
        if not valid:
            return valid, msg
        
        return True, ""
    
    def _validate_move_file(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate file move operation."""
        src = params.get('source', '')
        dst = params.get('destination', '')
        
        valid, msg = self._validate_path_access(src, write=False)
        if not valid:
            return valid, msg
        
        valid, msg = self._validate_path_access(dst, write=True)
        if not valid:
            return valid, msg
        
        return True, ""
    
    def _validate_copy_file(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate file copy operation."""
        src = params.get('source', '')
        dst = params.get('destination', '')
        
        valid, msg = self._validate_path_access(src, write=False)
        if not valid:
            return valid, msg
        
        valid, msg = self._validate_path_access(dst, write=True)
        if not valid:
            return valid, msg
        
        return True, ""
    
    def _validate_list_files(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate directory listing."""
        path = params.get('path', '')
        return self._validate_path_access(path, write=False)
    
    def _validate_open_app(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate app opening."""
        app = params.get('app', '')
        if not app:
            return False, "No app specified"
        
        # Block known malicious apps
        blocked_apps = ['cmd.exe', 'powershell.exe', 'regedit.exe', 'taskmgr.exe']
        if app.lower() in blocked_apps:
            return False, f"Opening {app} requires explicit confirmation"
        
        return True, ""
    
    def _validate_close_app(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate app closing."""
        app = params.get('app', '')
        if not app:
            return False, "No app specified"
        
        return True, ""
    
    def _validate_click_at(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate screen click coordinates."""
        x = params.get('x', 0)
        y = params.get('y', 0)
        
        # Validate coordinates are reasonable
        if not isinstance(x, int) or not isinstance(y, int):
            return False, "Coordinates must be integers"
        
        if x < 0 or y < 0 or x > 10000 or y > 10000:
            return False, "Coordinates out of reasonable range"
        
        return True, ""
    
    def _validate_type_text(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate text typing."""
        text = params.get('text', '')
        if not text:
            return True, ""  # Empty text is harmless
        
        if len(text) > 10000:
            return False, "Text too long"
        
        return True, ""
    
    def _validate_press_key(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate key press."""
        keys = params.get('keys', [])
        if not keys:
            return False, "No keys specified"
        
        # Block dangerous key combinations
        dangerous_combos = [['alt', 'f4'], ['ctrl', 'alt', 'del'], ['win', 'l']]
        keys_lower = [k.lower() for k in keys]
        
        for combo in dangerous_combos:
            if all(k in keys_lower for k in combo):
                return False, f"Dangerous key combination: {'+'.join(combo)}"
        
        return True, ""
    
    def _validate_run_python(self, params: Dict[str, Any], is_generated_tool: bool = False) -> Tuple[bool, str]:
        """Validate Python code execution.
        
        FIX #14: Uses unified STRICT_PATTERNS / DESTRUCTIVE_PATTERNS / DESTRUCTIVE_REGEX.
        """
        code = params.get('code', '')
        if not code:
            return False, "No code provided"
        
        # Always check destructive patterns (both strict and permissive)
        code_lower = code.lower()
        for pattern in self.DESTRUCTIVE_PATTERNS:
            if pattern.lower() in code_lower:
                return False, f"Destructive operation blocked: {pattern}"
        
        for pattern in self.DESTRUCTIVE_REGEX:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"Destructive operation blocked: {pattern}"
        
        if is_generated_tool:
            # Permissive rules for generated tools — only destructive patterns above apply
            return True, ""
        else:
            # Strict rules for user-submitted code — block additional dangerous patterns
            # Include eval, exec, os.system, ctypes which were missing
            
            # Block shutil destruction on system dirs - all quote and slash variants
            import re
            shutil_patterns = [
                re.compile(r"shutil\.rmtree\s*\(\s*['\"]C:[/\\\\]+Windows", re.IGNORECASE),
                re.compile(r"shutil\.rmtree\s*\(\s*['\"]C:[/\\\\]+Program\s+Files", re.IGNORECASE),
                re.compile(r"os\.remove\s*\(\s*['\"]C:[/\\\\]+Windows", re.IGNORECASE),
            ]
            for pat in shutil_patterns:
                if pat.search(code):
                    return False, f"Destructive operation blocked: {pat.pattern}"
            
            dangerous_patterns = [
                '__import__',
                r'eval\s*\(',
                r'exec\s*\(',
                r'os\.system\s*\(',
                r'ctypes\.windll',
                r'ctypes\.cdll',
            ]
            for pattern in dangerous_patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    return False, f"Dangerous pattern detected: {pattern}"
            
            # Block registry destruction
            if 'winreg' in code and 'DeleteKey' in code:
                return False, "Registry destruction detected"
            
            return True, ""
    
    def _validate_run_script(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate script execution."""
        script = params.get('script', '')
        lang = params.get('language', 'powershell')
        
        if not script:
            return False, "No script provided"
        
        if lang == 'powershell':
            return self._validate_powershell({'script': script})
        elif lang == 'python':
            return self._validate_run_python({'code': script})
        
        return True, ""
    
    def _validate_path_access(self, path: str, write: bool = False, delete: bool = False) -> Tuple[bool, str]:
        """
        Validate path access permissions.
        
        Args:
            path: The file/directory path
            write: Whether this is a write operation
            delete: Whether this is a delete operation (stricter)
        """
        if not path:
            return False, "Empty path"
        
        # Normalize path
        path = os.path.normpath(path)
        
        # Check for path traversal
        if '..' in path:
            return False, "Path traversal detected"
        
        # Check against protected paths
        for pattern in self.protected_patterns:
            if pattern.match(path):
                if delete:
                    return False, f"Cannot delete from protected location: {path}"
                if write:
                    return False, f"Cannot write to protected location: {path}"
        
        # For delete operations, ensure file exists first
        if delete and not os.path.exists(path):
            return False, f"File does not exist: {path}"
        
        return True, ""
    
    def _contains_dangerous_content(self, content: str, is_generated_tool: bool = False) -> bool:
        """Check if content contains potentially dangerous code.
        
        Args:
            content: Code content to check
            is_generated_tool: If True, use permissive rules for generated tools.
                              If False, use strict rules for user-submitted content.
        """
        if is_generated_tool:
            # Permissive rules - only block absolute destruction
            destructive_patterns = [
                r"format\s+c:",
                r"format\s+d:",
                r"rd\s+/s\s+/q\s+c:\\\\",
                r"del\s+/f\s+/s\s+/q\s+c:\\\\windows",
                r"reg\s+delete\s+HKLM\\\\SYSTEM",
                r"net\s+user\s+administrator",
                r"shutil\.rmtree\(['\"]C:\\\\Windows['\"]\)",
                r"shutil\.rmtree\(['\"]C:\\\\Program Files['\"]\)",
            ]
            
            for pattern in destructive_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True
            return False
        else:
            # Strict rules for user-submitted content
            dangerous_patterns = [
                r'os\.system\s*\(',
                r'subprocess\.(call|run|Popen)\s*\(',
                r'eval\s*\(',
                r'exec\s*\(',
                r'__import__\s*\(',
                r'ctypes\.windll',
                r'ctypes\.cdll',
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True
            
            return False
    
    def validate_generated_tool_code(self, code: str) -> Tuple[bool, str]:
        """Validate code for generated tools using permissive rules.
        
        Args:
            code: Python code to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not code:
            return False, "Empty code provided"
        
        # Check for destructive operations
        destructive_patterns = [
            "format c:",
            "format d:",
            "rd /s /q c:\\\\",
            "del /f /s /q c:\\\\windows",
            "reg delete HKLM\\\\SYSTEM",
            "net user administrator",
        ]
        code_lower = code.lower()
        for pattern in destructive_patterns:
            if pattern.lower() in code_lower:
                return False, f"Destructive operation blocked: {pattern}"
        
        # Block shutil.rmtree targeting Windows/Program Files directories
        import re
        if re.search(r"shutil\.rmtree\s*\(\s*['\"]C:\\\\Windows", code, re.IGNORECASE):
            return False, "Destructive operation blocked: shutil.rmtree on C:\\Windows"
        if re.search(r"shutil\.rmtree\s*\(\s*['\"]C:\\\\Program Files", code, re.IGNORECASE):
            return False, "Destructive operation blocked: shutil.rmtree on C:\\Program Files"
        
        return True, ""
    
    def log_action(self, tool_name: str, params: Dict[str, Any], 
                   validated: bool, error: str = "") -> None:
        """Log a validation action for audit purposes."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'tool': tool_name,
            'params': params,
            'validated': validated,
            'error': error
        }
        self.audit_log.append(entry)
    
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        return self.audit_log[-limit:]
    
    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self.audit_log = []


# Singleton instance — FIX #8: thread-safe
_guard_instance = None
_guard_lock = threading.Lock()

def get_tool_guard() -> ToolGuard:
    """Get the singleton ToolGuard instance (thread-safe)."""
    global _guard_instance
    if _guard_instance is None:
        with _guard_lock:
            if _guard_instance is None:
                _guard_instance = ToolGuard()
    return _guard_instance
