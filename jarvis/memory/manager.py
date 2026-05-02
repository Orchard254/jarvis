"""
Memory Manager - Coordinates all memory types.
Unified interface for working, episodic, semantic, and procedural memory.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from .working import WorkingMemory, get_working_memory
from .episodic import EpisodicMemory, get_episodic_memory
from .semantic import SemanticMemory, get_semantic_memory


class ProceduralMemory:
    """
    Stores learned procedures and how-to patterns.
    Simple key-value store for procedure templates.
    """
    
    def __init__(self, storage_file: str = None):
        if storage_file is None:
            base_dir = Path(__file__).parent.parent
            storage_file = base_dir / 'memory' / 'procedural.json'
        
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.procedures = {}
        self._load()
    
    def _load(self) -> None:
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.procedures = data.get('procedures', {})
            except Exception as e:
                log.warning(f"[MEMORY] Failed to load procedures, using empty: {e}")
                self.procedures = {}
    
    def _save(self) -> None:
        data = {
            'procedures': self.procedures,
            'updated_at': datetime.now().isoformat()
        }
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def store_procedure(self, name: str, steps: List[Dict[str, Any]],
                        context: str = None, success_rate: float = None) -> None:
        """Store a learned procedure."""
        self.procedures[name] = {
            'name': name,
            'steps': steps,
            'context': context or '',
            'success_rate': success_rate or 1.0,
            'created_at': datetime.now().isoformat(),
            'usage_count': 0
        }
        self._save()
    
    def get_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a procedure by name."""
        proc = self.procedures.get(name)
        if proc:
            proc['usage_count'] = proc.get('usage_count', 0) + 1
            self._save()
        return proc
    
    def list_procedures(self) -> List[str]:
        """List all procedure names."""
        return list(self.procedures.keys())
    
    def update_success_rate(self, name: str, success: bool) -> None:
        """Update the success rate for a procedure."""
        if name not in self.procedures:
            return
        
        proc = self.procedures[name]
        current_rate = proc.get('success_rate', 1.0)
        count = proc.get('usage_count', 1)
        
        # Exponential moving average
        alpha = 0.1
        new_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * current_rate
        proc['success_rate'] = new_rate
        self._save()


class MemoryManager:
    """
    Central coordinator for all memory systems.
    Provides unified access to working, episodic, semantic, and procedural memory.
    """
    
    def __init__(self, session_id: str = None):
        """
        Initialize the memory manager.
        
        Args:
            session_id: Unique identifier for the current session
        """
        self.session_id = session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Initialize all memory systems
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.procedural = ProceduralMemory()
        
        # Track memory state
        self.initialized_at = datetime.now()
        self.last_save = None
    
    def start_session(self) -> None:
        """Start a new session."""
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.working.clear()
        self.working.metadata['session_start'] = datetime.now().isoformat()
    
    def end_session(self) -> str:
        """
        End the current session and save to episodic memory.
        
        Returns:
            Session ID
        """
        # Save conversation to episodic memory
        messages = self.working.export_conversation()
        
        if messages:
            metadata = {
                'duration': str(datetime.now() - self.initialized_at),
                'message_count': len(messages),
                'tools_used': self._get_tools_used()
            }
            
            self.episodic.save_session(
                self.session_id,
                messages,
                metadata
            )
        
        self.last_save = datetime.now()
        return self.session_id
    
    def _get_tools_used(self) -> Dict[str, int]:
        """Get count of tools used in current session."""
        tools = {}
        for msg in self.working.messages:
            if msg.get('role') == 'tool':
                tool_name = msg.get('metadata', {}).get('tool_name', 'unknown')
                tools[tool_name] = tools.get(tool_name, 0) + 1
        return tools
    
    def add_user_message(self, content: str) -> None:
        """Add a user message to working memory."""
        self.working.add_user_message(content)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to working memory."""
        self.working.add_assistant_message(content)
    
    def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """Add a tool execution result to working memory."""
        self.working.add_tool_result(tool_name, result)
    
    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt."""
        self.working.set_system_prompt(prompt)
    
    def get_context_for_llm(self, include_memories: bool = True) -> List[Dict[str, str]]:
        """
        Get full context for LLM call, including relevant memories.
        
        Args:
            include_memories: Whether to include retrieved memories
            
        Returns:
            List of message dictionaries
        """
        # Get recent conversation from working memory
        messages = self.working.get_messages()
        
        if include_memories:
            # This method is called before each LLM call
            # Memories are injected by the brain/context layer
            pass
        
        return messages
    
    def retrieve_relevant_memories(self, query: str, 
                                   top_k: int = 5) -> Dict[str, Any]:
        """
        Retrieve relevant memories for a query.
        
        Args:
            query: The query/context to search for
            top_k: Number of results per memory type
            
        Returns:
            Dictionary with memories from each type
        """
        results = {
            'semantic': [],
            'episodic': [],
            'procedural': [],
            'working': []
        }
        
        # Search semantic memory
        semantic_results = self.semantic.search(query, top_k=top_k)
        results['semantic'] = [
            {'content': fact['content'], 'category': fact['category'], 'score': score}
            for fact, score in semantic_results
        ]
        
        # Search episodic memory (recent sessions)
        recent_sessions = self.episodic.list_sessions(limit=top_k)
        results['episodic'] = recent_sessions
        
        # Get relevant procedures
        proc_names = self.procedural.list_procedures()
        results['procedural'] = [
            self.procedural.get_procedure(name)
            for name in proc_names[:top_k]
        ]
        
        # Search working memory
        working_matches = self.working.search_messages(query)
        results['working'] = [
            {'message': m['message'], 'index': m['index']}
            for m in working_matches[:top_k]
        ]
        
        return results
    
    def remember_fact(self, content: str, category: str = 'general',
                      metadata: Dict[str, Any] = None) -> str:
        """Store a fact in semantic memory."""
        return self.semantic.remember(content, category, metadata)
    
    def recall_facts(self, query: str, top_k: int = 5) -> List[str]:
        """Recall relevant facts from semantic memory."""
        return self.semantic.recall(query, top_k)
    
    def learn_procedure(self, name: str, steps: List[Dict[str, Any]],
                        context: str = None) -> None:
        """Store a learned procedure."""
        self.procedural.store_procedure(name, steps, context)
    
    def get_procedure(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a learned procedure."""
        return self.procedural.get_procedure(name)
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of all memory systems."""
        return {
            'session_id': self.session_id,
            'initialized_at': self.initialized_at.isoformat(),
            'last_save': self.last_save.isoformat() if self.last_save else None,
            'working_memory': self.working.get_stats(),
            'episodic_memory': self.episodic.get_all_stats(),
            'semantic_memory': self.semantic.get_stats(),
            'procedural_memory': {
                'procedure_count': len(self.procedural.procedures),
                'procedures': self.procedural.list_procedures()
            }
        }
    
    def export_all(self, output_dir: str = None) -> str:
        """
        Export all memories to files.
        
        Args:
            output_dir: Output directory (default: jarvis/memory/exports)
            
        Returns:
            Path to export directory
        """
        if output_dir is None:
            base_dir = Path(__file__).parent.parent
            output_dir = base_dir / 'memory' / 'exports'
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Export episodic
        self.episodic.export_all_sessions(
            str(output_dir / f'episodic_{timestamp}.json')
        )
        
        # Export semantic
        self.semantic.export_facts(
            str(output_dir / f'semantic_{timestamp}.json')
        )
        
        # Export working
        with open(output_dir / f'working_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'messages': self.working.export_conversation()
            }, f, indent=2, ensure_ascii=False)
        
        # Export procedural
        with open(output_dir / f'procedural_{timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'procedures': list(self.procedural.procedures.values())
            }, f, indent=2, ensure_ascii=False)
        
        return str(output_dir)
    
    def clear_all(self, confirm: bool = False) -> None:
        """
        Clear all memories. Use with caution!
        
        Args:
            confirm: Must be True to proceed
        """
        if not confirm:
            raise ValueError("Must set confirm=True to clear all memories")
        
        self.working.clear()
        self.episodic.index = {'sessions': [], 'total_sessions': 0}
        self.episodic._save_index()
        self.semantic.facts = {}
        self.semantic._save()
        self.procedural.procedures = {}
        self.procedural._save()


# Singleton instance
_memory_manager_instance = None

def get_memory_manager(session_id: str = None) -> MemoryManager:
    """Get the singleton MemoryManager instance."""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager(session_id)
    return _memory_manager_instance
