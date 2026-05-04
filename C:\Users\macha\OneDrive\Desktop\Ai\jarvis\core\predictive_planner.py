"""
Predictive Planner - Leverages LLM's internal knowledge to predict user intent
and generate optimized execution plans without wasteful trial-and-error.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PredictivePlanner:
    """
    Uses LLM's pretrained knowledge to predict URLs, correct typos,
    and generate high-confidence execution plans.
    """
    
    def __init__(self, brain):
        self.brain = brain
        self.known_domains = {
            'kilimall': 'https://www.kilimall.co.ke',
            'kilimall kenya': 'https://www.kilimall.co.ke',
            'kilimall uganda': 'https://www.kilimall.ug',
            'amazon': 'https://www.amazon.com',
            'google': 'https://www.google.com',
            'youtube': 'https://www.youtube.com',
            'facebook': 'https://www.facebook.com',
            'twitter': 'https://twitter.com',
            'instagram': 'https://www.instagram.com',
            'linkedin': 'https://www.linkedin.com',
            'github': 'https://github.com',
            'stackoverflow': 'https://stackoverflow.com',
            'reddit': 'https://www.reddit.com',
            'netflix': 'https://www.netflix.com',
            'spotify': 'https://www.spotify.com',
        }
        
    def predict_intent(self, user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use LLM to predict user intent with high confidence using internal knowledge.
        Returns structured prediction with corrected entities and predicted actions.
        """
        prompt = f"""Analyze this user request and predict their exact intent using your internal knowledge.

User Request: "{user_input}"

Your task:
1. Correct any typos or misspellings (e.g., "refubished" → "refurbished", "kilimal" → "kilimall")
2. Identify the target website/entity and predict its URL from your knowledge
3. Determine the exact action sequence needed
4. Assign confidence scores (0.0-1.0) to each prediction

Respond ONLY with valid JSON in this format:
{{
    "corrected_query": "the corrected user request",
    "entities": [
        {{
            "name": "entity name",
            "type": "website|app|product|etc",
            "predicted_url": "https://...",
            "confidence": 0.95
        }}
    ],
    "intent": "brief description of what user wants to achieve",
    "actions": [
        {{
            "step": 1,
            "action": "open_url | open_app | search_web | fill_input | click_element",
            "target": "specific target",
            "parameters": {{}},
            "confidence": 0.9
        }}
    ],
    "overall_confidence": 0.85,
    "requires_confirmation": false
}}

Rules:
- If confidence < 0.7 for any critical element, set requires_confirmation to true
- Use your internal knowledge to predict URLs (e.g., you know kilimall is kilimall.co.ke)
- Be specific with action parameters
- Do not include any text outside the JSON"""

        try:
            response = self.brain.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1  # Low temperature for deterministic predictions
            )
            
            # Extract JSON from response
            content = response.get('content', '')
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                prediction = json.loads(content[json_start:json_end])
                logger.info(f"Intent prediction confidence: {prediction.get('overall_confidence', 0):.2f}")
                return prediction
            else:
                logger.warning("Failed to extract JSON from prediction response")
                return self._fallback_prediction(user_input)
                
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return self._fallback_prediction(user_input)
    
    def _fallback_prediction(self, user_input: str) -> Dict[str, Any]:
        """Fallback when LLM prediction fails."""
        return {
            "corrected_query": user_input,
            "entities": [],
            "intent": "Execute user request",
            "actions": [],
            "overall_confidence": 0.5,
            "requires_confirmation": True
        }
    
    def resolve_entity(self, entity_name: str) -> Optional[str]:
        """Resolve entity name to URL using known domains."""
        entity_lower = entity_name.lower().strip()
        
        # Direct match
        if entity_lower in self.known_domains:
            return self.known_domains[entity_lower]
        
        # Partial match
        for key, url in self.known_domains.items():
            if key in entity_lower or entity_lower in key:
                return url
        
        return None
    
    def generate_optimized_plan(self, prediction: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert prediction into an optimized execution plan.
        High-confidence predictions skip unnecessary steps.
        """
        plan = []
        
        if prediction.get('overall_confidence', 0) >= 0.8:
            # High confidence: execute predicted actions directly
            for action in prediction.get('actions', []):
                plan.append({
                    'tool': action['action'],
                    'params': action.get('parameters', {}),
                    'confidence': action.get('confidence', 0.8),
                    'skip_validation': True  # Trust LLM's prediction
                })
        else:
            # Lower confidence: add validation steps
            for i, action in enumerate(prediction.get('actions', [])):
                plan.append({
                    'tool': action['action'],
                    'params': action.get('parameters', {}),
                    'confidence': action.get('confidence', 0.5),
                    'skip_validation': False,
                    'validate_after': i < len(prediction.get('actions', [])) - 1
                })
        
        return plan
    
    def learn_from_execution(self, 
                            prediction: Dict[str, Any],
                            actual_result: Dict[str, Any],
                            success: bool) -> None:
        """
        Learn from execution results to improve future predictions.
        Stores experience for adaptive learning.
        """
        experience = {
            'timestamp': datetime.now().isoformat(),
            'prediction': prediction,
            'actual_result': actual_result,
            'success': success,
            'lessons': []
        }
        
        if not success:
            # Analyze what went wrong
            if actual_result.get('error'):
                experience['lessons'].append(f"Error: {actual_result['error']}")
            
            # Could adjust confidence thresholds or update known_domains
            logger.info(f"Learning from failed execution: {experience['lessons']}")
        else:
            logger.info("Successfully executed predicted plan")
        
        # Store in memory for future reference (could be enhanced with vector storage)
        # For now, log the experience
        logger.debug(f"Stored experience: {json.dumps(experience, indent=2)}")
