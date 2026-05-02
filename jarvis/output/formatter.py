"""
Formatter Module

Provides text formatting utilities for JARVIS output.
Handles structured formatting of tool results, errors, and responses.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OutputFormatter:
    """
    Formats output from JARVIS for display.
    
    Provides consistent formatting for different types of output.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize formatter.
        
        Args:
            config: Configuration dict
        """
        self.config = config or {}
        self.verbose = self.config.get('verbose_output', False)
        self.color_enabled = self.config.get('color_output', True)
        
    def format_tool_result(self, result: Dict[str, Any]) -> str:
        """
        Format a tool execution result.
        
        Args:
            result: Tool result dict with keys: success, output, error, exit_code, verified, verify_msg
            
        Returns:
            Formatted string
        """
        lines = []
        
        # Status indicator
        if result.get('success', False):
            status = "✓"
            if self.color_enabled:
                status = f"\033[92m{status}\033[0m"  # Green
        else:
            status = "✗"
            if self.color_enabled:
                status = f"\033[91m{status}\033[0m"  # Red
        
        lines.append(f"{status} Tool Result")
        
        # Output
        if result.get('output'):
            output = result['output']
            if isinstance(output, str):
                # Truncate long output
                if len(output) > 500 and not self.verbose:
                    output = output[:500] + "... (truncated)"
                lines.append(f"  Output: {output}")
            elif isinstance(output, (list, dict)):
                import json
                lines.append(f"  Output: {json.dumps(output, indent=2)}")
        
        # Error
        if result.get('error'):
            error = result['error']
            if self.color_enabled:
                error = f"\033[91m{error}\033[0m"
            lines.append(f"  Error: {error}")
        
        # Exit code
        if 'exit_code' in result:
            exit_code = result['exit_code']
            if exit_code != 0 and self.color_enabled:
                exit_code = f"\033[91m{exit_code}\033[0m"
            lines.append(f"  Exit Code: {exit_code}")
        
        # Verification
        if result.get('verified') is not None:
            verified = "Verified" if result['verified'] else "Not Verified"
            lines.append(f"  Verification: {verified}")
            
            if result.get('verify_msg'):
                lines.append(f"  Note: {result['verify_msg']}")
        
        return "\n".join(lines)
    
    def format_error(self, error: str, context: str = "") -> str:
        """
        Format an error message.
        
        Args:
            error: Error message
            context: Optional context about where the error occurred
            
        Returns:
            Formatted error string
        """
        if self.color_enabled:
            error = f"\033[91m{error}\033[0m"
        
        if context:
            return f"[ERROR in {context}] {error}"
        return f"[ERROR] {error}"
    
    def format_info(self, message: str) -> str:
        """
        Format an info message.
        
        Args:
            message: Info message
            
        Returns:
            Formatted info string
        """
        if self.color_enabled:
            message = f"\033[94m{message}\033[0m"  # Blue
        return f"[INFO] {message}"
    
    def format_success(self, message: str) -> str:
        """
        Format a success message.
        
        Args:
            message: Success message
            
        Returns:
            Formatted success string
        """
        if self.color_enabled:
            message = f"\033[92m{message}\033[0m"  # Green
        return f"[SUCCESS] {message}"
    
    def format_warning(self, message: str) -> str:
        """
        Format a warning message.
        
        Args:
            message: Warning message
            
        Returns:
            Formatted warning string
        """
        if self.color_enabled:
            message = f"\033[93m{message}\033[0m"  # Yellow
        return f"[WARNING] {message}"
    
    def format_response(self, response: str, speaker: str = "JARVIS") -> str:
        """
        Format a conversational response.
        
        Args:
            response: Response text
            speaker: Speaker name
            
        Returns:
            Formatted response
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}] {speaker}: {response}"
    
    def format_plan(self, plan: Dict[str, Any]) -> str:
        """
        Format a task plan.
        
        Args:
            plan: Plan dict with steps
            
        Returns:
            Formatted plan
        """
        lines = ["📋 Task Plan"]
        
        if plan.get('goal'):
            lines.append(f"Goal: {plan['goal']}")
        
        steps = plan.get('steps', [])
        if steps:
            lines.append("Steps:")
            for i, step in enumerate(steps, 1):
                step_text = step.get('description', str(step))
                tool = step.get('tool', 'unknown')
                lines.append(f"  {i}. [{tool}] {step_text}")
        
        if plan.get('estimated_duration'):
            lines.append(f"Estimated Duration: {plan['estimated_duration']}")
        
        return "\n".join(lines)
    
    def format_memory_retrieval(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format retrieved memories.
        
        Args:
            memories: List of memory dicts
            
        Returns:
            Formatted memories
        """
        if not memories:
            return "No relevant memories found."
        
        lines = [f"🧠 Retrieved {len(memories)} memories:"]
        for mem in memories[:5]:  # Show top 5
            content = mem.get('content', '')[:100]
            score = mem.get('score', 0)
            lines.append(f"  • [{score:.2f}] {content}...")
        
        if len(memories) > 5:
            lines.append(f"  ... and {len(memories) - 5} more")
        
        return "\n".join(lines)
    
    def disable_colors(self) -> None:
        """Disable color output."""
        self.color_enabled = False
    
    def enable_colors(self) -> None:
        """Enable color output."""
        self.color_enabled = True
    
    def set_verbose(self, verbose: bool) -> None:
        """Set verbose mode."""
        self.verbose = verbose
