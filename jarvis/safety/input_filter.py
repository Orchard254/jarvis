"""
JARVIS Input Filter - Sanitizes and validates user input before processing.

First layer of safety system. Filters dangerous commands, injection attempts,
and malformed input before they reach the LLM or execution layers.
"""

import re
from typing import Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class FilterResult:
    """Result of input filtering."""
    is_safe: bool
    sanitized_input: str
    reason: Optional[str] = None
    blocked_patterns: List[str] = None
    
    def __post_init__(self):
        if self.blocked_patterns is None:
            self.blocked_patterns = []


class InputFilter:
    """
    Input sanitization and validation filter.
    
    Checks for:
    - Command injection patterns
    - Path traversal attempts
    - SQL injection patterns (for future DB integration)
    - Excessive length
    - Malformed Unicode
    - Known dangerous phrases
    """
    
    # Dangerous command patterns (PowerShell/Windows specific)
    DANGEROUS_PATTERNS = [
        # File system destruction
        (r'format\s+[c-z]:', 'disk_format'),
        (r'del\s+/[a-z]*\s+[c-z]:', 'recursive_delete'),
        (r'remove-item\s+-recurse\s+-force.*[c-z]:', 'recursive_delete'),
        (r'rd\s+/s/q\s+[c-z]:', 'recursive_delete'),
        
        # System manipulation
        (r'reg\s+delete\s+hk', 'registry_delete'),
        (r'reg\s+add.*\/d.*cmd', 'registry_cmd_injection'),
        (r'schtasks\s+/create.*cmd', 'scheduled_task_injection'),
        
        # Network attacks
        (r'netsh\s+.*delete', 'network_config_delete'),
        (r'ipconfig\s+/release', 'network_release'),
        (r'ping\s+-t.*-l\s+\d{4,}', 'ping_flood'),
        
        # Process manipulation
        (r'taskkill\s+/im\s+(explorer|csrss|wininit)', 'critical_process_kill'),
        (r'stop-process\s+-name\s+(explorer|csrss)', 'critical_process_kill'),
        
        # Code execution
        (r'powershell\s+-enc\s+[a-z0-9+/=]{50,}', 'encoded_command'),
        (r'iex\s*\(\s*new-object', 'download_execute'),
        (r'invoke-webrequest.*downloadstring', 'download_execute'),
        
        # Privilege escalation
        (r'runas\s+/user:administrator', 'privilege_escalation'),
        (r'enable-psremoting', 'remote_access_enable'),
        
        # Data exfiltration
        (r'type\s+.*\|\s*nc\s+', 'data_exfiltration'),
        (r'get-content.*\|\s*curl', 'data_exfiltration'),
    ]
    
    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        (r'\.\./\.\.', 'path_traversal'),
        (r'\.\.\\\\\.\.', 'path_traversal_windows'),
        (r'%windir%', 'env_var_access'),
        (r'%systemroot%', 'env_var_access'),
        (r'%appdata%', 'env_var_access'),
    ]
    
    # Maximum input lengths
    MAX_INPUT_LENGTH = 2000
    MAX_SINGLE_WORD_LENGTH = 200
    
    def __init__(self):
        self.compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), name)
            for pattern, name in self.DANGEROUS_PATTERNS + self.PATH_TRAVERSAL_PATTERNS
        ]
    
    def check(self, user_input: str) -> FilterResult:
        """
        Check user input for safety.
        
        Args:
            user_input: Raw user input string
            
        Returns:
            FilterResult with safety assessment
        """
        if not user_input:
            return FilterResult(
                is_safe=False,
                sanitized_input='',
                reason='Empty input'
            )
        
        # Check length
        if len(user_input) > self.MAX_INPUT_LENGTH:
            return FilterResult(
                is_safe=False,
                sanitized_input=user_input[:self.MAX_INPUT_LENGTH],
                reason=f'Input exceeds maximum length ({len(user_input)} > {self.MAX_INPUT_LENGTH})'
            )
        
        # Check for oversized words (potential buffer overflow attempts)
        words = user_input.split()
        for word in words:
            if len(word) > self.MAX_SINGLE_WORD_LENGTH:
                return FilterResult(
                    is_safe=False,
                    sanitized_input=user_input,
                    reason=f'Single word exceeds maximum length ({len(word)} > {self.MAX_SINGLE_WORD_LENGTH})'
                )
        
        # Check for dangerous patterns
        blocked_patterns = []
        for pattern, name in self.compiled_patterns:
            if pattern.search(user_input):
                blocked_patterns.append(name)
        
        if blocked_patterns:
            return FilterResult(
                is_safe=False,
                sanitized_input=user_input,
                reason=f'Blocked dangerous patterns: {", ".join(blocked_patterns)}',
                blocked_patterns=blocked_patterns
            )
        
        # Sanitize Unicode (remove control characters except newline/tab)
        sanitized = self._sanitize_unicode(user_input)
        
        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())
        
        return FilterResult(
            is_safe=True,
            sanitized_input=sanitized
        )
    
    def _sanitize_unicode(self, text: str) -> str:
        """Remove dangerous control characters while preserving valid text."""
        result = []
        for char in text:
            code = ord(char)
            # Allow printable ASCII, common punctuation, and basic whitespace
            if (32 <= code <= 126) or (code in (9, 10, 13)):  # tab, newline, carriage return
                result.append(char)
            # Allow common Unicode ranges (Latin, symbols, etc.)
            elif (128 <= code <= 0x24F) or (0x2000 <= code <= 0x206F):
                result.append(char)
            # Block other control characters
            else:
                continue
        return ''.join(result)
    
    def is_command_likely(self, text: str) -> bool:
        """
        Heuristic to detect if input is likely a direct command.
        
        Used to decide if extra scrutiny is needed.
        """
        # Starts with known command verbs
        command_verbs = [
            'run', 'execute', 'open', 'delete', 'remove', 'kill', 'stop',
            'start', 'create', 'write', 'download', 'send', 'connect'
        ]
        
        text_lower = text.lower().strip()
        for verb in command_verbs:
            if text_lower.startswith(verb):
                return True
        
        # Contains PowerShell/cmd syntax
        cmd_syntax = ['|', '>', '<', '&', '`', '$', '@']
        return any(syntax in text for syntax in cmd_syntax)
    
    def extract_potential_commands(self, text: str) -> List[str]:
        """
        Extract substrings that look like shell commands.
        
        Useful for logging and audit.
        """
        commands = []
        
        # Look for quoted strings that might contain commands
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        for q in quoted:
            if any(verb in q.lower() for verb in ['del', 'rm', 'format', 'kill']):
                commands.append(q)
        
        # Look for PowerShell commands
        ps_commands = re.findall(r'(?:powershell|pwsh)\s+([^;]+)', text, re.IGNORECASE)
        commands.extend(ps_commands)
        
        return commands


# Singleton instance
_input_filter: Optional[InputFilter] = None


def get_input_filter() -> InputFilter:
    """Get the singleton input filter instance."""
    global _input_filter
    if _input_filter is None:
        _input_filter = InputFilter()
    return _input_filter


def reset_input_filter():
    """Reset the singleton instance (for testing)."""
    global _input_filter
    _input_filter = None


def check_input(user_input: str) -> FilterResult:
    """Convenience function to check input using singleton filter."""
    return get_input_filter().check(user_input)
