import logging
from autonomous.context_recorder import search_memory

logger = logging.getLogger(__name__)

def recall_memory(query: str, limit: int = 5) -> dict:
    """
    Search the Context Recorder's vector database of past screen states.
    """
    try:
        results = search_memory(query, n_results=limit)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"recall_memory failed: {e}")
        return {"success": False, "error": str(e)}

def register():
    return {"recall_memory": recall_memory}

def schema():
    return {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Searches the user's past screen context history (Recall Engine) to answer questions about what they were looking at in the past.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The semantic query, e.g., 'GitHub repository about AI agents' or 'that email from John'."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
