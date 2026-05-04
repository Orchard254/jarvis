"""
tools/data/calculate.py — Calculator tool

Tool for: calculate mathematical expressions
Uses Python's eval with safety restrictions.
"""

import logging
import re
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("calculate_tools")


def safe_calculate(expression: str) -> tuple[bool, Any]:
    """
    Safely evaluate a mathematical expression.
    
    Args:
        expression: Mathematical expression string
        
    Returns:
        Tuple of (success, result_or_error)
    """
    # Only allow safe characters
    allowed_pattern = r'^[\d\s\+\-\*\/\.\(\)\%\^\s]+$'
    
    if not re.match(allowed_pattern, expression):
        return False, "Invalid characters in expression"
    
    # Block dangerous patterns
    dangerous = ["__", "import", "exec", "eval", "lambda", "def ", "class "]
    expr_lower = expression.lower()
    for pattern in dangerous:
        if pattern in expr_lower:
            return False, f"Dangerous pattern blocked: {pattern}"
    
    try:
        # Replace ^ with ** for exponentiation
        expression = expression.replace("^", "**")
        
        # Evaluate safely
        result = eval(expression, {"__builtins__": {}}, {})
        
        # Format result
        if isinstance(result, float):
            if result == int(result):
                result = int(result)
            else:
                result = round(result, 6)
        
        return True, result
        
    except ZeroDivisionError:
        return False, "Division by zero"
    except SyntaxError:
        return False, "Invalid syntax"
    except Exception as e:
        return False, str(e)


class CalculateTool(BaseTool):
    """Calculate a mathematical expression."""
    
    name = "calculate"
    description = "Calculate the result of a mathematical expression. Supports +, -, *, /, %, ^ (power), and parentheses."
    parameters = {
        "expression": {
            "type": "string",
            "description": "Mathematical expression to evaluate (e.g., '2 + 2', '(10 * 5) / 2', '2^8')",
        },
    }
    required_parameters = ["expression"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        expression = kwargs.get("expression")
        if not expression:
            return False, "expression parameter is required"
        if not isinstance(expression, str):
            return False, "expression must be a string"
        if len(expression) > 200:
            return False, "Expression too long (max 200 characters)"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        expression = kwargs["expression"].strip()
        
        success, result = safe_calculate(expression)
        
        if success:
            return ToolResult.ok(f"{expression} = {result}")
        else:
            return ToolResult.fail(error=f"Calculation error: {result}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.1
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
CALCULATE_TOOLS = [
    CalculateTool,
]
