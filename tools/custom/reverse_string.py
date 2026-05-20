import json

def reverse_string(text: str) -> dict:
    """
    Reverses the input string.

    Parameters:
        text (str): The string to reverse.

    Returns:
        dict: A JSON‑serializable dictionary with keys:
            - success (bool): Indicates if operation succeeded.
            - result (str, optional): The reversed string when successful.
            - error (str, optional): Error message when failed.
    """
    try:
        # Ensure the input is indeed a string
        if not isinstance(text, str):
            raise TypeError("Parameter 'text' must be a string.")
        reversed_text = text[::-1]
        return {"success": True, "result": reversed_text}
    except Exception as e:
        return {"success": False, "error": str(e)}

def register():
    """
    Registers the tool with Jarvis.

    Returns:
        dict: Mapping of tool name to its implementation function.
    """
    return {
        "reverse_string": reverse_string
    }

def schema():
    """
    Provides the OpenAI function‑calling schema for the tool.

    Returns:
        dict: Schema compliant with OpenAI's function calling format.
    """
    return {
        "type": "function",
        "function": {
            "name": "reverse_string",
            "description": "Reverses a given string and returns the reversed result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The string to be reversed."
                    }
                },
                "required": ["text"]
            }
        }
    }