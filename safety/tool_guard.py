"""
AST-based import allowlist + environment stripping. Replaces string denylist.
"""

import ast
import logging
import os

from settings import ALLOWED_IMPORTS, BLOCKED_PATHS, EXECUTE_CODE_TIMEOUT

logger = logging.getLogger(__name__)

from safety.path_guard import SENSITIVE_PATH_FRAGMENTS

# ---------------------------------------------------------------------------
# Secret-bearing environment variable keywords.
# A variable is stripped from the safe env when its upper-cased name either
# *is* one of these keywords exactly, or *ends with* "_<keyword>" — so that
# real-world names like GITHUB_TOKEN, OPENAI_API_KEY, or DB_PASSWORD are all
# caught without risking false positives on common system variables.
# ---------------------------------------------------------------------------
_SECRET_KEYWORDS = frozenset(
    {
        "PASSWORD",
        "PASSWD",
        "SECRET",
        "API_KEY",
        "ACCESS_KEY",
        "PRIVATE_KEY",
        "TOKEN",
        "ACCESS_TOKEN",
        "AUTH_TOKEN",
        "CREDENTIAL",
        "CREDENTIALS",
        "KEY",
    }
)


def _is_secret_env_key(key: str) -> bool:
    """Return True if *key* looks like it holds a secret value."""
    upper = key.upper()
    # Exact match preserves the original behaviour.
    if upper in _SECRET_KEYWORDS:
        return True
    # Suffix match catches GITHUB_TOKEN, OPENAI_API_KEY, DB_PASSWORD, etc.
    for kw in _SECRET_KEYWORDS:
        if upper.endswith("_" + kw):
            return True
    return False


_POWERSHELL_BLOCKED_CMD = frozenset({
    "invoke-expression", "iex",
    "invoke-command", "icm",
    "invoke-webrequest", "iwr", "curl", "wget",
    "invoke-restmethod", "irm",
    "start-process", "start",
    "new-object net.webclient",
    "downloadstring", "downloadfile",
    "add-type",
    "set-executionpolicy",
    "new-object system.net.webclient",
    "remove-item", "del", "rm",
    "format-volume", "clear-disk",
    "stop-computer", "restart-computer",
    "shutdown", "restart",
})


def check_imports(code: str, language: str = "python"):
    if language != "python":
        return _check_powershell(code)
    if len(code) > 100000:
        return False, "Code too large for safety check"
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod not in ALLOWED_IMPORTS:
                        return False, f"Import not allowed: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod not in ALLOWED_IMPORTS:
                        return False, f"Import not allowed: {node.module}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        mod = str(node.args[0].value).split(".")[0]
                        if mod not in ALLOWED_IMPORTS:
                            return False, f"Import not allowed: {mod}"
                    return False, "Dynamic import not allowed (__import__)"
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                ):
                    return (
                        False,
                        "importlib.import_module() not allowed (use direct imports)",
                    )
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error: {e}"


def _check_powershell(code: str):
    """Check PowerShell code for dangerous commands."""
    lower = code.lower()
    for cmd in _POWERSHELL_BLOCKED_CMD:
        if cmd in lower:
            return False, f"PowerShell command not allowed: '{cmd}'"
    return True, ""


def check_paths(args: dict):
    """
    Reject tool calls whose arguments reference a blocked or sensitive path.

    Two layers of checks are applied:
      1. Settings-driven BLOCKED_PATHS (system directories such as System32).
      2. Hardcoded _SENSITIVE_PATH_FRAGMENTS (.ssh, .aws, credential files,
         etc.) that must never be accessible regardless of settings.
    """
    args_str = str(args).lower().replace("\\", "/")

    # 1. Settings-driven blocked paths (system directories, etc.)
    for path in BLOCKED_PATHS:
        if path.lower().replace("\\", "/") in args_str:
            return False, f"Blocked path in args: '{path}'"

    # 2. Hardcoded sensitive path fragments (SSH keys, cloud credentials, …)
    for fragment in SENSITIVE_PATH_FRAGMENTS:
        if fragment.lower() in args_str:
            return False, f"Blocked sensitive path in args: '{fragment}'"

    return True, ""


def get_safe_env() -> dict:
    """
    Return a sanitised copy of the current environment suitable for passing to
    subprocesses.

    The full original PATH is preserved so that tools installed by the user
    (winget, git, npm, pipx applications, etc.) remain reachable.  Only
    environment variables whose names indicate they hold secrets — passwords,
    API keys, tokens, private keys, etc. — are removed.
    """
    env = os.environ.copy()

    stripped = []
    for key in list(env.keys()):
        if _is_secret_env_key(key):
            del env[key]
            stripped.append(key)

    if stripped:
        logger.debug(
            "get_safe_env: stripped %d secret env var(s): %s", len(stripped), stripped
        )

    return env
