"""
Skill Store tools — let the LLM save and promote reusable skills directly.

save_candidate  — store a skill after a successful execute_code run
promote_skill   — promote a candidate skill to active (enables semantic search)
"""

import logging

logger = logging.getLogger(__name__)


def save_candidate(intent_label: str, code: str, language: str = "python") -> dict:
    """
    Save a reusable skill after a successful execute_code run.

    Parameters
    ----------
    intent_label : str
        Natural-language description of what this skill does
        (e.g. "open calculator", "close notepad").
    code : str
        The Python/PowerShell code to execute for this skill.
    language : str
        "python" or "powershell" (default "python").

    Returns
    -------
    dict with {"success": bool, "skill_id": str, ...}
    """
    try:
        from skills.skill_store import save_candidate as _save

        skill_id = _save(intent_label, code, language)
        if skill_id:
            logger.info(f"skill_store.save_candidate('{intent_label}') → {skill_id}")
            return {
                "success": True,
                "skill_id": skill_id,
                "intent": intent_label,
                "message": f"Saved candidate skill {skill_id} for '{intent_label}'.",
            }
        else:
            return {
                "success": False,
                "error": f"Failed to save skill for '{intent_label}'.",
            }
    except Exception as e:
        logger.error(f"save_candidate error: {e}")
        return {"success": False, "error": str(e)}


def promote_skill(skill_id: str) -> dict:
    """
    Promote a candidate skill to active status.

    Once promoted, the skill becomes available for semantic search and will be
    injected as code context when the orchestrator detects a matching intent.

    Parameters
    ----------
    skill_id : str
        The skill ID returned by save_candidate (e.g. "skill_a1b2c3d4").

    Returns
    -------
    dict with {"success": bool, "skill_id": str, ...}
    """
    try:
        from skills.skill_store import promote_skill as _promote

        _promote(skill_id)
        logger.info(f"skill_store.promote_skill('{skill_id}')")
        return {
            "success": True,
            "skill_id": skill_id,
            "message": f"Skill {skill_id} promoted to active.",
        }
    except Exception as e:
        logger.error(f"promote_skill error: {e}")
        return {"success": False, "error": str(e)}
