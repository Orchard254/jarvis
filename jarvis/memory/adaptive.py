"""
Adaptive Memory - Learns from user interactions to improve future predictions.
Stores successful patterns, corrections, and user preferences.
"""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class AdaptiveMemory:
    """
    Learns from execution history to improve future task planning.
    - Stores successful tool sequences for common intents
    - Remembers user corrections (e.g., preferred domains)
    - Adapts to user's specific environment (installed apps, working selectors)
    """
    
    def __init__(self, storage_path: str = "jarvis_data/adaptive_memory.json"):
        self.storage_path = storage_path
        self.data = self._load()
    
    def _load(self) -> Dict:
        """Load memory from disk."""
        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "successful_patterns": {},
                "failed_patterns": {},
                "user_corrections": {},
                "preferences": {},
                "environment_facts": {}
            }
        except Exception as e:
            logger.warning(f"Could not load adaptive memory: {e}")
            return {}
    
    def _save(self):
        """Persist memory to disk."""
        try:
            import os
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save adaptive memory: {e}")
    
    def record_success(self, intent: str, steps: List[Dict], duration_ms: int = 0):
        """
        Record a successful execution pattern.
        intent: Normalized intent (e.g., "open_site_and_search")
        steps: List of {tool, params} that succeeded
        """
        if intent not in self.data["successful_patterns"]:
            self.data["successful_patterns"][intent] = []
        
        pattern = {
            "steps": steps,
            "count": self.data["successful_patterns"][intent].get("count", 0) + 1,
            "last_used": datetime.now().isoformat(),
            "avg_duration_ms": duration_ms
        }
        
        # Keep only top 5 most used patterns per intent
        self.data["successful_patterns"][intent].append(pattern)
        self.data["successful_patterns"][intent] = sorted(
            self.data["successful_patterns"][intent],
            key=lambda x: x["count"],
            reverse=True
        )[:5]
        
        self._save()
        logger.debug(f"Recorded success for intent: {intent}")
    
    def record_failure(self, intent: str, failed_step: Dict, error: str):
        """Record a failed pattern to avoid repetition."""
        key = f"{failed_step.get('tool')}_{json.dumps(failed_step.get('params'), sort_keys=True)}"
        
        if key not in self.data["failed_patterns"]:
            self.data["failed_patterns"][key] = {
                "count": 0,
                "errors": [],
                "alternatives_suggested": []
            }
        
        failure = self.data["failed_patterns"][key]
        failure["count"] += 1
        failure["last_error"] = error
        failure["last_seen"] = datetime.now().isoformat()
        
        if error not in failure["errors"]:
            failure["errors"].append(error)
        
        self._save()
        logger.warning(f"Recorded failure for {key}: {error}")
    
    def add_correction(self, original: str, corrected: str, context: str = ""):
        """Learn from user or LLM corrections."""
        key = original.lower()
        self.data["user_corrections"][key] = {
            "corrected_to": corrected,
            "context": context,
            "count": self.data["user_corrections"].get(key, {}).get("count", 0) + 1
        }
        self._save()
        logger.info(f"Learned correction: {original} -> {corrected}")
    
    def get_correction(self, text: str) -> Optional[str]:
        """Get known correction for a term."""
        key = text.lower()
        if key in self.data["user_corrections"]:
            return self.data["user_corrections"][key]["corrected_to"]
        return None
    
    def get_best_pattern(self, intent: str) -> Optional[List[Dict]]:
        """Get the most successful pattern for an intent."""
        if intent in self.data["successful_patterns"]:
            patterns = self.data["successful_patterns"][intent]
            if patterns:
                return patterns[0]["steps"]
        return None
    
    def is_likely_to_fail(self, tool: str, params: Dict) -> bool:
        """Check if a tool call has failed repeatedly before."""
        key = f"{tool}_{json.dumps(params, sort_keys=True)}"
        if key in self.data["failed_patterns"]:
            return self.data["failed_patterns"][key]["count"] >= 3
        return False
    
    def add_environment_fact(self, fact_type: str, key: str, value: any):
        """Store environment-specific facts (e.g., 'selector', 'domain', 'app_path')."""
        if fact_type not in self.data["environment_facts"]:
            self.data["environment_facts"][fact_type] = {}
        
        self.data["environment_facts"][fact_type][key] = {
            "value": value,
            "verified_count": self.data["environment_facts"][fact_type].get(key, {}).get("verified_count", 0) + 1,
            "last_verified": datetime.now().isoformat()
        }
        self._save()
    
    def get_environment_fact(self, fact_type: str, key: str, default=None):
        """Retrieve a stored environment fact."""
        return self.data["environment_facts"].get(fact_type, {}).get(key, {}).get("value", default)
    
    def get_learning_summary(self) -> Dict:
        """Return summary of learned knowledge."""
        return {
            "successful_patterns_count": len(self.data["successful_patterns"]),
            "failed_patterns_count": len(self.data["failed_patterns"]),
            "corrections_count": len(self.data["user_corrections"]),
            "environment_facts_count": sum(len(v) for v in self.data["environment_facts"].values())
        }
