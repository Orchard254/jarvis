"""
Executor agent system prompt loader. Loads from prompts/executor.yaml.
Embeds raw tools/schemas.json (input/output contracts, not OpenAI format).
"""
import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_prompt_cache: dict[str, str] = {}
_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_SCHEMAS_PATH = Path(__file__).parent.parent / "tools" / "schemas.json"


def build_executor_prompt() -> str:
    """Build executor system prompt with embedded input/output tool schemas."""
    if "executor" not in _prompt_cache:
        path = _PROMPT_DIR / "executor.yaml"
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        sections = data.get("sections", {})
        _prompt_cache["executor"] = "\n\n".join(
            v.strip() for v in sections.values() if v.strip()
        )

    with open(_SCHEMAS_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    schemas_json = json.dumps(raw, indent=2)
    return _prompt_cache["executor"].format(schemas=schemas_json)
