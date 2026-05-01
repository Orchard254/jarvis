"""
Tool Guard - Safety validation layer for tool execution.
Replaces control_plane.py with focused tool-level safety checks.
"""

import re
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class ToolGuard:
    """
    Validates tool calls before execution.
    Checks for dangerous operations, path traversal, and policy violations.
    """
    
    # Dangerous system paths that should never be modified
    PROTECTED_PATHS = [
        r'C:\\Windows',
        r'C:\\Program Files',
        r'C:\\Program Files \(x86\)',
        r'C:\\Users\\.*\\AppData',
        r'.*\\.sys$',
        r'.*\\.dll$',
        r'.*\\.exe$',
    ]
    
    # Dangerous commands that require extra validation
    DANGEROUS_COMMANDS = [
        'format',
        'del /s',
        'rd /s',
        'rmdir /s',
        'shutdown',
        'taskkill /f',
        'reg delete',
        'icacls',
        'takeown',
        'powershell.*-force',
        'rm -rf',
        'dd ',
        'mkfs',
    ]
    
    # File extensions that are risky to execute
    RISKY_EXTENSIONS = [
        '.exe', '.bat', '.cmd', '.ps1', '.vbs', '.js',
        '.msi', '.scr', '.com', '.pif', '.jar'
    ]
    
    def __init__(self):
        self.protected_patterns = [re.compile(p, re.IGNORECASE) for p in self.PROTECTED_PATHS]
        self.dangerous_patterns = [re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_COMMANDS]
        self.audit_log = []
    
    def validate_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a tool call before execution.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if tool exists
        if not tool_name:
            return False, "No tool name provided"
        
        # Route to specific validator based on tool category
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
        
        # Default validation for unknown tools
        return True, ""
    
    def _validate_command(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate shell command execution."""
        cmd = params.get('command', '')
        if not cmd:
            return False, "Empty command"
        
        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if pattern.search(cmd):
                return False, f"Command contains dangerous pattern: {pattern.pattern}"
        
        # Check for path traversal
        if '..' in cmd:
            return False, "Path traversal detected"
        
        return True, ""
    
    def _validate_powershell(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate PowerShell script execution."""
        script = params.get('script', '')
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
    
    def _validate_run_python(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate Python code execution."""
        code = params.get('code', '')
        if not code:
            return False, "No code provided"
        
        # Check for dangerous imports
        dangerous_imports = ['os.system', 'subprocess.call', 'eval(', 'exec(']
        for imp in dangerous_imports:
            if imp in code:
                return False, f"Dangerous pattern detected: {imp}"
        
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
    
    def _contains_dangerous_content(self, content: str) -> bool:
        """Check if content contains potentially dangerous code."""
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


# Singleton instance
_guard_instance = None

def get_tool_guard() -> ToolGuard:
    """Get the singleton ToolGuard instance."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = ToolGuard()
    return _guard_instance
