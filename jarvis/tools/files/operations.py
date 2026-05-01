"""
tools/files/operations.py — File operation tools

Tools for: read, create, open, delete, move, copy files
Uses pathlib and subprocess for file operations.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("file_tools")


def is_safe_path(path: str) -> tuple[bool, str]:
    """Check if a path is safe to operate on (not system-critical)."""
    try:
        resolved = Path(path).resolve()
        path_str = str(resolved).lower()
        
        # Block system directories
        blocked_prefixes = [
            r"c:\windows",
            r"c:\program files",
            r"c:\program files (x86)",
            r"c:\users\all users",
            r"c:\programdata",
        ]
        
        for prefix in blocked_prefixes:
            if path_str.startswith(prefix):
                return False, f"Access denied: Cannot modify system path '{prefix}'"
        
        return True, ""
    except Exception as e:
        return False, f"Invalid path: {e}"


class ReadFileTool(BaseTool):
    """Read contents of a text file."""
    
    name = "read_file"
    description = "Read the contents of a text file. Returns up to 10KB of content."
    parameters = {
        "path": {
            "type": "string",
            "description": "Full path to the file to read",
        },
        "max_lines": {
            "type": "integer",
            "description": "Maximum lines to read (default: 100)",
        },
    }
    required_parameters = ["path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        if not path:
            return False, "path parameter is required"
        
        is_safe, error = is_safe_path(path)
        if not is_safe:
            return False, error
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        max_lines = kwargs.get("max_lines", 100)
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult.fail(error=f"File not found: {path}")
            
            if not file_path.is_file():
                return ToolResult.fail(error=f"Not a file: {path}")
            
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... ({max_lines} lines shown)")
                        break
                    lines.append(line.rstrip())
            
            content = "\n".join(lines)
            return ToolResult.ok(content[:10000])  # Limit output size
            
        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            log.error(f"Failed to read file: {e}")
            return ToolResult.fail(error=f"Failed to read file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class CreateFileTool(BaseTool):
    """Create a new file with content."""
    
    name = "create_file"
    description = "Create a new file with the specified content. Will overwrite existing files."
    parameters = {
        "path": {
            "type": "string",
            "description": "Full path where to create the file",
        },
        "content": {
            "type": "string",
            "description": "Content to write to the file",
        },
    }
    required_parameters = ["path", "content"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        content = kwargs.get("content")
        
        if not path:
            return False, "path parameter is required"
        if content is None:
            return False, "content parameter is required"
        
        is_safe, error = is_safe_path(path)
        if not is_safe:
            return False, error
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        content = kwargs["content"]
        
        try:
            file_path = Path(path)
            
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult.ok(f"Created file: {path}")
            
        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            log.error(f"Failed to create file: {e}")
            return ToolResult.fail(error=f"Failed to create file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"  # Can overwrite existing files


class OpenFileTool(BaseTool):
    """Open a file with its default application."""
    
    name = "open_file"
    description = "Open a file with its default associated application."
    parameters = {
        "path": {
            "type": "string",
            "description": "Full path to the file to open",
        },
    }
    required_parameters = ["path"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        if not path:
            return False, "path parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult.fail(error=f"File not found: {path}")
            
            # Use start command to open with default app
            subprocess.Popen(
                ["start", str(file_path)],
                shell=True,
            )
            
            return ToolResult.ok(f"Opening {path}")
            
        except Exception as e:
            log.error(f"Failed to open file: {e}")
            return ToolResult.fail(error=f"Failed to open file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 1.0
    
    def risk_level(self) -> str:
        return "low"


class DeleteFileTool(BaseTool):
    """Delete a file."""
    
    name = "delete_file"
    description = "Delete a file permanently. Use with caution - this cannot be undone easily."
    parameters = {
        "path": {
            "type": "string",
            "description": "Full path to the file to delete",
        },
        "confirm": {
            "type": "boolean",
            "description": "Must be true to confirm deletion (safety check)",
        },
    }
    required_parameters = ["path", "confirm"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        path = kwargs.get("path")
        confirm = kwargs.get("confirm", False)
        
        if not path:
            return False, "path parameter is required"
        if not confirm:
            return False, "confirm must be true to delete a file"
        
        is_safe, error = is_safe_path(path)
        if not is_safe:
            return False, error
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        path = kwargs["path"]
        
        try:
            file_path = Path(path)
            
            if not file_path.exists():
                return ToolResult.fail(error=f"File not found: {path}")
            
            if not file_path.is_file():
                return ToolResult.fail(error=f"Not a file: {path}")
            
            file_path.unlink()
            
            return ToolResult.ok(f"Deleted: {path}")
            
        except PermissionError:
            return ToolResult.fail(error=f"Permission denied: {path}")
        except Exception as e:
            log.error(f"Failed to delete file: {e}")
            return ToolResult.fail(error=f"Failed to delete file: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.2
    
    def risk_level(self) -> str:
        return "high"  # Permanent deletion


# Export all tool classes
FILE_TOOLS = [
    ReadFileTool,
    CreateFileTool,
    OpenFileTool,
    DeleteFileTool,
]
