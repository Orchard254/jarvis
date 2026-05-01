"""
tools/data/notes.py — Notes management tools

Tools for: create_note, read_notes, delete_note
Stores notes in a simple text file format.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from ..base import BaseTool, ToolResult

log = logging.getLogger("notes_tools")


# Notes storage file
NOTES_FILE = Path(__file__).parent.parent.parent.parent / "data" / "notes.json"
NOTES_FILE.parent.mkdir(exist_ok=True)


def load_notes() -> List[dict]:
    """Load all notes from storage."""
    if not NOTES_FILE.exists():
        return []
    
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_notes(notes: List[dict]) -> bool:
    """Save notes to storage."""
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        log.error(f"Failed to save notes: {e}")
        return False


class CreateNoteTool(BaseTool):
    """Create a new note."""
    
    name = "create_note"
    description = "Create a new note with the given content. Notes are saved and can be retrieved later."
    parameters = {
        "content": {
            "type": "string",
            "description": "Content of the note",
        },
        "title": {
            "type": "string",
            "description": "Optional title for the note",
        },
    }
    required_parameters = ["content"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        content = kwargs.get("content")
        if not content:
            return False, "content parameter is required"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        content = kwargs["content"]
        title = kwargs.get("title", "")
        
        try:
            notes = load_notes()
            
            note = {
                "id": len(notes) + 1,
                "title": title or f"Note {len(notes) + 1}",
                "content": content,
                "created_at": datetime.now().isoformat(),
            }
            
            notes.append(note)
            
            if save_notes(notes):
                return ToolResult.ok(f"Note created: '{note['title']}'")
            else:
                return ToolResult.fail(error="Failed to save note")
                
        except Exception as e:
            log.error(f"Failed to create note: {e}")
            return ToolResult.fail(error=f"Failed to create note: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class ReadNotesTool(BaseTool):
    """Read stored notes."""
    
    name = "read_notes"
    description = "Read your stored notes. Optionally filter by search term or limit number of results."
    parameters = {
        "search": {
            "type": "string",
            "description": "Optional search term to filter notes",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of notes to return (default: 10)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        limit = kwargs.get("limit", 10)
        if not isinstance(limit, int) or limit < 1 or limit > 50:
            return False, "limit must be between 1 and 50"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        search = kwargs.get("search", "")
        limit = min(kwargs.get("limit", 10), 50)
        
        try:
            notes = load_notes()
            
            # Filter by search term if provided
            if search:
                search_lower = search.lower()
                notes = [
                    n for n in notes 
                    if search_lower in n.get("title", "").lower() or 
                       search_lower in n.get("content", "").lower()
                ]
            
            # Sort by creation date (newest first) and limit
            notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            notes = notes[:limit]
            
            if not notes:
                return ToolResult.ok("No notes found")
            
            output_lines = [f"Found {len(notes)} note(s):"]
            for note in notes:
                title = note.get("title", "Untitled")
                content = note.get("content", "")[:100]
                created = note.get("created_at", "")[:10]
                output_lines.append(f"\n[{created}] {title}")
                output_lines.append(f"  {content}{'...' if len(note.get('content', '')) > 100 else ''}")
            
            return ToolResult.ok("\n".join(output_lines))
            
        except Exception as e:
            log.error(f"Failed to read notes: {e}")
            return ToolResult.fail(error=f"Failed to read notes: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "low"


class DeleteNoteTool(BaseTool):
    """Delete a note by ID or title."""
    
    name = "delete_note"
    description = "Delete a note by its ID number or title match."
    parameters = {
        "id": {
            "type": "integer",
            "description": "Note ID to delete",
        },
        "title": {
            "type": "string",
            "description": "Title to match for deletion (alternative to id)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        note_id = kwargs.get("id")
        title = kwargs.get("title")
        
        if note_id is None and not title:
            return False, "Either id or title is required"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        note_id = kwargs.get("id")
        title = kwargs.get("title", "")
        
        try:
            notes = load_notes()
            original_count = len(notes)
            
            if note_id is not None:
                # Delete by ID
                notes = [n for n in notes if n.get("id") != note_id]
            else:
                # Delete by title match
                title_lower = title.lower()
                notes = [n for n in notes if title_lower not in n.get("title", "").lower()]
            
            deleted_count = original_count - len(notes)
            
            if deleted_count > 0:
                if save_notes(notes):
                    return ToolResult.ok(f"Deleted {deleted_count} note(s)")
                else:
                    return ToolResult.fail(error="Failed to save changes")
            else:
                return ToolResult.fail(error="No matching notes found")
                
        except Exception as e:
            log.error(f"Failed to delete note: {e}")
            return ToolResult.fail(error=f"Failed to delete note: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 0.3
    
    def risk_level(self) -> str:
        return "medium"  # Data deletion


# Export all tool classes
NOTES_TOOLS = [
    CreateNoteTool,
    ReadNotesTool,
    DeleteNoteTool,
]
