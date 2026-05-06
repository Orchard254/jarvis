"""
6. Productivity Tools (4 tools)
Everyday assistant layer.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class CalendarManager:
    """
    calendar_manager: Manage calendar events
    
    Creates, reads, and manages calendar events.
    """
    
    def __init__(self, calendar_file: str = "~/.jarvis/calendar.json"):
        self.calendar_file = calendar_file
    
    def execute(self, action: str, event_data: Optional[dict] = None,
                date_filter: Optional[str] = None, **kwargs) -> dict:
        """
        Manage calendar events.
        
        Args:
            action: One of 'create', 'list', 'delete', 'update'
            event_data: Event details for create/update
            date_filter: Filter by date (YYYY-MM-DD)
            
        Returns:
            Operation result
        """
        try:
            events = self._load_events()
            
            if action == "create":
                if not event_data:
                    return {"success": False, "error": "event_data required for create"}
                
                event_id = f"evt_{len(events) + 1}_{datetime.now().timestamp()}"
                new_event = {
                    "id": event_id,
                    "title": event_data.get("title", "Untitled"),
                    "start": event_data.get("start"),
                    "end": event_data.get("end"),
                    "description": event_data.get("description", ""),
                    "location": event_data.get("location", ""),
                    "created_at": datetime.now().isoformat()
                }
                events.append(new_event)
                self._save_events(events)
                
                return {"success": True, "output": {"event_id": event_id, "event": new_event}}
            
            elif action == "list":
                filtered = events
                if date_filter:
                    filtered = [e for e in events if e.get("start", "").startswith(date_filter)]
                return {"success": True, "output": {"events": filtered, "count": len(filtered)}}
            
            elif action == "delete":
                event_id = event_data.get("id") if event_data else None
                if not event_id:
                    return {"success": False, "error": "event id required"}
                events = [e for e in events if e["id"] != event_id]
                self._save_events(events)
                return {"success": True, "output": {"deleted_id": event_id}}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _load_events(self) -> list:
        """Load events from file."""
        import os
        path = os.path.expanduser(self.calendar_file)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return []
    
    def _save_events(self, events: list):
        """Save events to file."""
        import os
        path = os.path.expanduser(self.calendar_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(events, f, indent=2)


class TaskScheduler:
    """
    task_scheduler: Schedule and manage tasks
    
    Manages todo lists and scheduled tasks.
    """
    
    def __init__(self, tasks_file: str = "~/.jarvis/tasks.json"):
        self.tasks_file = tasks_file
    
    def execute(self, action: str, task_data: Optional[dict] = None,
                status_filter: Optional[str] = None, **kwargs) -> dict:
        """
        Manage tasks.
        
        Args:
            action: One of 'create', 'list', 'complete', 'delete', 'update'
            task_data: Task details
            status_filter: Filter by status ('pending', 'completed')
            
        Returns:
            Operation result
        """
        try:
            tasks = self._load_tasks()
            
            if action == "create":
                if not task_data:
                    return {"success": False, "error": "task_data required"}
                
                task_id = f"task_{len(tasks) + 1}_{datetime.now().timestamp()}"
                new_task = {
                    "id": task_id,
                    "title": task_data.get("title", "Untitled Task"),
                    "description": task_data.get("description", ""),
                    "priority": task_data.get("priority", "medium"),
                    "due_date": task_data.get("due_date"),
                    "status": "pending",
                    "created_at": datetime.now().isoformat()
                }
                tasks.append(new_task)
                self._save_tasks(tasks)
                return {"success": True, "output": {"task_id": task_id, "task": new_task}}
            
            elif action == "list":
                filtered = tasks
                if status_filter:
                    filtered = [t for t in tasks if t.get("status") == status_filter]
                # Sort by priority
                priority_order = {"high": 0, "medium": 1, "low": 2}
                filtered.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 1))
                return {"success": True, "output": {"tasks": filtered, "count": len(filtered)}}
            
            elif action == "complete":
                task_id = task_data.get("id") if task_data else None
                if not task_id:
                    return {"success": False, "error": "task id required"}
                for task in tasks:
                    if task["id"] == task_id:
                        task["status"] = "completed"
                        task["completed_at"] = datetime.now().isoformat()
                        break
                self._save_tasks(tasks)
                return {"success": True, "output": {"completed_id": task_id}}
            
            elif action == "delete":
                task_id = task_data.get("id") if task_data else None
                if not task_id:
                    return {"success": False, "error": "task id required"}
                tasks = [t for t in tasks if t["id"] != task_id]
                self._save_tasks(tasks)
                return {"success": True, "output": {"deleted_id": task_id}}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _load_tasks(self) -> list:
        """Load tasks from file."""
        import os
        path = os.path.expanduser(self.tasks_file)
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return []
    
    def _save_tasks(self, tasks: list):
        """Save tasks to file."""
        import os
        path = os.path.expanduser(self.tasks_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(tasks, f, indent=2)


class NotesManager:
    """
    notes_manager: Create and manage notes
    
    Handles note-taking and retrieval.
    """
    
    def __init__(self, notes_dir: str = "~/.jarvis/notes"):
        self.notes_dir = notes_dir
    
    def execute(self, action: str, note_data: Optional[dict] = None,
                search_query: Optional[str] = None, **kwargs) -> dict:
        """
        Manage notes.
        
        Args:
            action: One of 'create', 'read', 'list', 'delete', 'search'
            note_data: Note details (title, content)
            search_query: Search term for notes
            
        Returns:
            Operation result
        """
        try:
            import os
            notes_path = os.path.expanduser(self.notes_dir)
            os.makedirs(notes_path, exist_ok=True)
            
            if action == "create":
                if not note_data:
                    return {"success": False, "error": "note_data required"}
                
                title = note_data.get("title", "untitled")
                safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
                filename = f"{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                filepath = os.path.join(notes_path, filename)
                
                content = f"# {title}\n\n{note_data.get('content', '')}\n"
                content += f"\n---\nCreated: {datetime.now().isoformat()}\n"
                
                with open(filepath, 'w') as f:
                    f.write(content)
                
                return {"success": True, "output": {"filename": filename, "path": filepath}}
            
            elif action == "read":
                filename = note_data.get("filename") if note_data else None
                if not filename:
                    return {"success": False, "error": "filename required"}
                filepath = os.path.join(notes_path, filename)
                if not os.path.exists(filepath):
                    return {"success": False, "error": "Note not found"}
                with open(filepath, 'r') as f:
                    content = f.read()
                return {"success": True, "output": {"content": content}}
            
            elif action == "list":
                notes = []
                for f in os.listdir(notes_path):
                    if f.endswith('.md'):
                        filepath = os.path.join(notes_path, f)
                        notes.append({
                            "filename": f,
                            "modified": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
                        })
                notes.sort(key=lambda x: x["modified"], reverse=True)
                return {"success": True, "output": {"notes": notes, "count": len(notes)}}
            
            elif action == "search":
                if not search_query:
                    return {"success": False, "error": "search_query required"}
                
                results = []
                for f in os.listdir(notes_path):
                    if f.endswith('.md'):
                        filepath = os.path.join(notes_path, f)
                        with open(filepath, 'r') as file:
                            content = file.read()
                            if search_query.lower() in content.lower():
                                results.append({"filename": f, "path": filepath})
                
                return {"success": True, "output": {"results": results, "count": len(results)}}
            
            elif action == "delete":
                filename = note_data.get("filename") if note_data else None
                if not filename:
                    return {"success": False, "error": "filename required"}
                filepath = os.path.join(notes_path, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    return {"success": True, "output": {"deleted": filename}}
                return {"success": False, "error": "Note not found"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class EmailHandler:
    """
    email_handler: Send and manage emails
    
    Handles email composition and sending.
    """
    
    def __init__(self, smtp_server: Optional[str] = None,
                 smtp_port: int = 587):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
    
    def execute(self, action: str, email_data: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Handle emails.
        
        Args:
            action: One of 'send', 'draft', 'list'
            email_data: Email details (to, subject, body, attachments)
            
        Returns:
            Operation result
        """
        try:
            if action == "send":
                if not email_data:
                    return {"success": False, "error": "email_data required"}
                
                # In production, would actually send via SMTP
                # For now, simulate and log
                logger.info(f"Would send email to: {email_data.get('to')}")
                
                return {
                    "success": True,
                    "output": {
                        "status": "simulated",
                        "to": email_data.get("to"),
                        "subject": email_data.get("subject"),
                        "sent_at": datetime.now().isoformat(),
                        "note": "Configure SMTP settings to actually send emails"
                    }
                }
            
            elif action == "draft":
                if not email_data:
                    return {"success": False, "error": "email_data required"}
                
                draft_id = f"draft_{datetime.now().timestamp()}"
                return {
                    "success": True,
                    "output": {
                        "draft_id": draft_id,
                        "email": email_data,
                        "saved_at": datetime.now().isoformat()
                    }
                }
            
            elif action == "list":
                # Return empty list (would connect to IMAP in production)
                return {"success": True, "output": {"emails": [], "count": 0}}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


# Factory functions
def get_calendar_manager(calendar_file: str = "~/.jarvis/calendar.json") -> CalendarManager:
    return CalendarManager(calendar_file=calendar_file)


def get_task_scheduler(tasks_file: str = "~/.jarvis/tasks.json") -> TaskScheduler:
    return TaskScheduler(tasks_file=tasks_file)


def get_notes_manager(notes_dir: str = "~/.jarvis/notes") -> NotesManager:
    return NotesManager(notes_dir=notes_dir)


def get_email_handler(smtp_server: Optional[str] = None, 
                      smtp_port: int = 587) -> EmailHandler:
    return EmailHandler(smtp_server=smtp_server, smtp_port=smtp_port)
