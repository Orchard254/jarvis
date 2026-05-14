"""
Coder Agent - Tier 3 Multi-Agent System

Generates safe, executable Python scripts for task execution.
Includes safety checks and code validation.
"""

import ast
import logging
from typing import Dict, List, Optional, Tuple

from brain.ollama_client import chat
from brain.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)


class CoderAgent:
    """
    Responsible for generating executable code to accomplish tasks.
    
    Capabilities:
    - Code generation from natural language specifications
    - Safety validation (imports, operations)
    - Error detection and self-correction
    - Code optimization
    """
    
    # Allowed standard library modules
    SAFE_STD_MODULES = {
        "os", "sys", "pathlib", "shutil", "glob", "tempfile",
        "json", "csv", "xml", "re", "datetime", "time",
        "subprocess", "threading", "multiprocessing",
        "http", "urllib", "socket",
        "math", "random", "statistics",
        "collections", "itertools", "functools",
        "typing", "dataclasses",
        "logging", "warnings",
        "hashlib", "base64", "hmac",
        "pickle", "copy",
    }
    
    # Dangerous operations to detect
    DANGEROUS_PATTERNS = [
        "eval(", "exec(", "__import__", "compile(",
        "open(/etc/", "rm -rf", "del /", "format c:",
        "subprocess.call.*shell=True",
        "os.system.*rm", "os.system.*del",
    ]
    
    def __init__(self, shared_context=None):
        self._shared_context = shared_context
        self._name = "CoderAgent"
    
    def generate_code(self, specification: str, context: Optional[Dict] = None) -> Dict[str, any]:
        """
        Generate Python code to accomplish the specified task.
        
        Args:
            specification: Natural language description of what the code should do
            context: Optional context including variables, previous results, etc.
            
        Returns:
            Dict with 'code', 'language', 'success', 'explanation', 'warnings'
        """
        if self._shared_context:
            self._shared_context.set_agent_state(self._name, {
                "action": "generate_code",
                "specification": specification[:100]
            })
        
        try:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "system", "content": self._get_coder_instruction()},
            ]
            
            if context:
                ctx_str = f"Available context:\n{context}\n\n"
                messages.append({"role": "system", "content": ctx_str})
            
            messages.append({"role": "user", "content": specification})
            
            result = chat(messages=messages, tools=[], temperature=0.1)
            content = (result.get("content") or "").strip()
            
            # Extract code from response
            code, explanation = self._extract_code(content)
            
            # Validate the generated code
            validation = self._validate_code(code)
            
            response = {
                "code": code,
                "language": "python",
                "success": validation["is_valid"],
                "explanation": explanation or validation.get("notes", ""),
                "warnings": validation.get("warnings", [])
            }
            
            if self._shared_context:
                self._shared_context.record_execution(
                    self._name, "generate_code",
                    {"code_length": len(code), "valid": validation["is_valid"]},
                    success=validation["is_valid"]
                )
            
            logger.info(f"CoderAgent generated {len(code)} chars, valid={validation['is_valid']}")
            return response
            
        except Exception as e:
            logger.error(f"CoderAgent code generation failed: {e}")
            return {
                "code": "",
                "language": "python",
                "success": False,
                "explanation": f"Code generation failed: {str(e)}",
                "warnings": []
            }
    
    def fix_code(self, original_code: str, error_message: str, 
                 context: Optional[Dict] = None) -> Dict[str, any]:
        """
        Analyze and fix broken code.
        
        Implements the self-healing capability by diagnosing errors
        and generating corrected code.
        
        Args:
            original_code: The code that failed
            error_message: The error message from execution
            context: Additional context about the failure including:
                - diagnosis: Error analysis from ExecutorAgent
                - retry_count: How many times this has been attempted
                - previous_fixes: List of previous fix attempts
            
        Returns:
            Dict with 'fixed_code', 'diagnosis', 'success', 'changes_made'
        """
        if self._shared_context:
            self._shared_context.set_agent_state(self._name, {
                "action": "fix_code",
                "error": error_message[:200],
                "context": context
            })
        
        # Extract additional context
        diagnosis = (context or {}).get("diagnosis", {})
        retry_count = (context or {}).get("retry_count", 0)
        previous_fixes = (context or {}).get("previous_fixes", [])
        
        # Build comprehensive error context for the LLM
        error_context = self._build_error_context(error_message, diagnosis, retry_count, previous_fixes)
        
        try:
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "system", "content": self._get_fixer_instruction()},
                {"role": "user", "content": f"""
ORIGINAL CODE THAT FAILED:
```python
{original_code}
```

EXECUTION ERROR:
{error_context}

PREVIOUS FIX ATTEMPTS: {len(previous_fixes)}
{('Previous attempts and their outcomes:' + chr(10) + chr(10).join(previous_fixes)) if previous_fixes else 'This is the first fix attempt.'}

Please analyze the error carefully and provide corrected code.
Your response MUST include:
1. A clear DIAGNOSIS explaining what went wrong
2. Specific CHANGES you are making to fix it
3. The complete FIXED CODE in a Python code block

IMPORTANT: If previous fixes failed, try a different approach.
Do not repeat the same fix strategy.
"""}
            ]
            
            result = chat(messages=messages, tools=[], temperature=0.1)
            content = (result.get("content") or "").strip()
            
            # Extract fixed code
            fixed_code, diagnosis_text = self._extract_code(content)
            
            # Validate the fix
            validation = self._validate_code(fixed_code)
            
            response = {
                "fixed_code": fixed_code,
                "diagnosis": diagnosis_text or self._diagnose_error(error_message, original_code),
                "success": validation["is_valid"],
                "changes_made": self._describe_changes(original_code, fixed_code),
                "warnings": validation.get("warnings", []),
                "retry_context": {
                    "retry_count": retry_count,
                    "previous_attempts": len(previous_fixes)
                }
            }
            
            if self._shared_context:
                self._shared_context.record_execution(
                    self._name, "fix_code",
                    {"diagnosis": response["diagnosis"], "valid": validation["is_valid"], "retry": retry_count},
                    success=validation["is_valid"]
                )
            
            logger.info(f"CoderAgent fix attempt #{retry_count + 1}: {response['diagnosis'][:50]}...")
            return response
            
        except Exception as e:
            logger.error(f"CoderAgent code fix failed: {e}")
            return {
                "fixed_code": "",
                "diagnosis": f"Could not analyze error: {str(e)}",
                "success": False,
                "changes_made": [],
                "warnings": [],
                "retry_context": {"retry_count": retry_count, "error": str(e)}
            }
    
    def _build_error_context(self, error_message: str, diagnosis: Dict, 
                              retry_count: int, previous_fixes: List[str]) -> str:
        """Build comprehensive error context for the LLM."""
        context_parts = [f"Error: {error_message}"]
        
        if diagnosis:
            error_type = diagnosis.get("type", "unknown")
            severity = diagnosis.get("severity", "medium")
            suggested = diagnosis.get("suggested_action", "retry_with_fix")
            context_parts.append(f"\nError Type: {error_type}")
            context_parts.append(f"\nSeverity: {severity}")
            context_parts.append(f"\nSuggested Action: {suggested}")
        
        if retry_count > 0:
            context_parts.append(f"\n\n*** RETRY ATTEMPT #{retry_count + 1} ***")
            context_parts.append(f"\nPrevious {len(previous_fixes)} fix attempts have failed.")
            context_parts.append("\nThe LLM should try a DIFFERENT approach than previous attempts.")
        
        return "\n".join(context_parts)
    
    def _get_coder_instruction(self) -> str:
        return (
            "You are an expert Python programmer for a desktop AI agent.\n"
            "Generate clean, safe, executable Python code to accomplish the user's task.\n"
            "\n"
            "SAFE TO USE (pre-approved Windows automation modules):\n"
            "- win32gui, win32con, win32api, win32process (window management)\n"
            "- ctypes (low-level Windows API calls)\n"
            "- pyautogui (keyboard/mouse simulation)\n"
            "- subprocess (run commands safely with capture_output=True)\n"
            "- os, pathlib, shutil (file operations - but NOT shutil.rmtree)\n"
            "- requests, urllib, socket (network operations)\n"
            "- json, csv, re, datetime, time (standard utilities)\n"
            "- PIL/pytesseract (image processing and OCR)\n"
            "- All modules listed in ALLOWED_IMPORTS\n"
            "\n"
            "NEVER USE (will be blocked):\n"
            "- eval(), exec(), __import__, compile()\n"
            "- shutil.rmtree() or recursive deletion\n"
            "- os.system() with shell=True\n"
            "- Direct access to C:/Windows/System32\n"
            "- format, diskpart, bcdedit commands\n"
            "\n"
            "Rules:\n"
            "- Include proper error handling with try/except\n"
            "- Add comments explaining key steps\n"
            "- Keep code concise but readable\n"
            "- Assume the code runs in a Windows environment\n"
            "- Print success/failure messages for visibility\n"
            "\n"
            "Format your response as:\n"
            "EXPLANATION: Brief description of what the code does\n"
            "```python\n"
            "# Your code here\n"
            "```"
        )
    
    def _get_fixer_instruction(self) -> str:
        return (
            "You are an expert code debugger.\n"
            "Analyze the provided code and error message, then fix the issue.\n"
            "\n"
            "Process:\n"
            "1. Identify the root cause of the error\n"
            "2. Explain what went wrong\n"
            "3. Provide corrected code\n"
            "4. List the changes made\n"
            "\n"
            "Format:\n"
            "DIAGNOSIS: Explanation of the error\n"
            "CHANGES: List of fixes applied\n"
            "```python\n"
            "# Fixed code here\n"
            "```"
        )
    
    def _extract_code(self, content: str) -> Tuple[str, str]:
        """Extract code block and explanation from LLM response."""
        code = ""
        explanation = ""
        
        # Try to find markdown code block
        import re
        code_match = re.search(r'```(?:python)?\s*(.*?)```', content, re.DOTALL | re.IGNORECASE)
        if code_match:
            code = code_match.group(1).strip()
            # Get text before code block as explanation
            explanation = content[:code_match.start()].strip()
            if not explanation:
                explanation = content[code_match.end():].strip()
        else:
            # No code block found, treat entire response as potentially code
            lines = content.split("\n")
            code_lines = []
            for line in lines:
                if line.strip() and not line.strip().startswith(("#", "EXPLANATION:", "DIAGNOSIS:")):
                    code_lines.append(line)
            code = "\n".join(code_lines)
            explanation = content
        
        return code, explanation
    
    def _validate_code(self, code: str) -> Dict[str, any]:
        """Validate code for safety and syntax."""
        warnings = []
        notes = []
        
        if not code.strip():
            return {"is_valid": False, "warnings": ["Empty code"], "notes": ""}
        
        # Syntax check
        try:
            ast.parse(code)
            notes.append("Syntax valid")
        except SyntaxError as e:
            return {
                "is_valid": False,
                "warnings": [f"Syntax error: {str(e)}"],
                "notes": ""
            }
        
        # Check for dangerous patterns
        code_lower = code.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            import re
            try:
                if re.search(re.escape(pattern), code_lower):
                    warnings.append(f"Dangerous pattern detected: {pattern}")
            except re.error:
                # Skip invalid regex patterns
                continue
        
        # Check imports
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name.split(".")[0]
                        if mod not in self.SAFE_STD_MODULES:
                            warnings.append(f"Potentially unsafe import: {mod}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        mod = node.module.split(".")[0]
                        if mod not in self.SAFE_STD_MODULES:
                            warnings.append(f"Potentially unsafe import: {mod}")
        except:
            pass
        
        is_valid = len(warnings) == 0 or all("potentially unsafe import" in w.lower() for w in warnings)
        
        return {
            "is_valid": is_valid,
            "warnings": warnings,
            "notes": "; ".join(notes)
        }
    
    def _diagnose_error(self, error_message: str, code: str) -> str:
        """Provide a diagnosis based on error message patterns."""
        error_lower = error_message.lower()
        
        if "syntaxerror" in error_lower or "invalid syntax" in error_lower:
            return "Syntax error in the code"
        elif "nameerror" in error_lower or "not defined" in error_lower:
            return "Undefined variable or function name"
        elif "typeerror" in error_lower:
            return "Type mismatch or incorrect operation"
        elif "attributeerror" in error_lower:
            return "Accessing non-existent attribute"
        elif "filenotfounderror" in error_lower or "no such file" in error_lower:
            return "File path does not exist"
        elif "permissionerror" in error_lower or "access is denied" in error_lower:
            return "Insufficient permissions"
        elif "moduleNotFoundError" in error_lower or "no module named" in error_lower:
            return "Missing required module"
        elif "timeout" in error_lower or "timed out" in error_lower:
            return "Operation timed out"
        elif "connection" in error_lower:
            return "Network connection issue"
        else:
            return f"Runtime error: {error_message[:100]}"
    
    def _describe_changes(self, original: str, fixed: str) -> List[str]:
        """Describe what changed between original and fixed code."""
        changes = []
        
        orig_lines = set(original.split("\n"))
        fixed_lines = set(fixed.split("\n"))
        
        added = fixed_lines - orig_lines
        removed = orig_lines - fixed_lines
        
        if added:
            changes.append(f"Added {len(added)} lines")
        if removed:
            changes.append(f"Removed {len(removed)} lines")
        
        if not changes:
            changes.append("Modified existing code")
        
        return changes
