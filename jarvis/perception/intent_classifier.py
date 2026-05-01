"""
Intent Classifier - Routes between chat mode and agent mode.
Does NOT filter tool choices - the LLM handles tool selection.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class IntentClassifier:
    """
    Classifies user intent to route between chat and agent modes.
    
    Chat mode: Simple conversation, questions, information lookup
    Agent mode: Task execution requiring tool use
    """
    
    def __init__(self, ollama_client=None):
        """
        Initialize the intent classifier.
        
        Args:
            ollama_client: OllamaClient instance for classification
        """
        self.ollama_client = ollama_client
        self.classification_history = []
        
        # Keywords that strongly suggest agent mode
        self.agent_keywords = [
            'open', 'close', 'click', 'type', 'search', 'find',
            'create', 'delete', 'move', 'copy', 'rename',
            'run', 'execute', 'launch', 'start', 'stop',
            'change', 'set', 'adjust', 'increase', 'decrease',
            'take screenshot', 'capture', 'record',
            'send', 'download', 'upload', 'install',
            'show me', 'let me', 'help me', 'i want to',
            'can you', 'please', 'would you'
        ]
        
        # Keywords that suggest chat mode
        self.chat_keywords = [
            'what is', 'who is', 'when', 'where', 'why', 'how',
            'explain', 'tell me about', 'define', 'describe',
            'what do you think', 'opinion', 'idea',
            'hello', 'hi', 'hey', 'good morning', 'good evening',
            'thanks', 'thank you', 'bye', 'goodbye'
        ]
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def classify(self, user_input: str) -> Dict[str, Any]:
        """
        Classify user intent.
        
        Args:
            user_input: The user's input text
            
        Returns:
            Dictionary with classification results:
            {
                'mode': 'chat' or 'agent',
                'confidence': float 0-1,
                'reasoning': str,
                'requires_action': bool
            }
        """
        # Quick heuristic check first
        heuristic_result = self._heuristic_classify(user_input)
        
        # If high confidence from heuristics, use that
        if heuristic_result['confidence'] > 0.8:
            result = heuristic_result
            result['method'] = 'heuristic'
        else:
            # Use LLM for classification
            result = self._llm_classify(user_input)
            result['method'] = 'llm'
        
        # Store in history
        self.classification_history.append({
            'input': user_input[:200],
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep history bounded
        if len(self.classification_history) > 50:
            self.classification_history = self.classification_history[-50:]
        
        return result
    
    def _heuristic_classify(self, user_input: str) -> Dict[str, Any]:
        """Quick heuristic-based classification."""
        input_lower = user_input.lower()
        
        agent_score = 0
        chat_score = 0
        
        # Check for agent keywords
        for keyword in self.agent_keywords:
            if keyword in input_lower:
                agent_score += 1
        
        # Check for chat keywords
        for keyword in self.chat_keywords:
            if keyword in input_lower:
                chat_score += 1
        
        # Check for imperative verbs (action words)
        imperative_verbs = ['open', 'close', 'get', 'find', 'show', 'make', 
                           'create', 'delete', 'run', 'execute', 'click', 'type']
        words = input_lower.split()
        if words and words[0] in imperative_verbs:
            agent_score += 2
        
        # Check for question patterns
        question_words = ['what', 'who', 'when', 'where', 'why', 'how', 'is', 'are', 'does', 'do']
        if words and words[0] in question_words:
            chat_score += 1
        
        # Calculate confidence
        total = agent_score + chat_score
        if total == 0:
            # Default to chat for ambiguous input
            return {
                'mode': 'chat',
                'confidence': 0.5,
                'reasoning': 'No strong indicators, defaulting to chat mode',
                'requires_action': False
            }
        
        if agent_score > chat_score:
            confidence = min(0.5 + (agent_score - chat_score) * 0.15, 0.95)
            return {
                'mode': 'agent',
                'confidence': confidence,
                'reasoning': f'Detected action-oriented language (agent score: {agent_score}, chat score: {chat_score})',
                'requires_action': True
            }
        else:
            confidence = min(0.5 + (chat_score - agent_score) * 0.15, 0.95)
            return {
                'mode': 'chat',
                'confidence': confidence,
                'reasoning': f'Detected conversational or informational query (chat score: {chat_score}, agent score: {agent_score})',
                'requires_action': False
            }
    
    def _llm_classify(self, user_input: str) -> Dict[str, Any]:
        """Use LLM for more nuanced classification."""
        if self.ollama_client is None:
            return self._heuristic_classify(user_input)
        
        prompt = f"""Classify the following user input into one of two modes:

CHAT: Simple conversation, questions, information requests, greetings, thanks
AGENT: Tasks requiring action on the computer (opening apps, manipulating files, system control, etc.)

User input: "{user_input}"

Respond in JSON format:
{{
    "mode": "chat" or "agent",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation of the classification"
}}

Only classify as "agent" if the user is clearly requesting an action on their computer."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                response_format='json'
            )
            
            content = response.get('content', '{}')
            
            import json
            try:
                result = json.loads(content)
                return {
                    'mode': result.get('mode', 'chat'),
                    'confidence': result.get('confidence', 0.5),
                    'reasoning': result.get('reasoning', 'LLM classification'),
                    'requires_action': result.get('mode', 'chat') == 'agent'
                }
            except json.JSONDecodeError:
                # Fallback to heuristic
                return self._heuristic_classify(user_input)
                
        except Exception as e:
            # Fallback to heuristic on error
            return self._heuristic_classify(user_input)
    
    def is_agent_mode(self, user_input: str) -> bool:
        """
        Quick check if input requires agent mode.
        
        Args:
            user_input: User input text
            
        Returns:
            True if agent mode, False if chat mode
        """
        result = self.classify(user_input)
        return result['mode'] == 'agent'
    
    def get_classification_history(self, limit: int = 20) -> list:
        """Get recent classification history."""
        return self.classification_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear classification history."""
        self.classification_history = []


# Singleton instance
_intent_classifier_instance = None

def get_intent_classifier(ollama_client=None) -> IntentClassifier:
    """Get the singleton IntentClassifier instance."""
    global _intent_classifier_instance
    if _intent_classifier_instance is None:
        _intent_classifier_instance = IntentClassifier(ollama_client)
    elif ollama_client is not None:
        _intent_classifier_instance.set_client(ollama_client)
    return _intent_classifier_instance
