"""
Tool Creator Sub-Agent — dynamically writes and registers new Python tools.

Handles tasks like:
  - "Create a tool to get the current price of Bitcoin"
  - "Build a custom parser for this log format"

It writes the Python code, ensures it matches the custom tool schema,
and saves it to tools/custom/.
"""

import logging
import time
import os
import re

from agents.base_agent import SubAgentBase, SubAgentResult, SubAgentTask
from agents.sub_agent_registry import register
from brain import ollama_client
from brain.prompt_builder import _load_prompt

logger = logging.getLogger(__name__)

class ToolCreatorAgent(SubAgentBase):
    name = "tool_creator"
    description = (
        "Writes and permanently installs new Python custom tools. "
        "Use this ONLY when Jarvis needs a permanent new capability that cannot "
        "be fulfilled by existing tools or a simple one-off execute_code script."
    )
    capabilities = [
        "generate_tool_code",
        "install_tool",
    ]

    def run(self, task: SubAgentTask) -> SubAgentResult:
        start = time.time()
        goal = task.goal
        ctx = task.context
        
        self._log.info(f"[{task.task_id}] Tool Creator task: {goal[:100]}")

        # 1. Build the prompt
        system_prompt = _load_prompt("tool_creator")
        
        user_message = f"Goal for new tool: {goal}\n"
        if ctx:
            user_message += f"Context: {ctx}\n"
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # 2. Query LLM to generate the code
        self._log.info(f"[{task.task_id}] Generating tool code via LLM...")
        try:
            # We use a relatively high reasoning effort since coding requires precision
            llm_result = ollama_client.chat(
                messages=messages,
                temperature=0.1,
            )
            content = llm_result.get("content", "")
        except Exception as e:
            self._log.error(f"[{task.task_id}] LLM generation failed: {e}")
            return SubAgentResult(
                success=False,
                summary="Failed to generate tool code due to LLM error.",
                error=str(e),
                agent_name=self.name
            )

        # 3. Extract the Python code block
        match = re.search(r"```python\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if not match:
            self._log.error(f"[{task.task_id}] No valid Python code block found in response.")
            return SubAgentResult(
                success=False,
                summary="LLM did not return a valid Python code block.",
                error="Formatting error",
                data={"raw_response": content},
                agent_name=self.name
            )
            
        python_code = match.group(1).strip()
        
        # Basic validation: ensure register and schema exist
        if "def register" not in python_code or "def schema" not in python_code:
            return SubAgentResult(
                success=False,
                summary="Generated code is missing required `register()` or `schema()` functions.",
                error="Invalid API structure",
                data={"code": python_code},
                agent_name=self.name
            )

        # Extract tool name from the schema definition (simple heuristic)
        # We look for "name": "something" inside the schema or the first def before register
        tool_name_match = re.search(r"\"name\"\s*:\s*\"([a-zA-Z0-9_]+)\"", python_code)
        if tool_name_match:
            tool_name = tool_name_match.group(1)
        else:
            # Fallback: grab the first function defined that isn't register or schema
            func_match = re.search(r"def ([a-zA-Z0-9_]+)\(", python_code)
            if func_match and func_match.group(1) not in ("register", "schema"):
                tool_name = func_match.group(1)
            else:
                tool_name = f"custom_tool_{int(time.time())}"

        # --- SANDBOX AUTO-TESTING STEP ---
        self._log.info(f"[{task.task_id}] Running sandbox validation tests for '{tool_name}'...")
        try:
            from tools.system.sandbox import execute_sandboxed
            
            # Find potential packages to install in sandbox
            imported_pkgs = []
            import sys as _sys
            std_libs = {
                "os", "sys", "time", "re", "json", "math", "datetime", "hashlib", "urllib", 
                "collections", "itertools", "functools", "typing", "logging", "shutil", 
                "tempfile", "subprocess", "xml", "csv", "ast", "inspect", "uuid", "random",
                "traceback", "base64", "threading", "queue", "socket", "struct", "select",
                "asyncio", "argparse", "pathlib", "io", "copy", "platform", "ctypes"
            }
            # Simple regex to find imports like "import x" or "from x import y"
            pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", re.MULTILINE)
            for match in pattern.finditer(python_code):
                pkg = match.group(1)
                if pkg not in _sys.builtin_module_names and pkg not in std_libs:
                    imported_pkgs.append(pkg)
            
            # Deduplicate packages
            imported_pkgs = list(set(imported_pkgs))
            if imported_pkgs:
                self._log.info(f"[{task.task_id}] Identified external packages to install in sandbox: {imported_pkgs}")

            # Define the test driver script
            test_driver = f"""
try:
    import {tool_name}
    assert hasattr({tool_name}, 'register'), "Missing register() function in {tool_name}"
    assert hasattr({tool_name}, 'schema'), "Missing schema() function in {tool_name}"
    
    registry = {tool_name}.register()
    assert isinstance(registry, dict), "register() must return a dict"
    assert len(registry) > 0, "register() returned an empty dict"
    
    schema = {tool_name}.schema()
    assert isinstance(schema, dict), "schema() must return a dict"
    assert "function" in schema or schema.get("type") == "function", "schema must contain function definitions"
    
    # Verify all registered functions are callable
    for name, func in registry.items():
        assert callable(func), f"Registered object '{{name}}' is not callable"
        
    print("SANDBOX_TEST_PASSED")
except Exception as e:
    import sys
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""

            # Run in sandbox
            sandbox_res = execute_sandboxed(
                code=test_driver,
                language="python",
                timeout=30,
                install_packages=imported_pkgs if imported_pkgs else None,
                files={f"{tool_name}.py": python_code}
            )
            
            if not sandbox_res.get("success", False):
                err_msg = sandbox_res.get("error") or sandbox_res.get("stderr") or "Unknown error"
                self._log.error(f"[{task.task_id}] Sandbox validation failed:\n{err_msg}")
                return SubAgentResult(
                    success=False,
                    summary=f"Sandbox validation failed for new tool '{tool_name}'. Code did not execute cleanly in the sandbox.",
                    error=err_msg,
                    data={"code": python_code, "sandbox_result": sandbox_res},
                    agent_name=self.name
                )
            
            if "SANDBOX_TEST_PASSED" not in sandbox_res.get("stdout", ""):
                self._log.error(f"[{task.task_id}] Sandbox validation did not finish successfully.")
                err_msg = sandbox_res.get("stderr") or "No validation output"
                return SubAgentResult(
                    success=False,
                    summary=f"Sandbox validation did not finish successfully for '{tool_name}'.",
                    error=err_msg,
                    data={"code": python_code, "sandbox_result": sandbox_res},
                    agent_name=self.name
                )
                
            self._log.info(f"[{task.task_id}] Sandbox validation PASSED for '{tool_name}'!")
            
        except Exception as e:
            self._log.error(f"[{task.task_id}] Sandbox validation system error: {e}")
            return SubAgentResult(
                success=False,
                summary=f"Sandbox validation crashed due to system error.",
                error=str(e),
                agent_name=self.name
            )

        # 4. Save the file to tools/custom/
        custom_tools_dir = os.path.join("tools", "custom")
        os.makedirs(custom_tools_dir, exist_ok=True)
        
        file_path = os.path.join(custom_tools_dir, f"{tool_name}.py")
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(python_code)
            self._log.info(f"[{task.task_id}] Successfully saved new tool to {file_path}")
        except Exception as e:
            self._log.error(f"[{task.task_id}] Failed to save tool to disk: {e}")
            return SubAgentResult(
                success=False,
                summary=f"Failed to write file {file_path}",
                error=str(e),
                agent_name=self.name
            )
            
        elapsed = round(time.time() - start, 2)
        summary = (
            f"Successfully created and installed new tool: `{tool_name}`.\n"
            f"File saved to `{file_path}`.\n"
            "Jarvis may need to be restarted or reload its tools for the new tool to become available."
        )

        return SubAgentResult(
            success=True,
            summary=summary,
            data={
                "tool_name": tool_name,
                "file_path": file_path,
                "code": python_code
            },
            elapsed_s=elapsed,
            agent_name=self.name
        )

# Auto-register
register(ToolCreatorAgent())
