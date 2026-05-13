"""
Run Skill tool — executes a stored skill by ID through the safety funnel.
"""

import logging

logger = logging.getLogger(__name__)


def run_skill(skill_id: str) -> dict:
    """
    Execute a stored skill by its skill_id. The skill's code runs through the
    safety executor and is recorded for success/failure tracking.

    Parameters
    ----------
    skill_id : str
        The skill_id from the skills catalog (e.g. "skill_a1b2c3d4").

    Returns
    -------
    dict with {"success": bool, "stdout": str, "skill_id": str, ...}
    """
    try:
        from skills.skill_runner import run_skill as _run

        result = _run(skill_id, intent="")
        logger.info(f"run_skill('{skill_id}') -> success={result.get('success')}")
        return result
    except Exception as e:
        logger.error(f"run_skill error: {e}")
        return {"success": False, "error": str(e), "skill_id": skill_id}
