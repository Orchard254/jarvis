"""
tools/data/todo.py — Todo list management tools

Tools for: add_todo, list_todos, complete_todo, delete_todo
Stores todos in a simple JSON file format.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("todo_tools")


# Todo storage file
TODO_FILE = Path(__file__).parent.parent.parent.parent / "data" / "todos.json"
TODO_FILE.parent.mkdir(exist_ok=True)


def load_todos() -> List[dict]:
    """Load all todos from storage."""
    if not TODO_FILE.exists():
        return []
    
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_todos(todos: List[dict]) -> bool:
    """Save todos to storage."""
    try:
        with open(TODO_FILE, "w", encoding="utf-8") as f:
            json.dump(todos, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        log.error(f"Failed to save todos: {e}")
        return False


class AddTodoTool(BaseTool):
    """Add a new todo item."""
    
    name = "add_todo"
    description = "Add a new todo item to your task list."
    parameters = {
        "task": {
            "type": "string",
            "description": "Description of the task to add",
        },
        "priority": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Priority level (default: medium)",
        },
    }
    required_parameters = ["task"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        task = kwargs.get("task")
        if not task:
            return False, "task parameter is required"
        
        priority = kwargs.get("priority", "medium")
        if priority not in ["low", "medium", "high"]:
            return False, "priority must be 'low', 'medium', or 'high'"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        task = kwargs["task"]
        priority = kwargs.get("priority", "medium")
        
        try:
            todos = load_todos()
            
            todo = {
                "id": len(todos) + 1,
                "task": task,
                "priority": priority,
                "completed": False,
                "created_at": datetime.now().isoformat(),
                "completed_at": None,
            }
            
            todos.append(todo)
            
            if save_todos(todos):
                return ToolResult.ok(f"Added todo: '{task}' (Priority: {priority})")
            else:
                return ToolResult.fail(error="Failed to save todo")
                
        except Exception as e:
            log.error(f"Failed to add todo: {e}")
            return ToolResult.fail(error=f"Failed to add todo: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class ListTodosTool(BaseTool):
    """List todo items."""
    
    name = "list_todos"
    description = "List your todo items. Optionally filter by status (pending/completed) or priority."
    parameters = {
        "status": {
            "type": "string",
            "enum": ["all", "pending", "completed"],
            "description": "Filter by status (default: pending)",
        },
        "priority": {
            "type": "string",
            "enum": ["all", "low", "medium", "high"],
            "description": "Filter by priority (default: all)",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of todos to return (default: 20)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        status = kwargs.get("status", "pending")
        if status not in ["all", "pending", "completed"]:
            return False, "status must be 'all', 'pending', or 'completed'"
        
        priority = kwargs.get("priority", "all")
        if priority not in ["all", "low", "medium", "high"]:
            return False, "priority must be 'all', 'low', 'medium', or 'high'"
        
        limit = kwargs.get("limit", 20)
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            return False, "limit must be between 1 and 100"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        status = kwargs.get("status", "pending")
        priority = kwargs.get("priority", "all")
        limit = min(kwargs.get("limit", 20), 100)
        
        try:
            todos = load_todos()
            
            # Filter by status
            if status == "pending":
                todos = [t for t in todos if not t.get("completed")]
            elif status == "completed":
                todos = [t for t in todos if t.get("completed")]
            
            # Filter by priority
            if priority != "all":
                todos = [t for t in todos if t.get("priority") == priority]
            
            # Sort by priority (high first) then by creation date
            priority_order = {"high": 0, "medium": 1, "low": 2}
            todos.sort(key=lambda x: (priority_order.get(x.get("priority"), 1), x.get("created_at", "")))
            todos = todos[:limit]
            
            if not todos:
                return ToolResult.ok("No todos found")
            
            output_lines = [f"Your todos ({len(todos)} shown):"]
            for todo in todos:
                status_icon = "✓" if todo.get("completed") else "○"
                priority_icon = {"high": "!", "medium": "-", "low": "."}.get(todo.get("priority"), "-")
                task = todo.get("task", "Untitled")
                output_lines.append(f"  [{status_icon}] {priority_icon} [{todo['id']}] {task}")
            
            return ToolResult.ok("\n".join(output_lines))
            
        except Exception as e:
            log.error(f"Failed to list todos: {e}")
            return ToolResult.fail(error=f"Failed to list todos: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class CompleteTodoTool(BaseTool):
    """Mark a todo as completed."""
    
    name = "complete_todo"
    description = "Mark a todo item as completed by its ID."
    parameters = {
        "id": {
            "type": "integer",
            "description": "ID of the todo to complete",
        },
    }
    required_parameters = ["id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        todo_id = kwargs.get("id")
        if todo_id is None:
            return False, "id parameter is required"
        if not isinstance(todo_id, int) or todo_id < 1:
            return False, "id must be a positive integer"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        todo_id = kwargs["id"]
        
        try:
            todos = load_todos()
            
            found = False
            for todo in todos:
                if todo.get("id") == todo_id:
                    todo["completed"] = True
                    todo["completed_at"] = datetime.now().isoformat()
                    found = True
                    break
            
            if found:
                if save_todos(todos):
                    return ToolResult.ok(f"Completed todo #{todo_id}")
                else:
                    return ToolResult.fail(error="Failed to save changes")
            else:
                return ToolResult.fail(error=f"Todo #{todo_id} not found")
                
        except Exception as e:
            log.error(f"Failed to complete todo: {e}")
            return ToolResult.fail(error=f"Failed to complete todo: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class DeleteTodoTool(BaseTool):
    """Delete a todo item."""
    
    name = "delete_todo"
    description = "Delete a todo item by its ID."
    parameters = {
        "id": {
            "type": "integer",
            "description": "ID of the todo to delete",
        },
    }
    required_parameters = ["id"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        todo_id = kwargs.get("id")
        if todo_id is None:
            return False, "id parameter is required"
        if not isinstance(todo_id, int) or todo_id < 1:
            return False, "id must be a positive integer"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        todo_id = kwargs["id"]
        
        try:
            todos = load_todos()
            original_count = len(todos)
            
            todos = [t for t in todos if t.get("id") != todo_id]
            
            if len(todos) < original_count:
                if save_todos(todos):
                    return ToolResult.ok(f"Deleted todo #{todo_id}")
                else:
                    return ToolResult.fail(error="Failed to save changes")
            else:
                return ToolResult.fail(error=f"Todo #{todo_id} not found")
                
        except Exception as e:
            log.error(f"Failed to delete todo: {e}")
            return ToolResult.fail(error=f"Failed to delete todo: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"  # Data deletion


# Export all tool classes
TODO_TOOLS = [
    AddTodoTool,
    ListTodosTool,
    CompleteTodoTool,
    DeleteTodoTool,
]
