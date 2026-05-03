"""
JARVIS Persistent Memory System with RAG (Retrieval-Augmented Generation)
Uses ChromaDB for vector storage and semantic search.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

logger = logging.getLogger(__name__)


class PersistentMemory:
    """Vector-based persistent memory with semantic search."""
    
    def __init__(self, data_dir: str = "jarvis_data/memory"):
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, "vector_store")
        self.history_file = os.path.join(data_dir, "conversation_history.json")
        
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(self.db_path, exist_ok=True)
        
        self.client = None
        self.collection = None
        
        if CHROMA_AVAILABLE:
            self._init_chroma()
        else:
            logger.warning("ChromaDB not available - using file-based memory only")
        
        self._load_history()
    
    def _init_chroma(self):
        """Initialize ChromaDB client and collection."""
        try:
            self.client = chromadb.PersistentClient(path=self.db_path)
            self.collection = self.client.get_or_create_collection(
                name="jarvis_memory",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.client = None
    
    def _load_history(self):
        """Load conversation history from file."""
        self.history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                logger.info(f"Loaded {len(self.history)} conversation records")
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
    
    def _save_history(self):
        """Save conversation history to file."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    def add_experience(self, user_input: str, assistant_response: str, 
                      context: Optional[Dict] = None):
        """Store an interaction in both history and vector DB."""
        timestamp = datetime.now().isoformat()
        
        record = {
            "id": hashlib.md5(f"{timestamp}{user_input}".encode()).hexdigest(),
            "timestamp": timestamp,
            "user": user_input,
            "assistant": assistant_response,
            "context": context or {}
        }
        
        # Add to history
        self.history.append(record)
        self._save_history()
        
        # Add to vector DB if available
        if self.collection:
            try:
                # Create searchable text
                search_text = f"{user_input} {assistant_response}"
                if context:
                    search_text += f" Context: {json.dumps(context)}"
                
                self.collection.add(
                    ids=[record["id"]],
                    documents=[search_text],
                    metadatas=[{
                        "user": user_input[:100],
                        "assistant": assistant_response[:100],
                        "timestamp": timestamp
                    }]
                )
                logger.debug(f"Added experience to vector store: {record['id']}")
            except Exception as e:
                logger.error(f"Failed to add to vector store: {e}")
    
    def search_memories(self, query: str, n_results: int = 5) -> List[Dict]:
        """Search for relevant past experiences using semantic similarity."""
        if not self.collection:
            # Fallback: simple text search in history
            return self._text_search(query, n_results)
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            memories = []
            if results and results['ids'] and results['ids'][0]:
                for i, id in enumerate(results['ids'][0]):
                    # Find full record from history
                    record = next((r for r in self.history if r['id'] == id), None)
                    if record:
                        memories.append({
                            **record,
                            "relevance_score": results['distances'][0][i] if 'distances' in results else 1.0
                        })
            
            return memories
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._text_search(query, n_results)
    
    def _text_search(self, query: str, n_results: int = 5) -> List[Dict]:
        """Fallback text-based search."""
        query_lower = query.lower()
        scored = []
        
        for record in self.history:
            score = 0
            text = f"{record['user']} {record['assistant']}".lower()
            if query_lower in text:
                score = text.count(query_lower)
            if score > 0:
                scored.append((score, record))
        
        scored.sort(reverse=True, key=lambda x: x[0])
        return [record for _, record in scored[:n_results]]
    
    def get_recent_conversations(self, limit: int = 10) -> List[Dict]:
        """Get most recent conversations."""
        return self.history[-limit:]
    
    def clear_memory(self):
        """Clear all stored memories."""
        self.history = []
        self._save_history()
        
        if self.collection:
            try:
                ids = self.collection.get()['ids']
                if ids:
                    self.collection.delete(ids=ids)
            except Exception as e:
                logger.error(f"Failed to clear vector store: {e}")
        
        logger.info("Memory cleared")
