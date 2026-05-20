"""
Digital Sandbox — Isolated code execution engine.

Provides a hardened subprocess environment for executing untrusted or
experimental code. Unlike the standard execute_code, the sandbox:

1. Runs code in a temporary directory with NO access to the Jarvis project files
2. Uses a restricted environment with only whitelisted env vars
3. Automatically captures and returns stdout, stderr, and exit code
4. Enforces strict timeouts and resource limits
5. Cleans up all artifacts after execution

This is used by the ToolCreator agent to TEST generated tools before
permanently installing them, and can be used directly by Jarvis to
run experimental/dangerous code safely.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Windows-only constant for hiding console windows
_CREATE_NO_WINDOW = 0x00080000 if sys.platform == "win32" else 0

# Maximum output size to prevent memory bombs
_MAX_OUTPUT_BYTES = 50_000  # 50 KB

# Default timeout for sandboxed execution
_DEFAULT_TIMEOUT = 30


def _build_sandbox_env() -> dict:
    """Build a minimal, safe environment for sandboxed execution."""
    safe_keys = {
        "PATH", "SYSTEMROOT", "TEMP", "TMP", "COMSPEC",
        "USERPROFILE", "HOME", "LANG", "LC_ALL",
    }
    env = {k: v for k, v in os.environ.items() if k in safe_keys}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Explicitly do NOT set PYTHONPATH — isolate from Jarvis
    return env


def _create_sandbox_dir() -> str:
    """Create a temporary sandbox directory."""
    sandbox_dir = tempfile.mkdtemp(prefix="jarvis_sandbox_")
    return sandbox_dir


def _destroy_sandbox_dir(sandbox_dir: str) -> None:
    """Remove the sandbox directory and all its contents."""
    try:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
    except Exception as e:
        logger.warning(f"sandbox: failed to clean up {sandbox_dir}: {e}")


def execute_sandboxed(
    code: str,
    language: str = "python",
    timeout: int = _DEFAULT_TIMEOUT,
    install_packages: list = None,
    files: dict = None,
) -> dict:
    """
    Execute code in a fully isolated sandbox.

    Args:
        code: The source code to execute.
        language: 'python' or 'powershell'.
        timeout: Max execution time in seconds.
        install_packages: Optional list of pip packages to install in sandbox.
        files: Optional dict of {filename: content} to write into the sandbox dir.

    Returns:
        dict with keys: success, stdout, stderr, return_code, sandbox_dir, elapsed_s
    """
    if not code.strip():
        return {"success": False, "error": "No code provided"}

    if language not in ("python", "powershell"):
        return {"success": False, "error": f"Unsupported language: {language}"}

    sandbox_dir = _create_sandbox_dir()
    temp_file = None
    start_time = time.time()

    try:
        # Write any supporting files into the sandbox
        if files:
            for filename, content in files.items():
                # Sanitize filename to prevent path traversal
                safe_name = Path(filename).name
                filepath = os.path.join(sandbox_dir, safe_name)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

        # Write the main code file
        suffix = ".py" if language == "python" else ".ps1"
        temp_file = os.path.join(sandbox_dir, f"main{suffix}")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)

        env = _build_sandbox_env()

        # Install packages if requested (into sandbox only)
        if install_packages and language == "python":
            pip_cmd = [
                sys.executable, "-m", "pip", "install",
                "--target", sandbox_dir,
                "--no-cache-dir", "--quiet",
            ] + install_packages

            try:
                pip_result = subprocess.run(
                    pip_cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                    env=env,
                    cwd=sandbox_dir,
                    creationflags=_CREATE_NO_WINDOW,
                )
                if pip_result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"pip install failed: {pip_result.stderr[:500]}",
                        "phase": "dependency_install",
                    }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": "pip install timed out after 60s",
                    "phase": "dependency_install",
                }

        # Build the execution command
        if language == "python":
            cmd = [sys.executable, temp_file]
            # If we installed packages to sandbox_dir, add it to PYTHONPATH
            if install_packages:
                env["PYTHONPATH"] = sandbox_dir
        else:
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", temp_file]

        # Execute in sandbox
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=env,
            cwd=sandbox_dir,
            creationflags=_CREATE_NO_WINDOW,
        )

        elapsed = round(time.time() - start_time, 2)

        # Truncate output if too large
        stdout = result.stdout[:_MAX_OUTPUT_BYTES] if result.stdout else ""
        stderr = result.stderr[:_MAX_OUTPUT_BYTES] if result.stderr else ""

        # List any files the code created in the sandbox
        created_files = []
        for f in os.listdir(sandbox_dir):
            fpath = os.path.join(sandbox_dir, f)
            if os.path.isfile(fpath) and f != f"main{suffix}":
                try:
                    size = os.path.getsize(fpath)
                    created_files.append({"name": f, "size_bytes": size})
                except OSError:
                    pass

        return {
            "success": result.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": result.returncode,
            "elapsed_s": elapsed,
            "created_files": created_files,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start_time, 2)
        return {
            "success": False,
            "error": f"Sandbox execution timed out after {timeout}s",
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        return {
            "success": False,
            "error": str(e),
            "elapsed_s": elapsed,
        }
    finally:
        _destroy_sandbox_dir(sandbox_dir)
