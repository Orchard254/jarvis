"""
Task Executor Skill - Executes complex multi-step tasks

Handles task planning, execution tracking, and recovery.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import threading
import time

from ..base import BaseSkill


class TaskExecutorSkill(BaseSkill):
    """
    Skill for executing complex multi-step tasks.
    
    Features:
    - Task queue management
    - Progress tracking
    - Error recovery
    - Parallel execution support
    - Task persistence
    """
    
    def __init__(self):
        super().__init__(
            name="task_executor",
            description="Execute complex multi-step tasks with tracking",
            version="1.0.0"
        )
        
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        self.failed_tasks: List[Dict[str, Any]] = []
        self.task_queue: List[Dict[str, Any]] = []
        self.executor_thread: Optional[threading.Thread] = None
        self.stop_executor = threading.Event()
        self.current_task_id: Optional[str] = None
    
    def get_system_prompt(self) -> str:
        active_count = len(self.active_tasks)
        queued_count = len(self.task_queue)
        completed_count = len(self.completed_tasks)
        
        return """You are JARVIS in Task Executor mode. Your role is to manage and execute complex tasks.

TASK EXECUTION STATUS:
- Active Tasks: {active}
- Queued Tasks: {queued}
- Completed Today: {completed}
- Failed Today: {failed}

EXECUTION GUIDELINES:
1. Break complex requests into discrete, executable steps
2. Track progress for each step
3. Handle errors gracefully with retry logic
4. Report progress updates to the user
5. Allow task cancellation at any point
6. Log all task outcomes for learning
7. Prioritize user safety and confirmation for destructive actions

Current active tasks should be monitored and updated regularly.""".format(
            active=active_count,
            queued=queued_count,
            completed=completed_count,
            failed=len(self.failed_tasks)
        )
    
    def execute(self, action: str, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task manager actions."""
        
        actions = {
            "create": self._create_task,
            "start": self._start_task,
            "pause": self._pause_task,
            "resume": self._resume_task,
            "cancel": self._cancel_task,
            "status": self._get_task_status,
            "list": self._list_tasks,
            "queue": self._add_to_queue,
            "clear_queue": self._clear_queue
        }
        
        if action not in actions:
            return {
                "success": False,
                "output": None,
                "error": f"Unknown task executor action: {action}",
                "exit_code": 1,
                "verified": False,
                "verify_msg": "Invalid action"
            }
        
        return actions[action](params, context)
    
    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _create_task(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task."""
        try:
            task_id = self._generate_task_id()
            
            task = {
                "id": task_id,
                "name": params.get("name", "Unnamed Task"),
                "description": params.get("description", ""),
                "steps": params.get("steps", []),
                "current_step": 0,
                "status": "created",
                "created_at": datetime.now().isoformat(),
                "started_at": None,
                "completed_at": None,
                "progress": 0,
                "result": None,
                "error": None,
                "metadata": params.get("metadata", {})
            }
            
            self.active_tasks[task_id] = task
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' created with ID: {task_id}. {len(task['steps'])} steps defined.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} created",
                "task_id": task_id,
                "task": task
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to create task: {e}"
            }
    
    def _start_task(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Start executing a task."""
        try:
            task_id = params.get("task_id")
            
            if not task_id or task_id not in self.active_tasks:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks[task_id]
            
            if task["status"] == "running":
                return {
                    "success": False,
                    "output": None,
                    "error": "Task is already running",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task already running"
                }
            
            task["status"] = "running"
            task["started_at"] = datetime.now().isoformat()
            self.current_task_id = task_id
            
            # Start execution thread if not already running
            if not self.executor_thread or not self.executor_thread.is_alive():
                self.stop_executor.clear()
                self.executor_thread = threading.Thread(target=self._execute_loop, daemon=True)
                self.executor_thread.start()
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' started. Execution in progress...",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} started"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to start task: {e}"
            }
    
    def _pause_task(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Pause a running task."""
        try:
            task_id = params.get("task_id")
            
            if not task_id or task_id not in self.active_tasks:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks[task_id]
            
            if task["status"] != "running":
                return {
                    "success": False,
                    "output": None,
                    "error": "Task is not running",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not running"
                }
            
            task["status"] = "paused"
            
            if self.current_task_id == task_id:
                self.current_task_id = None
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' paused at step {task['current_step'] + 1}/{len(task['steps'])}",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} paused"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to pause task: {e}"
            }
    
    def _resume_task(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Resume a paused task."""
        try:
            task_id = params.get("task_id")
            
            if not task_id or task_id not in self.active_tasks:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks[task_id]
            
            if task["status"] != "paused":
                return {
                    "success": False,
                    "output": None,
                    "error": "Task is not paused",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not paused"
                }
            
            task["status"] = "running"
            self.current_task_id = task_id
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' resumed. Continuing from step {task['current_step'] + 1}...",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} resumed"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to resume task: {e}"
            }
    
    def _cancel_task(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel a task."""
        try:
            task_id = params.get("task_id")
            
            if not task_id or task_id not in self.active_tasks:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks.pop(task_id)
            task["status"] = "cancelled"
            task["completed_at"] = datetime.now().isoformat()
            
            self.failed_tasks.append(task)
            
            if self.current_task_id == task_id:
                self.current_task_id = None
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' cancelled.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} cancelled"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to cancel task: {e}"
            }
    
    def _get_task_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Get status of a specific task."""
        try:
            task_id = params.get("task_id")
            
            if not task_id:
                # Return summary if no specific task requested
                return {
                    "success": True,
                    "output": f"Active: {len(self.active_tasks)}, Queued: {len(self.task_queue)}, Completed: {len(self.completed_tasks)}, Failed: {len(self.failed_tasks)}",
                    "error": None,
                    "exit_code": 0,
                    "verified": True,
                    "verify_msg": "Summary returned",
                    "summary": {
                        "active": len(self.active_tasks),
                        "queued": len(self.task_queue),
                        "completed": len(self.completed_tasks),
                        "failed": len(self.failed_tasks)
                    }
                }
            
            if task_id not in self.active_tasks:
                # Check completed/failed
                for task_list in [self.completed_tasks, self.failed_tasks]:
                    for task in task_list:
                        if task["id"] == task_id:
                            return {
                                "success": True,
                                "output": f"Task '{task['name']}' - Status: {task['status']}, Progress: {task['progress']}%",
                                "error": None,
                                "exit_code": 0,
                                "verified": True,
                                "verify_msg": "Historical task found",
                                "task": task
                            }
                
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks[task_id]
            total_steps = len(task["steps"])
            current = task["current_step"]
            progress = task["progress"]
            
            status_output = (
                f"Task: {task['name']}\n"
                f"Status: {task['status']}\n"
                f"Progress: {progress}%\n"
                f"Step: {current + 1}/{total_steps}\n"
                f"Started: {task['started_at'] or 'Not started'}"
            )
            
            if task["steps"] and current < len(task["steps"]):
                status_output += f"\nCurrent Step: {task['steps'][current].get('description', 'Executing...')}"
            
            return {
                "success": True,
                "output": status_output,
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Status: {task['status']}, {progress}%",
                "task": task
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to get status: {e}"
            }
    
    def _list_tasks(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """List all tasks."""
        try:
            status_filter = params.get("status", "all")
            
            output_parts = ["=== Task List ==="]
            
            if status_filter in ["all", "active"]:
                if self.active_tasks:
                    output_parts.append("\nActive Tasks:")
                    for task_id, task in self.active_tasks.items():
                        output_parts.append(f"  [{task_id}] {task['name']} - {task['status']} ({task['progress']}%)")
                else:
                    output_parts.append("\nNo active tasks.")
            
            if status_filter in ["all", "completed"]:
                if self.completed_tasks:
                    output_parts.append(f"\nCompleted Tasks ({len(self.completed_tasks)}):")
                    for task in self.completed_tasks[-5:]:  # Last 5
                        output_parts.append(f"  [{task['id']}] {task['name']} - {task['completed_at']}")
            
            if status_filter in ["all", "failed"]:
                if self.failed_tasks:
                    output_parts.append(f"\nFailed Tasks ({len(self.failed_tasks)}):")
                    for task in self.failed_tasks[-5:]:  # Last 5
                        output_parts.append(f"  [{task['id']}] {task['name']} - Error: {task.get('error', 'Unknown')}")
            
            return {
                "success": True,
                "output": "\n".join(output_parts),
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Listed tasks with filter: {status_filter}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to list tasks: {e}"
            }
    
    def _add_to_queue(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Add task to execution queue."""
        try:
            task_id = params.get("task_id")
            
            if not task_id or task_id not in self.active_tasks:
                return {
                    "success": False,
                    "output": None,
                    "error": f"Task {task_id} not found",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Task not found"
                }
            
            task = self.active_tasks[task_id]
            
            if task["status"] != "created":
                return {
                    "success": False,
                    "output": None,
                    "error": "Task must be in 'created' status to queue",
                    "exit_code": 1,
                    "verified": True,
                    "verify_msg": "Invalid task status"
                }
            
            task["status"] = "queued"
            self.task_queue.append(task_id)
            
            position = len(self.task_queue)
            
            return {
                "success": True,
                "output": f"Task '{task['name']}' added to queue at position {position}",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"Task {task_id} queued at position {position}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to queue task: {e}"
            }
    
    def _clear_queue(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Clear the task queue."""
        try:
            count = len(self.task_queue)
            
            for task_id in self.task_queue:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id]["status"] = "created"
            
            self.task_queue = []
            
            return {
                "success": True,
                "output": f"Cleared {count} tasks from queue.",
                "error": None,
                "exit_code": 0,
                "verified": True,
                "verify_msg": f"{count} tasks dequeued"
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e),
                "exit_code": 1,
                "verified": False,
                "verify_msg": f"Failed to clear queue: {e}"
            }
    
    def _execute_loop(self):
        """Background task execution loop."""
        while not self.stop_executor.is_set():
            if not self.current_task_id and self.task_queue:
                # Pick next task from queue
                next_task_id = self.task_queue.pop(0)
                if next_task_id in self.active_tasks:
                    self.active_tasks[next_task_id]["status"] = "running"
                    self.active_tasks[next_task_id]["started_at"] = datetime.now().isoformat()
                    self.current_task_id = next_task_id
            
            if self.current_task_id and self.current_task_id in self.active_tasks:
                task = self.active_tasks[self.current_task_id]
                
                if task["status"] == "running" and task["current_step"] < len(task["steps"]):
                    # Execute current step
                    step = task["steps"][task["current_step"]]
                    
                    try:
                        # In full implementation, this would call the actual tool/action
                        # For now, simulate step completion
                        time.sleep(step.get("duration", 1))
                        
                        task["current_step"] += 1
                        task["progress"] = int((task["current_step"] / len(task["steps"])) * 100)
                        
                        if task["current_step"] >= len(task["steps"]):
                            # Task complete
                            task["status"] = "completed"
                            task["completed_at"] = datetime.now().isoformat()
                            task["result"] = "Success"
                            
                            self.completed_tasks.append(task)
                            del self.active_tasks[self.current_task_id]
                            self.current_task_id = None
                            
                    except Exception as e:
                        task["status"] = "failed"
                        task["error"] = str(e)
                        self.failed_tasks.append(task)
                        del self.active_tasks[self.current_task_id]
                        self.current_task_id = None
            
            time.sleep(0.5)  # Poll interval
    
    def on_exit(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Cleanup on skill exit."""
        self.stop_executor.set()
        
        if self.executor_thread and self.executor_thread.is_alive():
            self.executor_thread.join(timeout=2)
        
        return {
            "success": True,
            "output": "Task executor stopped. Active tasks preserved.",
            "error": None,
            "exit_code": 0,
            "verified": True,
            "verify_msg": "Executor stopped"
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get skill state for persistence."""
        return {
            "active_tasks": self.active_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "task_queue": self.task_queue
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore skill state."""
        self.active_tasks = state.get("active_tasks", {})
        self.completed_tasks = state.get("completed_tasks", [])
        self.failed_tasks = state.get("failed_tasks", [])
        self.task_queue = state.get("task_queue", [])
