"""
Core Memory Integration Module

Coordinates memory operations across all memory types for the JARVIS system.
Provides unified interface for storing and retrieving memories before each LLM call.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from memory.working import WorkingMemory
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.manager import ProceduralMemory

logger = logging.getLogger(__name__)


class CoreMemory:
    """
    Central memory coordinator for JARVIS.
    
    Integrates working, episodic, semantic, and procedural memory
    to provide context-aware memory retrieval for the LLM.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize core memory system.
        
        Args:
            config: Configuration dict with memory settings
        """
        self.config = config
        
        # Initialize memory components
        self.working = WorkingMemory(
            max_messages=config.get('working_memory_max_messages', 20),
            max_tokens_estimate=config.get('working_memory_max_tokens', 4000)
        )
        
        data_dir = config.get('data_dir', 'jarvis_data')
        self.episodic = EpisodicMemory(data_dir=data_dir)
        self.semantic = SemanticMemory(data_dir=data_dir)
        
        # Create procedural memory instance
        self.procedural = ProceduralMemory(
            storage_file=str(Path(data_dir) / 'procedural.json')
        )
        
        logger.info("Core memory system initialized")
    
    def add_user_message(self, message: str, metadata: Optional[Dict] = None) -> None:
        """
        Add a user message to working memory.
        
        Args:
            message: The user's message text
            metadata: Optional metadata (timestamp, source, etc.)
        """
        self.working.add_message(
            role='user',
            content=message,
            metadata=metadata
        )
        logger.debug(f"Added user message to working memory: {message[:50]}...")
    
    def add_assistant_message(self, message: str, metadata: Optional[Dict] = None) -> None:
        """
        Add an assistant response to working memory.
        
        Args:
            message: The assistant's response text
            metadata: Optional metadata (tool_calls, execution_results, etc.)
        """
        self.working.add_message(
            role='assistant',
            content=message,
            metadata=metadata
        )
        logger.debug(f"Added assistant message to working memory: {message[:50]}...")
    
    def add_system_message(self, message: str) -> None:
        """
        Add a system message to working memory.
        
        Args:
            message: The system message text
        """
        self.working.add_message(
            role='system',
            content=message,
            metadata=None
        )
    
    def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """
        Add a tool execution result to working memory.
        
        Args:
            tool_name: Name of the tool that was executed
            result: Tool execution result dict
        """
        self.working.add_tool_result(tool_name, result)
        logger.debug(f"Added tool result for {tool_name} to working memory")
    
    def retrieve_context(self, query: Optional[str] = None, 
                        limit: int = 5) -> Dict[str, Any]:
        """
        Retrieve relevant context from all memory types.
        
        Args:
            query: Optional query for semantic search
            limit: Maximum number of items to retrieve from each memory type
            
        Returns:
            Dict containing retrieved memories organized by type
        """
        context = {
            'working': [],
            'episodic': [],
            'semantic': [],
            'procedural': []
        }
        
        # Get recent working memory messages
        context['working'] = self.working.get_recent_messages(limit * 2)
        
        # Get relevant episodic memories if query provided
        if query:
            context['episodic'] = self.episodic.search_sessions(query)[:limit]
            
            # Get relevant semantic memories
            context['semantic'] = self.semantic.search(query, top_k=limit)
            
            # Get relevant procedural memories (simplified - just return procedure names)
            context['procedural'] = [{'name': name} for name in self.procedural.list_procedures()[:limit]]
        
        logger.debug(f"Retrieved context: {len(context['working'])} working, "
                    f"{len(context['episodic'])} episodic, "
                    f"{len(context['semantic'])} semantic, "
                    f"{len(context['procedural'])} procedural")
        
        return context
    
    def store_experience(self, goal: str, actions: List[Dict], 
                       outcome: str, success: bool) -> str:
        """
        Store a completed experience in episodic memory.
        
        Args:
            goal: The original goal/request
            actions: List of actions taken
            outcome: Description of the outcome
            success: Whether the goal was achieved
            
        Returns:
            Session ID for the stored experience
        """
        # Build messages from the interaction
        messages = [
            {'role': 'user', 'content': goal},
            {'role': 'assistant', 'content': f"Actions: {actions}\nOutcome: {outcome}"}
        ]
        
        metadata = {
            'goal': goal,
            'actions': actions,
            'outcome': outcome,
            'success': success
        }
        
        session_id = self.episodic.store_session(
            session_id=datetime.now().strftime('%Y%m%d_%H%M%S'),
            messages=messages,
            metadata=metadata
        )
        
        # Extract facts for semantic memory
        self._extract_facts(goal, outcome, success)
        
        # Update procedural memory if successful
        if success:
            self._update_procedural_memory(goal, actions)
        
        logger.info(f"Stored experience in episodic memory: {session_id}")
        return session_id
    
    def _extract_facts(self, goal: str, outcome: str, success: bool) -> None:
        """
        Extract factual information from experience for semantic memory.
        
        Args:
            goal: The original goal
            outcome: The outcome description
            success: Whether it was successful
        """
        # Simple heuristic fact extraction
        # In production, this would use an LLM to extract facts
        
        facts = []
        
        # Extract user preferences from successful outcomes
        if success:
            if 'volume' in goal.lower() or 'volume' in outcome.lower():
                facts.append({'fact': 'User adjusts audio volume frequently'})
            
            if 'file' in goal.lower() or 'document' in outcome.lower():
                facts.append({'fact': 'User works with files and documents'})
        
        for fact in facts:
            self.semantic.add_fact(fact['fact'], source='experience_extraction')
    
    def _update_procedural_memory(self, goal: str, actions: List[Dict]) -> None:
        """
        Update procedural memory with successful action patterns.
        
        Args:
            goal: The goal that was achieved
            actions: The sequence of actions that worked
        """
        # Extract action pattern
        action_types = [a.get('tool', a.get('action', 'unknown')) for a in actions]
        
        # Create procedural memory entry
        pattern_key = f"successful_pattern_{hash(goal) % 10000}"
        
        self.procedural.store_procedure(
            name=pattern_key,
            steps=[{
                'goal_pattern': goal[:100],  # Truncate for indexing
                'action_sequence': action_types,
                'full_actions': actions,
                'success_count': 1
            }]
        )
    
    def remember_fact(self, fact: str, category: Optional[str] = None) -> bool:
        """
        Explicitly store a fact in semantic memory.
        
        Args:
            fact: The fact to remember
            category: Optional category for the fact
            
        Returns:
            True if successfully stored
        """
        result = self.semantic.add_fact(fact, category=category)
        logger.info(f"Stored fact in semantic memory: {fact[:50]}...")
        return result
    
    def recall_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Recall memories relevant to a query.
        
        Args:
            query: The search query
            limit: Maximum number of results
            
        Returns:
            List of relevant memories
        """
        semantic_results = self.semantic.search(query, top_k=limit)
        episodic_results = self.episodic.search_sessions(query)[:limit]
        
        # Combine and rank results
        all_results = []
        for r in semantic_results:
            # semantic.search returns list of (fact_dict, score) tuples
            if isinstance(r, tuple):
                fact_dict, score = r
                all_results.append({
                    'type': 'semantic',
                    'content': fact_dict.get('content', fact_dict.get('fact', '')),
                    'relevance': score
                })
            else:
                all_results.append({
                    'type': 'semantic',
                    'content': r.get('fact', r.get('text', r.get('content', ''))),
                    'relevance': r.get('similarity', r.get('score', 0.0))
                })

        for r in episodic_results:
            # episodic.search_sessions returns list of dicts with 'session', 'match_count', 'relevance'
            if isinstance(r, dict):
                session_data = r.get('full_session', r.get('session', {}))
                all_results.append({
                    'type': 'episodic',
                    'content': session_data.get('summary', r.get('goal', '')),
                    'relevance': r.get('relevance', 0.0)
                })
        
        # Sort by relevance
        all_results.sort(key=lambda x: x['relevance'], reverse=True)
        
        return all_results[:limit]
    
    def get_conversation_history(self, include_tool_results: bool = True) -> List[Dict]:
        """
        Get the current conversation history from working memory.
        
        Args:
            include_tool_results: Whether to include tool execution results
            
        Returns:
            List of conversation messages
        """
        return self.working.get_messages(include_system=True)
    
    def clear_working_memory(self) -> None:
        """Clear the working memory buffer."""
        self.working.clear()
        logger.info("Working memory cleared")
    
    def start_new_session(self, session_name: Optional[str] = None) -> str:
        """
        Start a new episodic memory session.
        
        Args:
            session_name: Optional name for the session
            
        Returns:
            Session ID
        """
        session_id = self.episodic.start_session()
        logger.info(f"Started new memory session: {session_id}")
        return session_id
    
    def end_current_session(self, summary: Optional[str] = None) -> Optional[str]:
        """
        End the current episodic memory session.
        
        Args:
            summary: Optional summary of the session
            
        Returns:
            Session ID that was ended, or None if no active session
        """
        # Get current conversation messages
        messages = self.get_conversation_history()
        session_id = self.episodic.end_session(
            session_id=datetime.now().strftime('%Y%m%d_%H%M%S'),
            messages=messages,
            summary=summary
        )
        if session_id:
            logger.info(f"Ended memory session: {session_id}")
        return session_id
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage.
        
        Returns:
            Dict with memory statistics
        """
        return {
            'working': {
                'message_count': len(self.working.messages),
                'token_estimate': self.working.get_stats()['estimated_tokens']
            },
            'episodic': self.episodic.get_memory_stats(),
            'semantic': {
                'fact_count': len(self.semantic.facts),
                'embedding_dimensions': 768  # Using TF-IDF, not actual embeddings
            },
            'procedural': {
                'pattern_count': len(self.procedural.procedures)
            }
        }
