"""
Episodic Memory - Long-term session history storage.
Stores complete conversation sessions for later retrieval.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class EpisodicMemory:
    """
    Stores complete conversation sessions as episodic memories.
    Each session is saved as a separate file for easy retrieval.
    """
    
    def __init__(self, storage_dir: str = None, data_dir: str = None):
        """
        Initialize episodic memory storage.
        
        Args:
            storage_dir: Directory to store session files. Defaults to jarvis/memory/episodes
            data_dir: Alternative way to specify storage directory (for compatibility)
        """
        if storage_dir is None:
            if data_dir is not None:
                storage_dir = Path(data_dir) / 'episodes'
            else:
                base_dir = Path(__file__).parent.parent
                storage_dir = base_dir / 'memory' / 'episodes'
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Index of all sessions
        self.index_file = self.storage_dir / 'index.json'
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """Load or create the session index."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                log.warning(f"[EPISODIC] Failed to load index, using defaults: {e}")
        
        return {
            'sessions': [],
            'total_sessions': 0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
    
    def _save_index(self) -> None:
        """Save the session index."""
        self.index['updated_at'] = datetime.now().isoformat()
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)
    
    def save_session(self, session_id: str, messages: List[Dict[str, Any]],
                     metadata: Dict[str, Any] = None) -> str:
        """
        Save a complete session to episodic memory.
        
        Args:
            session_id: Unique session identifier
            messages: List of conversation messages
            metadata: Optional session metadata
            
        Returns:
            Path to the saved session file
        """
        session_data = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'messages': messages,
            'metadata': metadata or {},
            'message_count': len(messages)
        }
        
        # Calculate summary from first and last messages
        if messages:
            session_data['first_message'] = messages[0].get('content', '')[:200]
            session_data['last_message'] = messages[-1].get('content', '')[:200]
        
        # Save session file
        filename = f"session_{session_id}.json"
        filepath = self.storage_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)
        
        # Update index
        session_entry = {
            'session_id': session_id,
            'filename': filename,
            'created_at': session_data['created_at'],
            'message_count': len(messages),
            'first_message_preview': session_data.get('first_message', '')
        }
        
        # Check if session already exists in index
        existing = next(
            (i for i, s in enumerate(self.index['sessions']) 
             if s['session_id'] == session_id),
            None
        )
        
        if existing is not None:
            self.index['sessions'][existing] = session_entry
        else:
            self.index['sessions'].append(session_entry)
            self.index['total_sessions'] += 1
        
        self._save_index()
        
        return str(filepath)
    
    def start_session(self, session_id: str = None) -> str:
        """Start a new session and return its ID."""
        if session_id is None:
            session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        return session_id
    
    def store_session(self, session_id: str, messages: List[Dict[str, Any]],
                      metadata: Dict[str, Any] = None) -> str:
        """
        Store a complete session (alias for save_session with better naming).
        
        Args:
            session_id: Unique session identifier
            messages: List of conversation messages
            metadata: Optional session metadata
            
        Returns:
            Session ID
        """
        self.save_session(session_id, messages, metadata or {})
        return session_id
    
    def end_session(self, session_id: str, messages: List[Dict[str, Any]] = None,
                    summary: str = None) -> str:
        """
        End a session by saving it.
        
        Args:
            session_id: Session identifier
            messages: Optional messages to save
            summary: Optional summary
            
        Returns:
            Session ID
        """
        if messages:
            metadata = {'summary': summary} if summary else {}
            self.store_session(session_id, messages, metadata)
        return session_id
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a session from episodic memory.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session data dictionary or None if not found
        """
        filename = f"session_{session_id}.json"
        filepath = self.storage_dir / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[EPISODIC] Failed to load session {session_id}: {e}")
            return None
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from episodic memory.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if deleted, False if not found
        """
        filename = f"session_{session_id}.json"
        filepath = self.storage_dir / filename
        
        if not filepath.exists():
            return False
        
        try:
            filepath.unlink()
            
            # Remove from index
            self.index['sessions'] = [
                s for s in self.index['sessions']
                if s['session_id'] != session_id
            ]
            self.index['total_sessions'] = len(self.index['sessions'])
            self._save_index()
            
            return True
        except Exception as e:
            log.warning(f"[EPISODIC] Failed to delete session {session_id}: {e}")
            return False
    
    def list_sessions(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all sessions with metadata.
        
        Args:
            limit: Maximum sessions to return
            offset: Number of sessions to skip
            
        Returns:
            List of session metadata
        """
        sessions = sorted(
            self.index['sessions'],
            key=lambda s: s.get('created_at', ''),
            reverse=True
        )
        
        return sessions[offset:offset + limit]
    
    def search_sessions(self, query: str, case_insensitive: bool = True) -> List[Dict[str, Any]]:
        """
        Search sessions by content.
        
        Args:
            query: Search query string
            case_insensitive: Whether to ignore case
            
        Returns:
            List of matching sessions with relevance scores
        """
        results = []
        
        if case_insensitive:
            query = query.lower()
        
        for session_meta in self.index['sessions']:
            session_id = session_meta['session_id']
            session = self.load_session(session_id)
            
            if not session:
                continue
            
            # Search in messages
            match_count = 0
            total_messages = len(session.get('messages', []))
            
            for msg in session.get('messages', []):
                content = msg.get('content', '')
                search_content = content.lower() if case_insensitive else content
                
                if query in search_content:
                    match_count += 1
            
            if match_count > 0:
                results.append({
                    'session': session_meta,
                    'match_count': match_count,
                    'relevance': match_count / max(total_messages, 1),
                    'full_session': session
                })
        
        # Sort by relevance
        results.sort(key=lambda r: r['relevance'], reverse=True)
        
        return results
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Statistics dictionary or None if not found
        """
        session = self.load_session(session_id)
        
        if not session:
            return None
        
        messages = session.get('messages', [])
        
        # Count by role
        role_counts = {}
        tool_usage = {}
        
        for msg in messages:
            role = msg.get('role', 'unknown')
            role_counts[role] = role_counts.get(role, 0) + 1
            
            if role == 'tool':
                tool_name = msg.get('metadata', {}).get('tool_name', 'unknown')
                tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
        
        return {
            'session_id': session_id,
            'total_messages': len(messages),
            'role_distribution': role_counts,
            'tool_usage': tool_usage,
            'duration_estimate': self._estimate_duration(messages),
            'created_at': session.get('created_at'),
            'metadata': session.get('metadata', {})
        }
    
    def _estimate_duration(self, messages: List[Dict[str, Any]]) -> str:
        """Estimate session duration based on message timestamps."""
        if len(messages) < 2:
            return "Unknown"
        
        try:
            first_time = datetime.fromisoformat(messages[0].get('timestamp', ''))
            last_time = datetime.fromisoformat(messages[-1].get('timestamp', ''))
            delta = last_time - first_time
            
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            
            if hours > 0:
                return f"{hours}h {minutes}m"
            elif minutes > 0:
                return f"{minutes}m"
            else:
                return f"{delta.seconds}s"
        except Exception as e:
            log.debug(f"[EPISODIC] Duration calculation failed: {e}")
            return "Unknown"
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about memory usage."""
        return {
            'session_count': self.index['total_sessions'],
            'total_messages': sum(
                s.get('message_count', 0) for s in self.index['sessions']
            ),
            'storage_location': str(self.storage_dir)
        }
    
    def export_all_sessions(self, output_path: str = None) -> str:
        """
        Export all sessions to a single JSON file.
        
        Args:
            output_path: Output file path
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"episodic_export_{timestamp}.json"
        
        all_sessions = []
        for session_meta in self.index['sessions']:
            session = self.load_session(session_meta['session_id'])
            if session:
                all_sessions.append(session)
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'total_sessions': len(all_sessions),
            'sessions': all_sessions
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return output_path


# Singleton instance
_episodic_memory_instance = None

def get_episodic_memory() -> EpisodicMemory:
    """Get the singleton EpisodicMemory instance."""
    global _episodic_memory_instance
    if _episodic_memory_instance is None:
        _episodic_memory_instance = EpisodicMemory()
    return _episodic_memory_instance
