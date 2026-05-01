"""
tools/base.py — BaseTool abstract class

All tools must inherit from this class and implement:
- validate(): Check parameters are valid
- execute(): Run the tool
- rollback(): Undo the action if possible
- estimate_duration(): Return estimated seconds to complete
- risk_level(): Return risk level (low, medium, high, critical)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    """Standard result structure for all tool executions."""
    
    success: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    verified: bool = False
    verify_msg: str = ""
    
    # Additional metadata
    duration_ms: int = 0
    tool_name: str = ""
    parameters: Dict[str, Any] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary format used throughout JARVIS."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "verified": self.verified,
            "verify_msg": self.verify_msg,
        }
    
    @classmethod
    def ok(cls, output: str = "", **kwargs) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, **kwargs)
    
    @classmethod
    def fail(cls, error: str = "", exit_code: int = -1, **kwargs) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, error=error, exit_code=exit_code, **kwargs)


class BaseTool(ABC):
    """
    Abstract base class for all JARVIS tools.
    
    Every tool must implement:
    - name: Unique identifier for the tool
    - description: Human-readable description
    - parameters: Schema definition for parameters
    - validate(): Check parameters before execution
    - execute(): Perform the action
    - rollback(): Undo if possible
    - estimate_duration(): How long it takes
    - risk_level(): Safety classification
    """
    
    # Class-level attributes that subclasses must override
    name: str = "base_tool"
    description: str = "Base tool - should be overridden"
    parameters: Dict[str, Any] = {}
    required_parameters: list = None
    
    def __init__(self):
        if self.required_parameters is None:
            self.required_parameters = []
    
    @abstractmethod
    def validate(self, **kwargs) -> tuple[bool, str]:
        """
        Validate tool parameters before execution.
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            Tuple of (is_valid, error_message)
            If valid: (True, "")
            If invalid: (False, "Description of what's wrong")
        """
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool action.
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            ToolResult with success/failure and output/error
        """
        pass
    
    def rollback(self, **kwargs) -> ToolResult:
        """
        Attempt to undo the tool's action.
        
        Args:
            **kwargs: Original parameters or state info
            
        Returns:
            ToolResult indicating if rollback succeeded
        """
        return ToolResult.ok("Rollback not applicable for this tool")
    
    def estimate_duration(self, **kwargs) -> float:
        """
        Estimate how long execution will take in seconds.
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            Estimated duration in seconds
        """
        return 1.0
    
    def risk_level(self) -> str:
        """
        Return the risk level of this tool.
        
        Returns:
            One of: "low", "medium", "high", "critical"
        """
        return "low"
    
    def get_schema(self) -> dict:
        """
        Get the OpenAI/Ollama function calling schema for this tool.
        
        Returns:
            Dict in Ollama function calling format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required_parameters,
                },
            },
        }
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
