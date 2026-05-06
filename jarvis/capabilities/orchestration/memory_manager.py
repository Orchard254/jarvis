"""
memory_manager: Store/retrieve short + long term context

Manages working memory for current session and persistent memory
for long-term knowledge.
"""

import logging
import time
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """Entry in the memory system."""
    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    ttl: Optional[float] = None  # Time to live in seconds
    tags: list[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        """Check if entry has expired based on TTL."""
        if self.ttl is None:
            return False
        return (time.time() - self.timestamp) > self.ttl
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "tags": self.tags,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "expired": self.is_expired()
        }


class MemoryManager:
    """
    Manages short-term and long-term memory for JARVIS.
    
    Features:
    - Short-term memory (session-based, volatile)
    - Long-term memory (persistent, file-backed)
    - TTL support for automatic expiration
    - Tag-based search and retrieval
    - Access tracking for memory prioritization
    """
    
    def __init__(self, storage_path: Optional[str] = None, 
                 auto_save: bool = True):
        """
        Initialize the MemoryManager.
        
        Args:
            storage_path: Path for persistent memory storage
            auto_save: Whether to auto-save long-term memory on changes
        """
        self._short_term: dict[str, MemoryEntry] = {}
        self._long_term: dict[str, MemoryEntry] = {}
        self._history: list[tuple] = []
        
        self.storage_path = Path(storage_path) if storage_path else None
        self.auto_save = auto_save
        self._dirty = False
        
        # Load persistent memory if available
        if self.storage_path:
            self._load_long_term_memory()
    
    def execute(self, action: str, key: Optional[str] = None,
                value: Any = None, long_term: bool = False,
                query: Optional[str] = None, tags: Optional[list[str]] = None,
                ttl: Optional[float] = None, **kwargs) -> dict:
        """
        Execute memory operations.
        
        Args:
            action: One of 'store', 'retrieve', 'search', 'clear', 'summary', 'delete'
            key: Memory key (for store/retrieve/delete)
            value: Value to store
            long_term: Use persistent memory
            query: Search query
            tags: Search tags
            ttl: Time to live in seconds
            
        Returns:
            Operation result
        """
        try:
            if action == "store":
                if not key:
                    return {"success": False, "error": "key required for store"}
                success = self.store(key, value, long_term, ttl, tags)
                return {"success": success, "output": {"stored": key}}
            
            elif action == "retrieve":
                if not key:
                    return {"success": False, "error": "key required for retrieve"}
                result = self.retrieve(key, long_term)
                if result is None:
                    return {"success": False, "error": f"Key '{key}' not found"}
                return {"success": True, "output": {"key": key, "value": result}}
            
            elif action == "search":
                results = self.search(query or "", tags, long_term)
                return {
                    "success": True, 
                    "output": {"results": results, "count": len(results)}
                }
            
            elif action == "delete":
                if not key:
                    return {"success": False, "error": "key required for delete"}
                success = self.delete(key, long_term)
                return {"success": success, "output": {"deleted": key}}
            
            elif action == "clear":
                self.clear(long_term)
                return {
                    "success": True, 
                    "output": {"cleared": "long_term" if long_term else "short_term"}
                }
            
            elif action == "summary":
                return {"success": True, "output": self.get_summary()}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Memory operation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def store(self, key: str, value: Any, long_term: bool = False, 
              ttl: Optional[float] = None, tags: Optional[list[str]] = None) -> bool:
        """
        Store a value in memory.
        
        Args:
            key: Unique identifier for the memory
            value: Data to store (must be JSON-serializable for long-term)
            long_term: If True, store in persistent memory
            ttl: Time to live in seconds (None = permanent)
            tags: Optional tags for categorization
            
        Returns:
            True if successful
        """
        try:
            # Verify JSON serializability for long-term storage
            if long_term:
                try:
                    json.dumps(value)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Value not JSON-serializable: {e}")
                    # Convert to string if not serializable
                    value = str(value)
            
            entry = MemoryEntry(
                key=key,
                value=value,
                ttl=ttl,
                tags=tags or []
            )
            
            storage = self._long_term if long_term else self._short_term
            storage[key] = entry
            
            self._history.append(("store", key, long_term, time.time()))
            logger.debug(f"Stored memory: {key} (long_term={long_term})")
            
            if long_term and self.auto_save:
                self._save_long_term_memory()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False
    
    def retrieve(self, key: str, long_term: bool = False) -> Optional[Any]:
        """
        Retrieve a value from memory.
        
        Args:
            key: Identifier to look up
            long_term: Search in persistent memory
            
        Returns:
            Value if found and not expired, None otherwise
        """
        storage = self._long_term if long_term else self._short_term
        entry = storage.get(key)
        
        if entry is None:
            return None
        
        # Check expiration
        if entry.is_expired():
            del storage[key]
            logger.debug(f"Expired memory removed: {key}")
            return None
        
        # Update access stats
        entry.access_count += 1
        entry.last_accessed = time.time()
        
        self._history.append(("retrieve", key, long_term, time.time()))
        return entry.value
    
    def delete(self, key: str, long_term: bool = False) -> bool:
        """
        Delete a memory entry.
        
        Args:
            key: Key to delete
            long_term: Delete from persistent memory
            
        Returns:
            True if deleted, False if not found
        """
        storage = self._long_term if long_term else self._short_term
        
        if key in storage:
            del storage[key]
            self._history.append(("delete", key, long_term, time.time()))
            logger.debug(f"Deleted memory: {key}")
            
            if long_term and self.auto_save:
                self._save_long_term_memory()
            
            return True
        
        return False
    
    def search(self, query: str, tags: Optional[list[str]] = None, 
               long_term: bool = True) -> list[dict]:
        """
        Search memory by content or tags.
        
        Args:
            query: Text to search for in values
            tags: Filter by tags
            long_term: Search in persistent memory
            
        Returns:
            List of matching entries (sorted by relevance)
        """
        storage = self._long_term if long_term else self._short_term
        results = []
        
        query_lower = query.lower() if query else ""
        
        for key, entry in storage.items():
            # Skip expired entries
            if entry.is_expired():
                continue
            
            score = 0
            
            # Search in value
            if query_lower and query_lower in str(entry.value).lower():
                score += 2
            
            # Search in key
            if query_lower and query_lower in key.lower():
                score += 1
            
            # Search by tags
            if tags:
                matching_tags = [t for t in entry.tags if t in tags]
                if matching_tags:
                    score += len(matching_tags)
            
            if score > 0:
                results.append({
                    "key": entry.key,
                    "value": entry.value,
                    "score": score,
                    "tags": entry.tags,
                    "timestamp": entry.timestamp,
                    "access_count": entry.access_count
                })
        
        # Sort by score (descending) then by recency
        results.sort(key=lambda x: (-x["score"], -x["timestamp"]))
        
        return results
    
    def clear(self, long_term: bool = False):
        """
        Clear memory.
        
        Args:
            long_term: Clear persistent memory
        """
        if long_term:
            self._long_term.clear()
            if self.auto_save:
                self._save_long_term_memory()
            logger.info("Cleared long-term memory")
        else:
            self._short_term.clear()
            logger.info("Cleared short-term memory")
        
        self._history.append(("clear", None, long_term, time.time()))
    
    def get_summary(self) -> dict:
        """Get summary of memory state."""
        # Clean expired entries first
        self._cleanup_expired()
        
        return {
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
            "recent_operations": self._history[-10:],
            "storage_path": str(self.storage_path) if self.storage_path else None,
            "auto_save_enabled": self.auto_save
        }
    
    def _cleanup_expired(self):
        """Remove expired entries from both memories."""
        expired_keys = []
        
        for key, entry in self._short_term.items():
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._short_term[key]
        
        expired_keys = []
        for key, entry in self._long_term.items():
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._long_term[key]
            self._dirty = True
        
        if expired_keys and self.auto_save:
            self._save_long_term_memory()
    
    def _save_long_term_memory(self):
        """Save long-term memory to disk."""
        if not self.storage_path:
            return
        
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert entries to serializable format
            data = {
                key: entry.to_dict()
                for key, entry in self._long_term.items()
                if not entry.is_expired()
            }
            
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._dirty = False
            logger.debug(f"Saved long-term memory to {self.storage_path}")
            
        except Exception as e:
            logger.error(f"Failed to save long-term memory: {e}")
    
    def _load_long_term_memory(self):
        """Load long-term memory from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            self._long_term = {}
            for key, entry_data in data.items():
                # Recreate MemoryEntry from dict
                entry = MemoryEntry(
                    key=entry_data['key'],
                    value=entry_data['value'],
                    timestamp=entry_data.get('timestamp', time.time()),
                    ttl=entry_data.get('ttl'),
                    tags=entry_data.get('tags', []),
                    access_count=entry_data.get('access_count', 0),
                    last_accessed=entry_data.get('last_accessed', time.time())
                )
                
                # Skip expired entries
                if not entry.is_expired():
                    self._long_term[key] = entry
            
            logger.info(f"Loaded {len(self._long_term)} long-term memories")
            
        except Exception as e:
            logger.error(f"Failed to load long-term memory: {e}")
    
    def get_all_keys(self, long_term: bool = False) -> list[str]:
        """Get all memory keys."""
        storage = self._long_term if long_term else self._short_term
        return list(storage.keys())
    
    def get_statistics(self) -> dict:
        """Get memory statistics."""
        self._cleanup_expired()
        
        total_short = len(self._short_term)
        total_long = len(self._long_term)
        
        avg_access_short = (
            sum(e.access_count for e in self._short_term.values()) / total_short
            if total_short > 0 else 0
        )
        
        avg_access_long = (
            sum(e.access_count for e in self._long_term.values()) / total_long
            if total_long > 0 else 0
        )
        
        return {
            "short_term_entries": total_short,
            "long_term_entries": total_long,
            "total_entries": total_short + total_long,
            "avg_access_short_term": avg_access_short,
            "avg_access_long_term": avg_access_long,
            "total_operations": len(self._history)
        }


# Singleton instance
_memory_manager_instance = None


def get_memory_manager(storage_path: Optional[str] = None,
                       auto_save: bool = True) -> MemoryManager:
    """
    Get or create MemoryManager singleton.
    
    Args:
        storage_path: Path for persistent storage
        auto_save: Enable auto-save
        
    Returns:
        MemoryManager instance
    """
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager(
            storage_path=storage_path,
            auto_save=auto_save
        )
    return _memory_manager_instance
