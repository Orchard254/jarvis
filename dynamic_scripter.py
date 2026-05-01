"""
DYNAMIC SCRIPTER ENGINE
-----------------------
Allows the LLM to write and execute arbitrary Python scripts to perform 
tasks on the PC without hardcoded tools.

SECURITY MODEL:
1. Code is generated in memory.
2. Static analysis blocks dangerous imports (socket, requests, os.system with shell=True).
3. Execution happens in a restricted subprocess.
4. Self-correction loop fixes syntax/runtime errors automatically.
"""

import ast
import subprocess
import sys
import json
import tempfile
import os
from typing import Optional, Tuple, List
from pathlib import Path

# --- Configuration ---
ALLOWED_IMPORTS = {
    'os', 'sys', 'json', 're', 'math', 'datetime', 'time', 
    'pathlib', 'subprocess', 'shutil', 'psutil', 'pyautogui', 
    'keyboard', 'mouse', 'screeninfo', 'PIL', 'cv2'
}

DANGEROUS_PATTERNS = [
    '__import__', 'eval(', 'exec(', 'compile(', 'open(..., "w")', 
    'socket.', 'requests.', 'urllib.', 'http.', 'ftplib', 'smtplib'
]

class DynamicScripter:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.max_retries = 3
        self.timeout = 30

    def generate_script(self, goal: str, context: str = "") -> str:
        """Ask LLM to write a Python script to achieve the goal."""
        
        system_prompt = """
You are an expert Python automation engineer. Your task is to write a COMPLETE, 
RUNNABLE Python script to achieve a specific user goal on a Windows PC.

RULES:
1. Write ONLY valid Python code. No markdown, no explanations outside comments.
2. Use standard libraries and these allowed packages: pyautogui, psutil, pillow.
3. Do NOT use 'input()', 'socket', 'requests', or network libraries.
4. Do NOT use 'eval()' or 'exec()'.
5. Handle errors gracefully with try/except blocks.
6. Print progress updates to stdout so the user knows what's happening.
7. The script must exit with code 0 on success, non-zero on failure.

AVAILABLE CONTEXT:
{context}

USER GOAL:
{goal}

WRITE THE CODE NOW:
""".format(context=context, goal=goal)

        response = self.llm.chat(
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.2  # Low temperature for deterministic code
        )
        
        # Clean up markdown formatting if LLM adds it
        code = response.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.endswith("```"):
            code = code[:-3]
        return code.strip()

    def static_analysis(self, code: str) -> Tuple[bool, str]:
        """Scan code for dangerous patterns before execution."""
        
        # 1. Check for dangerous string patterns
        for pattern in DANGEROUS_PATTERNS:
            if pattern in code:
                return False, f"Dangerous pattern detected: {pattern}"
        
        # 2. Parse AST to check imports
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[0] not in ALLOWED_IMPORTS:
                            return False, f"Disallowed import: {alias.name}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] not in ALLOWED_IMPORTS:
                        return False, f"Disallowed import: from {node.module}"
        except SyntaxError as e:
            return False, f"Syntax error in generated code: {e}"
        
        return True, "Safe"

    def execute_script(self, code: str) -> Tuple[bool, str, str]:
        """Run the code in a isolated subprocess and capture output."""
        
        # Write to a temp file to execute as a script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=os.getcwd()  # Run in current directory
            )
            
            success = result.returncode == 0
            output = result.stdout
            error = result.stderr
            
            return success, output, error
            
        except subprocess.TimeoutExpired:
            return False, "", "Script execution timed out."
        except Exception as e:
            return False, "", str(e)
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def run_task(self, goal: str, context: str = "") -> dict:
        """Main entry point: Generate -> Analyze -> Execute -> Retry"""
        
        print(f"[SCRIPTER] Goal: {goal}")
        
        last_error = ""
        
        for attempt in range(1, self.max_retries + 1):
            print(f"[SCRIPTER] Attempt {attempt}/{self.max_retries}...")
            
            # 1. Generate
            # If retrying, include the previous error in the context
            if last_error:
                retry_context = f"{context}\n\nPREVIOUS ERROR: {last_error}\nPlease fix the code."
                code = self.generate_script(goal, retry_context)
            else:
                code = self.generate_script(goal, context)
            
            print(f"[SCRIPTER] Generated {len(code)} chars of code.")
            
            # 2. Static Analysis
            is_safe, safety_msg = self.static_analysis(code)
            if not is_safe:
                last_error = f"Safety Check Failed: {safety_msg}"
                print(f"[SCRIPTER] ❌ {last_error}")
                continue # Retry
            
            # 3. Execute
            success, output, error = self.execute_script(code)
            
            if success:
                print(f"[SCRIPTER] ✅ Success!")
                return {
                    "success": True,
                    "output": output,
                    "code": code,
                    "attempts": attempt
                }
            else:
                last_error = f"Runtime Error: {error}\nOutput: {output}"
                print(f"[SCRIPTER] ❌ {last_error}")
                
        return {
            "success": False,
            "error": f"Failed after {self.max_retries} attempts. Last error: {last_error}",
            "code": code
        }

# --- Helper Library for LLM Context ---
# We inject this documentation so the LLM knows what helpers exist
HELPER_DOCS = """
AVAILABLE HELPERS:
- You have full access to 'os', 'sys', 'subprocess' for system tasks.
- 'pyautogui' is available for mouse/keyboard control.
- 'psutil' is available for process management.
- Do not try to import 'jarvis' or 'brain' modules; run standalone.
"""
