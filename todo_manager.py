import json
import os
from datetime import datetime
from pathlib import Path

from logger import get_logger

log = get_logger("todo")

TODO_FILE = Path(__file__).parent / "todo_list.json"


def load_todo() -> list:
    try:
        if TODO_FILE.exists():
            with open(TODO_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return []


def save_todo(todo_list: list) -> None:
    try:
        with open(TODO_FILE, "w") as f:
            json.dump(todo_list, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save todo: {e}")


def create_todo(task: str, subtasks: list = None) -> str:
    todo_list = load_todo()
    todo_id = f"todo_{len(todo_list) + 1}_{datetime.now().strftime('%H%M%S')}"

    formatted_subtasks = []
    if subtasks:
        for sub in subtasks:
            if isinstance(sub, str):
                formatted_subtasks.append({"text": sub, "done": False})
            elif isinstance(sub, dict):
                formatted_subtasks.append(
                    {"text": sub.get("text", ""), "done": sub.get("done", False)}
                )

    todo_item = {
        "id": todo_id,
        "task": task,
        "subtasks": formatted_subtasks,
        "status": "in_progress",
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }
    todo_list.append(todo_item)
    save_todo(todo_list)
    log.info(f"[TODO] Created: {task}")
    return todo_id


def add_subtask(todo_id: str, subtask: str) -> None:
    todo_list = load_todo()
    for item in todo_list:
        if item["id"] == todo_id:
            item["subtasks"].append({"text": subtask, "done": False})
            save_todo(todo_list)
            log.info(f"[TODO] Added subtask to {todo_id}: {subtask}")
            return


def mark_subtask_done(todo_id: str, subtask_text: str) -> None:
    todo_list = load_todo()
    for item in todo_list:
        if item["id"] == todo_id:
            for sub in item.get("subtasks", []):
                if isinstance(sub, dict) and "text" in sub:
                    if sub["text"].lower() in subtask_text.lower():
                        sub["done"] = True
                        log.info(f"[TODO] Marked done: {sub['text']}")
            save_todo(todo_list)
            return


def complete_todo(todo_id: str) -> str:
    todo_list = load_todo()
    for item in todo_list:
        if item["id"] == todo_id:
            item["status"] = "completed"
            item["completed_at"] = datetime.now().isoformat()
            save_todo(todo_list)
            log.info(f"[TODO] Completed: {item['task']}")
            return item["task"]
    return ""


def get_pending_todos() -> list:
    todo_list = load_todo()
    pending = [t for t in todo_list if t["status"] == "in_progress"]
    return pending


def clear_completed() -> int:
    todo_list = load_todo()
    before = len(todo_list)
    todo_list = [t for t in todo_list if t["status"] != "completed"]
    save_todo(todo_list)
    return before - len(todo_list)


def get_todo_summary() -> str:
    pending = get_pending_todos()
    if not pending:
        return "No pending tasks."

    lines = ["Current tasks:"]
    for i, item in enumerate(pending, 1):
        lines.append(f"{i}. {item['task']}")
        for sub in item.get("subtasks", []):
            done = "[x]" if sub.get("done") else "[ ]"
            lines.append(f"   {done} {sub['text']}")
    return "\n".join(lines)


def get_overdue_todos(hours_threshold: int = 24) -> list:
    """Get todos that have been pending for more than threshold hours."""
    pending = get_pending_todos()
    overdue = []
    now = datetime.now()

    for item in pending:
        created = datetime.fromisoformat(item["created_at"])
        hours_pending = (now - created).total_seconds() / 3600
        if hours_pending > hours_threshold:
            overdue.append({**item, "hours_pending": round(hours_pending, 1)})

    return overdue


def get_progress_stats() -> dict:
    """Get todo progress statistics."""
    todo_list = load_todo()
    total = len(todo_list)
    completed = sum(1 for t in todo_list if t["status"] == "completed")
    in_progress = total - completed

    total_subtasks = 0
    completed_subtasks = 0
    for item in todo_list:
        for sub in item.get("subtasks", []):
            total_subtasks += 1
            if sub.get("done"):
                completed_subtasks += 1

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "in_progress_tasks": in_progress,
        "total_subtasks": total_subtasks,
        "completed_subtasks": completed_subtasks,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
    }


def cleanup_old_completed(days_old: int = 7) -> int:
    """Remove completed todos older than specified days."""
    from datetime import timedelta

    todo_list = load_todo()
    cutoff = datetime.now() - timedelta(days=days_old)

    before = len(todo_list)
    filtered = []

    for item in todo_list:
        if item["status"] != "completed":
            filtered.append(item)
        else:
            completed_at = item.get("completed_at")
            if completed_at:
                comp_date = datetime.fromisoformat(completed_at)
                if comp_date > cutoff:
                    filtered.append(item)

    save_todo(filtered)
    removed = before - len(filtered)
    if removed > 0:
        log.info(f"[TODO] Cleaned up {removed} old completed tasks")
    return removed
