import logging
from tools.system.sandbox import execute_sandboxed

logger = logging.getLogger(__name__)


def sandbox_execute(
    code: str,
    language: str = "python",
    timeout: int = 30,
    install_packages: list = None,
) -> dict:
    """
    Executes Python or PowerShell code inside an isolated, secure digital sandbox.
    
    Parameters
    ----------
    code : str
        The code to execute inside the sandbox.
    language : str, optional
        The programming language of the code, either 'python' or 'powershell'. Defaults to 'python'.
    timeout : int, optional
        Maximum execution time in seconds. Defaults to 30.
    install_packages : list, optional
        List of pip packages to install inside the sandbox before executing Python code.

    Returns
    -------
    dict
        A JSON-serializable dictionary containing the results (stdout, stderr, return_code, success).
    """
    try:
        # Simply delegate to the system sandbox
        result = execute_sandboxed(
            code=code,
            language=language,
            timeout=timeout,
            install_packages=install_packages
        )
        return result
    except Exception as e:
        logger.error(f"sandbox_execute tool failed: {e}")
        return {"success": False, "error": str(e)}


def register():
    """
    Register the tool with Jarvis.
    """
    return {"sandbox_execute": sandbox_execute}


def schema():
    """
    Provide the OpenAI-style function calling schema for the sandbox tool.
    """
    return {
        "type": "function",
        "function": {
            "name": "sandbox_execute",
            "description": "Executes Python or PowerShell code inside a hardened, isolated sandbox environment, keeping Jarvis safe from side-effects or crashes. Use this to safely test generated tools or run experimental code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The exact source code block to execute in the sandbox."
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "powershell"],
                        "description": "The programming language/environment to use. Defaults to 'python'."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds. Defaults to 30."
                    },
                    "install_packages": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Optional list of pip packages to install (Python only) for this run only."
                    }
                },
                "required": ["code"]
            }
        }
    }
