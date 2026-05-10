"""
Persistent Long-Term Memory with RAG (Retrieval-Augmented Generation)

Stores user preferences, chat history, and contextual information in a vector database
for semantic retrieval across sessions. Makes the agent remember user preferences
and personalize interactions over time.

Features:
- Automatic extraction of user preferences from conversations
- Semantic search for relevant memories
- Context injection into LLM prompts
- Memory consolidation and pruning
- Session persistence
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import vector DB dependencies
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning("chromadb not available, using fallback memory storage")
    CHROMADB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("sentence-transformers not available, using keyword-based retrieval")
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@dataclass
class Memory:
    """A single memory unit with metadata."""
    content: str
    category: str  # 'preference', 'fact', 'history', 'context'
    timestamp: float = field(default_factory=time.time)
    importance: float = 1.0  # 0-1 scale for memory retention
    access_count: int = 0
    last_accessed: float = 0.0
    source: str = ""  # e.g., 'user_statement', 'inferred', 'tool_result'
    memory_id: str = ""
    
    def __post_init__(self):
        if not self.memory_id:
            # Generate deterministic ID from content
            self.memory_id = hashlib.sha256(
                f"{self.content}:{self.timestamp}".encode()
            ).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "category": self.category,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "source": self.source,
            "memory_id": self.memory_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        return cls(**data)


class VectorMemoryStore:
    """
    Vector-based memory storage using ChromaDB for semantic search.
    
    Falls back to keyword-based search if dependencies unavailable.
    """
    
    def __init__(self, persist_dir: str = "./data/long_term_memory"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        self._client = None
        self._collection = None
        self._embedder = None
        self._fallback_memories: list[Memory] = []
        
        self._init_storage()
    
    def _init_storage(self):
        """Initialize vector database or fallback storage."""
        if CHROMADB_AVAILABLE:
            try:
                self._client = chromadb.PersistentClient(
                    path=str(self.persist_dir),
                    settings=Settings(anonymized_telemetry=False)
                )
                self._collection = self._client.get_or_create_collection(
                    name="agent_memories",
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info(f"ChromaDB initialized at {self.persist_dir}")
                
                if SENTENCE_TRANSFORMERS_AVAILABLE:
                    self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
                    logger.info("Sentence transformer loaded for embeddings")
                else:
                    logger.warning("Using ChromaDB with default embeddings")
                    
            except Exception as e:
                logger.error(f"ChromaDB initialization failed: {e}, using fallback")
                self._client = None
                self._collection = None
        else:
            logger.info("Using fallback in-memory storage")
    
    def add_memory(self, memory: Memory) -> bool:
        """Add a memory to the store."""
        if self._collection is not None and self._embedder is not None:
            try:
                embedding = self._embedder.encode(memory.content).tolist()
                self._collection.add(
                    ids=[memory.memory_id],
                    embeddings=[embedding],
                    metadatas=[memory.to_dict()],
                    documents=[memory.content]
                )
                logger.debug(f"Added memory: {memory.memory_id[:8]} ({memory.category})")
                return True
            except Exception as e:
                logger.error(f"Failed to add memory to ChromaDB: {e}")
        
        # Fallback to in-memory storage
        self._fallback_memories.append(memory)
        logger.debug(f"Added memory to fallback: {memory.memory_id[:8]}")
        return True
    
    def search_memories(
        self, 
        query: str, 
        category: Optional[str] = None,
        limit: int = 5,
        min_importance: float = 0.0
    ) -> list[Memory]:
        """
        Search for relevant memories using semantic similarity.
        
        Args:
            query: Search query text
            category: Filter by memory category (optional)
            limit: Maximum number of results
            min_importance: Minimum importance threshold
        
        Returns:
            List of matching memories sorted by relevance
        """
        results = []
        
        if self._collection is not None:
            try:
                # Build filter
                where_filter = None
                if category:
                    where_filter = {"category": category}
                
                if self._embedder is not None:
                    query_embedding = self._embedder.encode(query).tolist()
                    chroma_results = self._collection.query(
                        query_embeddings=[query_embedding],
                        n_results=limit * 2,  # Get more to filter
                        where=where_filter,
                        include=["metadatas", "distances"]
                    )
                    
                    # Process results
                    if chroma_results and chroma_results['metadatas']:
                        for i, metadata in enumerate(chroma_results['metadatas'][0]):
                            if metadata.get('importance', 1.0) >= min_importance:
                                memory = Memory.from_dict(metadata)
                                memory.last_accessed = time.time()
                                memory.access_count += 1
                                results.append(memory)
                                
                                if len(results) >= limit:
                                    break
                else:
                    # ChromaDB without custom embedder (uses default)
                    chroma_results = self._collection.query(
                        query_texts=[query],
                        n_results=limit * 2,
                        where=where_filter,
                        include=["metadatas", "distances"]
                    )
                    
                    if chroma_results and chroma_results['metadatas']:
                        for metadata in chroma_results['metadatas'][0]:
                            if metadata.get('importance', 1.0) >= min_importance:
                                memory = Memory.from_dict(metadata)
                                memory.last_accessed = time.time()
                                memory.access_count += 1
                                results.append(memory)
                                
                                if len(results) >= limit:
                                    break
                                    
            except Exception as e:
                logger.error(f"ChromaDB search failed: {e}, using fallback")
        
        # Fallback to keyword-based search
        if not results:
            results = self._keyword_search(query, category, limit, min_importance)
        
        return results
    
    def _keyword_search(
        self,
        query: str,
        category: Optional[str],
        limit: int,
        min_importance: float
    ) -> list[Memory]:
        """Fallback keyword-based search."""
        query_words = set(query.lower().split())
        scored_memories = []
        
        candidates = self._fallback_memories
        if category:
            candidates = [m for m in candidates if m.category == category]
        
        for memory in candidates:
            if memory.importance < min_importance:
                continue
            
            # Simple word overlap scoring
            content_words = set(memory.content.lower().split())
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), 1)
            
            # Boost by importance and recency
            age_days = (time.time() - memory.timestamp) / 86400
            recency_boost = max(0, 1 - age_days / 30)  # Decay over 30 days
            
            final_score = score * 0.7 + memory.importance * 0.2 + recency_boost * 0.1
            scored_memories.append((final_score, memory))
        
        # Sort by score and return top results
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, memory in scored_memories[:limit]:
            memory.last_accessed = time.time()
            memory.access_count += 1
            results.append(memory)
        
        return results
    
    def update_memory(self, memory_id: str, updates: dict) -> bool:
        """Update memory metadata."""
        if self._collection is not None:
            try:
                # Get current memory
                current = self._collection.get(ids=[memory_id], include=["metadatas"])
                if current and current['metadatas']:
                    metadata = current['metadatas'][0]
                    metadata.update(updates)
                    
                    self._collection.update(
                        ids=[memory_id],
                        metadatas=[metadata]
                    )
                    return True
            except Exception as e:
                logger.error(f"Failed to update memory in ChromaDB: {e}")
        
        # Update fallback storage
        for i, mem in enumerate(self._fallback_memories):
            if mem.memory_id == memory_id:
                for key, value in updates.items():
                    setattr(mem, key, value)
                return True
        
        return False
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        if self._collection is not None:
            try:
                self._collection.delete(ids=[memory_id])
                return True
            except Exception as e:
                logger.error(f"Failed to delete memory from ChromaDB: {e}")
        
        # Delete from fallback
        self._fallback_memories = [
            m for m in self._fallback_memories if m.memory_id != memory_id
        ]
        return True
    
    def get_all_memories(self, category: Optional[str] = None) -> list[Memory]:
        """Get all memories, optionally filtered by category."""
        memories = []
        
        if self._collection is not None:
            try:
                where_filter = {"category": category} if category else None
                results = self._collection.get(
                    where=where_filter,
                    include=["metadatas"]
                )
                
                if results and results['metadatas']:
                    for metadata in results['metadatas']:
                        memories.append(Memory.from_dict(metadata))
            except Exception as e:
                logger.error(f"Failed to get memories from ChromaDB: {e}")
        
        # Also include fallback memories
        fallback = self._fallback_memories
        if category:
            fallback = [m for m in fallback if m.category == category]
        memories.extend(fallback)
        
        return memories
    
    def consolidate_memories(self, max_per_category: int = 100):
        """
        Prune old/low-importance memories to stay within limits.
        
        Keeps most important and recently accessed memories.
        """
        categories = ['preference', 'fact', 'history', 'context']
        
        for category in categories:
            memories = self.get_all_memories(category=category)
            if len(memories) <= max_per_category:
                continue
            
            # Score memories by importance + recency + access frequency
            scored = []
            for mem in memories:
                age_days = (time.time() - mem.timestamp) / 86400
                recency = max(0, 1 - age_days / 90)  # 90-day decay
                access_score = min(1.0, mem.access_count / 10)
                
                total_score = (
                    mem.importance * 0.5 +
                    recency * 0.3 +
                    access_score * 0.2
                )
                scored.append((total_score, mem.memory_id))
            
            # Sort and keep top N
            scored.sort(key=lambda x: x[0], reverse=True)
            to_delete = scored[max_per_category:]
            
            for _, memory_id in to_delete:
                self.delete_memory(memory_id)
            
            logger.info(
                f"Consolidated {category}: removed {len(to_delete)} memories, "
                f"kept {max_per_category}"
            )
    
    def stats(self) -> dict:
        """Get memory store statistics."""
        all_memories = self.get_all_memories()
        
        by_category = {}
        for mem in all_memories:
            cat = mem.category
            by_category[cat] = by_category.get(cat, 0) + 1
        
        return {
            "total_memories": len(all_memories),
            "by_category": by_category,
            "storage_backend": "chromadb" if self._collection else "fallback",
            "embedder": "sentence-transformer" if self._embedder else "default/keyword",
        }


class LongTermMemoryManager:
    """
    High-level manager for long-term memory operations.
    
    Handles preference extraction, context injection, and automatic
    memory management.
    """
    
    def __init__(self, persist_dir: str = "./data/long_term_memory"):
        self.store = VectorMemoryStore(persist_dir)
        self._preference_cache: dict[str, Any] = {}
        self._cache_dirty = False
    
    def remember_preference(self, preference_key: str, value: Any, confidence: float = 0.9):
        """
        Store a user preference.
        
        Args:
            preference_key: Key like 'preferred_editor', 'default_browser'
            value: The preference value
            confidence: Confidence level 0-1
        """
        content = f"User prefers {preference_key}: {value}"
        memory = Memory(
            content=content,
            category='preference',
            importance=confidence,
            source='user_statement'
        )
        self.store.add_memory(memory)
        self._preference_cache[preference_key] = value
        self._cache_dirty = True
        
        logger.info(f"Remembered preference: {preference_key} = {value}")
    
    def remember_fact(self, fact: str, importance: float = 0.5):
        """Store a factual piece of information."""
        memory = Memory(
            content=fact,
            category='fact',
            importance=importance,
            source='inferred'
        )
        self.store.add_memory(memory)
        logger.debug(f"Remembered fact: {fact[:50]}...")
    
    def remember_interaction(
        self, 
        user_input: str, 
        agent_response: str,
        success: bool = True
    ):
        """Store a conversation turn for historical context."""
        content = f"User: {user_input} | Agent: {agent_response}"
        memory = Memory(
            content=content,
            category='history',
            importance=0.3 if success else 0.5,  # Failures are more important
            source='conversation'
        )
        self.store.add_memory(memory)
    
    def get_relevant_context(
        self, 
        query: str, 
        max_memories: int = 5
    ) -> str:
        """
        Retrieve relevant memories as context for LLM.
        
        Returns formatted context string for injection into prompts.
        """
        memories = self.store.search_memories(query, limit=max_memories)
        
        if not memories:
            return ""
        
        context_parts = ["Relevant memories:"]
        for mem in memories:
            timestamp = datetime.fromtimestamp(mem.timestamp).strftime('%Y-%m-%d')
            context_parts.append(f"- [{mem.category}] {mem.content} (from {timestamp})")
        
        return "\n".join(context_parts)
    
    def get_user_preferences(self) -> dict[str, Any]:
        """Get all stored user preferences."""
        if self._preference_cache and not self._cache_dirty:
            return self._preference_cache.copy()
        
        # Reload from storage
        preferences = {}
        memories = self.store.get_all_memories(category='preference')
        
        for mem in memories:
            # Parse "User prefers X: Y" format
            content = mem.content
            if content.startswith("User prefers "):
                parts = content.replace("User prefers ", "").split(": ", 1)
                if len(parts) == 2:
                    key, value = parts
                    preferences[key] = value
        
        self._preference_cache = preferences
        self._cache_dirty = False
        return preferences
    
    def build_personalized_prompt(self, base_prompt: str, user_input: str) -> str:
        """
        Enhance a prompt with personalized context from memory.
        
        Injects user preferences and relevant facts into the prompt.
        """
        enhancements = []
        
        # Add preferences
        prefs = self.get_user_preferences()
        if prefs:
            pref_lines = ["User Preferences:"]
            for key, value in prefs.items():
                pref_lines.append(f"- {key}: {value}")
            enhancements.append("\n".join(pref_lines))
        
        # Add relevant context
        context = self.get_relevant_context(user_input, max_memories=3)
        if context:
            enhancements.append(context)
        
        if enhancements:
            return f"{base_prompt}\n\n{''.join(enhancements)}"
        
        return base_prompt
    
    def cleanup(self):
        """Run maintenance tasks."""
        self.store.consolidate_memories()
        logger.info("Long-term memory cleanup complete")
    
    def export_memories(self, filepath: str):
        """Export all memories to JSON file."""
        memories = self.store.get_all_memories()
        data = [mem.to_dict() for mem in memories]
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(memories)} memories to {filepath}")
    
    def import_memories(self, filepath: str):
        """Import memories from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        count = 0
        for item in data:
            memory = Memory.from_dict(item)
            self.store.add_memory(memory)
            count += 1
        
        logger.info(f"Imported {count} memories from {filepath}")
        return count


# Global instance
_memory_manager: Optional[LongTermMemoryManager] = None


def get_memory_manager() -> LongTermMemoryManager:
    """Get or create the global memory manager."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = LongTermMemoryManager()
    return _memory_manager


def init_memory_manager(persist_dir: str = "./data/long_term_memory") -> LongTermMemoryManager:
    """Initialize the global memory manager with custom settings."""
    global _memory_manager
    _memory_manager = LongTermMemoryManager(persist_dir)
    logger.info(f"Long-term memory manager initialized at {persist_dir}")
    return _memory_manager
