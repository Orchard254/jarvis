"""
Semantic Memory - Fact storage with embedding-based retrieval.
Stores user facts, preferences, and knowledge for semantic search.
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import math


class SemanticMemory:
    """
    Stores facts about the user with semantic similarity search.
    Uses simple TF-IDF-like scoring for retrieval (no external dependencies).
    """
    
    def __init__(self, storage_file: str = None):
        """
        Initialize semantic memory.
        
        Args:
            storage_file: Path to store facts. Defaults to jarvis/memory/semantic.json
        """
        if storage_file is None:
            base_dir = Path(__file__).parent.parent
            storage_file = base_dir / 'memory' / 'semantic.json'
        
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.facts = {}
        self.vocabulary = {}
        self.idf_scores = {}
        self._load()
    
    def _load(self) -> None:
        """Load facts from disk."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.facts = data.get('facts', {})
                    self.vocabulary = data.get('vocabulary', {})
                    self.idf_scores = data.get('idf_scores', {})
            except Exception:
                self.facts = {}
                self.vocabulary = {}
                self.idf_scores = {}
    
    def _save(self) -> None:
        """Save facts to disk."""
        data = {
            'facts': self.facts,
            'vocabulary': self.vocabulary,
            'idf_scores': self.idf_scores,
            'updated_at': datetime.now().isoformat()
        }
        
        with open(self.storage_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        # Convert to lowercase and split on non-alphanumeric
        import re
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens
    
    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Compute term frequency for a document."""
        tf = {}
        total = len(tokens)
        if total == 0:
            return tf
        
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        
        # Normalize
        for token in tf:
            tf[token] /= total
        
        return tf
    
    def _update_idf(self) -> None:
        """Update IDF scores based on current facts."""
        num_docs = len(self.facts)
        if num_docs == 0:
            return
        
        # Count document frequency for each term
        doc_freq = {}
        for fact_id, fact in self.facts.items():
            text = fact.get('content', '') + ' ' + fact.get('category', '')
            tokens = set(self._tokenize(text))
            for token in tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        
        # Compute IDF
        self.idf_scores = {}
        for token, df in doc_freq.items():
            # IDF = log(N / df)
            self.idf_scores[token] = math.log(num_docs / df) + 1
        
        # Update vocabulary
        self.vocabulary = set(self.idf_scores.keys())
    
    def add_fact(self, content: str, category: str = 'general',
                 metadata: Dict[str, Any] = None, fact_id: str = None) -> str:
        """
        Add a fact to semantic memory.
        
        Args:
            content: The fact content
            category: Category of the fact (preference, routine, fact, etc.)
            metadata: Additional metadata
            fact_id: Optional custom ID (auto-generated if not provided)
            
        Returns:
            The fact ID
        """
        if fact_id is None:
            # Generate ID from content hash
            fact_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        fact = {
            'id': fact_id,
            'content': content,
            'category': category,
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'access_count': 0,
            'last_accessed': None
        }
        
        self.facts[fact_id] = fact
        self._update_idf()
        self._save()
        
        return fact_id
    
    def get_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific fact by ID."""
        fact = self.facts.get(fact_id)
        if fact:
            fact['access_count'] = fact.get('access_count', 0) + 1
            fact['last_accessed'] = datetime.now().isoformat()
            self._save()
        return fact
    
    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact by ID."""
        if fact_id in self.facts:
            del self.facts[fact_id]
            self._update_idf()
            self._save()
            return True
        return False
    
    def update_fact(self, fact_id: str, content: str = None,
                    category: str = None, metadata: Dict[str, Any] = None) -> bool:
        """Update an existing fact."""
        if fact_id not in self.facts:
            return False
        
        fact = self.facts[fact_id]
        
        if content is not None:
            fact['content'] = content
        if category is not None:
            fact['category'] = category
        if metadata is not None:
            fact['metadata'] = metadata
        
        fact['updated_at'] = datetime.now().isoformat()
        self._update_idf()
        self._save()
        
        return True
    
    def search(self, query: str, top_k: int = 10,
               category_filter: str = None) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for relevant facts using semantic similarity.
        
        Args:
            query: Search query
            top_k: Number of results to return
            category_filter: Optional category filter
            
        Returns:
            List of (fact, score) tuples sorted by relevance
        """
        if not self.facts:
            return []
        
        # Tokenize query
        query_tokens = self._tokenize(query)
        query_tf = self._compute_tf(query_tokens)
        
        # Compute query vector (TF-IDF)
        query_vector = {}
        for token, tf in query_tf.items():
            idf = self.idf_scores.get(token, 0)
            query_vector[token] = tf * idf
        
        # Score each fact
        scores = []
        for fact_id, fact in self.facts.items():
            # Apply category filter
            if category_filter and fact.get('category') != category_filter:
                continue
            
            # Compute fact vector
            text = fact.get('content', '') + ' ' + fact.get('category', '')
            fact_tokens = self._tokenize(text)
            fact_tf = self._compute_tf(fact_tokens)
            
            fact_vector = {}
            for token, tf in fact_tf.items():
                idf = self.idf_scores.get(token, 0)
                fact_vector[token] = tf * idf
            
            # Compute cosine similarity
            similarity = self._cosine_similarity(query_vector, fact_vector)
            
            if similarity > 0:
                scores.append((fact, similarity))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    def _cosine_similarity(self, vec1: Dict[str, float], 
                           vec2: Dict[str, float]) -> float:
        """Compute cosine similarity between two sparse vectors."""
        # Find common terms
        common_terms = set(vec1.keys()) & set(vec2.keys())
        
        if not common_terms:
            return 0.0
        
        # Dot product
        dot_product = sum(vec1[t] * vec2[t] for t in common_terms)
        
        # Magnitudes
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    def get_facts_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get all facts in a category."""
        return [
            fact for fact in self.facts.values()
            if fact.get('category') == category
        ]
    
    def get_all_facts(self) -> List[Dict[str, Any]]:
        """Get all facts."""
        return list(self.facts.values())
    
    def get_categories(self) -> List[str]:
        """Get all unique categories."""
        categories = set()
        for fact in self.facts.values():
            cat = fact.get('category', 'general')
            categories.add(cat)
        return list(categories)
    
    def remember(self, content: str, category: str = 'general',
                 metadata: Dict[str, Any] = None) -> str:
        """
        Convenience method to remember a fact.
        Alias for add_fact with better naming.
        """
        return self.add_fact(content, category, metadata)
    
    def recall(self, query: str, top_k: int = 5) -> List[str]:
        """
        Convenience method to recall relevant facts.
        Returns just the content strings.
        """
        results = self.search(query, top_k=top_k)
        return [fact['content'] for fact, score in results]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        category_counts = {}
        for fact in self.facts.values():
            cat = fact.get('category', 'general')
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        return {
            'total_facts': len(self.facts),
            'categories': category_counts,
            'vocabulary_size': len(self.vocabulary),
            'storage_file': str(self.storage_file)
        }
    
    def export_facts(self, output_path: str = None) -> str:
        """Export all facts to a JSON file."""
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"semantic_export_{timestamp}.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'facts': list(self.facts.values())
            }, f, indent=2, ensure_ascii=False)
        
        return output_path
    
    def import_facts(self, input_path: str, merge: bool = True) -> int:
        """
        Import facts from a JSON file.
        
        Args:
            input_path: Path to import file
            merge: If True, merge with existing facts; if False, replace
            
        Returns:
            Number of facts imported
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        imported_facts = data.get('facts', [])
        
        if not merge:
            self.facts = {}
        
        count = 0
        for fact in imported_facts:
            fact_id = fact.get('id')
            if fact_id:
                self.facts[fact_id] = fact
                count += 1
        
        self._update_idf()
        self._save()
        
        return count


# Singleton instance
_semantic_memory_instance = None

def get_semantic_memory() -> SemanticMemory:
    """Get the singleton SemanticMemory instance."""
    global _semantic_memory_instance
    if _semantic_memory_instance is None:
        _semantic_memory_instance = SemanticMemory()
    return _semantic_memory_instance
