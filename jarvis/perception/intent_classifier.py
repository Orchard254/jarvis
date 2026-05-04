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
        
        # Explicit mode triggers - force agent mode when detected
        self.explicit_agent_triggers = [
            'do this:', 'execute:', 'run:', 'perform:', 'action:',
            'agent:', 'task:', 'make it:', 'actually ', 'just '
        ]
        
        # Keywords that strongly suggest agent mode
        self.agent_keywords = [
            # App/Window control
            'open', 'close', 'click', 'type', 'launch', 'start', 'stop', 'kill', 'restart',
            'minimize', 'maximize', 'restore', 'focus', 'switch',
            
            # File operations
            'create', 'delete', 'move', 'copy', 'rename', 'save', 'load',
            'download', 'upload', 'extract', 'compress',
            
            # Text input (including specific text content phrases)
            'write', 'input', 'enter text', 'paste text', 'clear text', 'delete text',
            'good morning', 'good afternoon', 'good evening', 'hello world',
            
            # Search & Navigation
            'search', 'find', 'locate', 'navigate', 'browse', 'visit', 'go to',
            'search in', 'search for', 'look for',
            
            # System control
            'run', 'execute', 'install', 'uninstall', 'configure', 'setup', 'update',
            'change', 'set', 'adjust', 'increase', 'decrease', 'enable', 'disable',
            'lock', 'unlock', 'shutdown', 'restart', 'sleep', 'hibernate',
            
            # Screen & Input
            'take screenshot', 'capture', 'record', 'scroll',
            'type text', 'press key', 'copy', 'paste', 'cut',
            
            # Communication
            'send', 'receive', 'email', 'message', 'notify', 'share',
            
            # Verification & Information (action-oriented)
            'check', 'verify', 'confirm', 'validate', 'test', 'ensure',
            'current', 'time', 'date', 'what time', 'battery', 'volume', 'brightness',
            'network', 'internet', 'wifi', 'bluetooth',
            'list', 'show', 'running', 'apps', 'processes',
            
            # Web control
            'open url', 'open website', 'close tab', 'close browser', 'new tab', 'refresh',
            'bookmark', 'history', 'clear cache',
            
            # Phrases indicating action request (specific tasks)
            'show me', 'let me', 
            'help me open', 'help me close', 'help me find', 'help me search',
            'i want to open', 'i want to close', 'i want to search', 'i want to find',
            'i need to open', 'i need to close', 'i need to search', 'i need to find',
            'can you open', 'can you close', 'can you search', 'can you find',
            'can you help me open', 'can you help me close', 'can you help me search',
            'please open', 'please close', 'please search', 'please find',
            'would you open', 'could you open', 'would you help me', 'could you help me',
            
            # Site-specific search
            'inside', 'within', 'on the site', 'on website'
        ]
        
        # Keywords that suggest chat mode (purely conversational/informational)
        self.chat_keywords = [
            # Questions about facts/opinions
            'what is', 'who is', 'when', 'where', 'why', 'how',
            'explain', 'tell me about', 'define', 'describe',
            'what do you think', 'opinion', 'idea', 'your thoughts',
            
            # Greetings and social (without time-specific phrases that could be text content)
            'hello', 'hi', 'hey',
            'how are you', 'how is it going', 'whats up',
            
            # Farewells and thanks
            'thanks', 'thank you', 'bye', 'goodbye', 'see you', 'take care',
            
            # Meta conversation (not action requests)
            'can you help', 'can you help me', 'are you able', 'do you know', 'is it possible',
            'i wonder', 'i am curious', 'just asking', 'just wondering',
            'can you tell me', 'could you tell me', 'would you tell me',
            
            # Clarification requests
            'what does', 'how does', 'why does', 'when did', 'who was'
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
        
        # Check for explicit agent mode triggers FIRST (highest priority)
        for trigger in self.explicit_agent_triggers:
            if trigger in input_lower:
                return {
                    'mode': 'agent',
                    'confidence': 0.95,
                    'reasoning': f'Explicit agent mode trigger detected: "{trigger}"',
                    'requires_action': True
                }
        
        # Remove articles for better phrase matching (e.g., "take a screenshot" -> "take screenshot")
        import re
        input_normalized = re.sub(r'\b(a|an|the)\b', ' ', input_lower).strip()
        input_normalized = re.sub(r'\s+', ' ', input_normalized)  # Normalize spaces
        
        agent_score = 0
        chat_score = 0
        
        # Check for agent keywords (multi-word phrases first, then single words)
        # Prioritize longer phrases to avoid partial matches
        multi_word_agents = [kw for kw in self.agent_keywords if ' ' in kw]
        single_word_agents = [kw for kw in self.agent_keywords if ' ' not in kw]
        
        for keyword in multi_word_agents:
            # Check both original and normalized input for phrase matching
            if keyword in input_lower or keyword in input_normalized:
                agent_score += 2  # Higher weight for multi-word phrases
        
        for keyword in single_word_agents:
            # Use word boundary check for single words to avoid false positives
            import re
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, input_lower):
                # Give extra weight to action verbs at the start of the command
                if input_lower.startswith(keyword + ' '):
                    agent_score += 2  # Double weight for imperative commands
                else:
                    agent_score += 1
        
        # Check for chat keywords (same approach)
        multi_word_chats = [kw for kw in self.chat_keywords if ' ' in kw]
        single_word_chats = [kw for kw in self.chat_keywords if ' ' not in kw]
        
        for keyword in multi_word_chats:
            if keyword in input_lower:
                chat_score += 2
        
        for keyword in single_word_chats:
            import re
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, input_lower):
                chat_score += 1
        
        # Check for imperative verbs at start (action words)
        imperative_verbs = ['open', 'close', 'get', 'find', 'show', 'make', 
                           'create', 'delete', 'run', 'execute', 'click', 'type',
                           'search', 'check', 'verify', 'launch', 'start', 'stop',
                           'write', 'clear', 'input', 'paste']
        words = input_lower.split()
        if words and words[0] in imperative_verbs:
            agent_score += 3  # Higher weight for clear command structure
        
        # Check for "i want" pattern (indicates request)
        if input_lower.startswith('i want') or input_lower.startswith('i need'):
            agent_score += 2
        
        # Check for question patterns at start
        question_words = ['what', 'who', 'when', 'where', 'why', 'how', 'is', 'are', 'does', 'do']
        if words and words[0] in question_words:
            # But not if it's about time/battery/system info (those are agent tasks)
            system_info_words = ['time', 'battery', 'volume', 'brightness', 'network', 'wifi']
            if any(word in input_lower for word in system_info_words):
                agent_score += 2
            else:
                chat_score += 1
        
        # Calculate confidence
        total = agent_score + chat_score
        if total == 0:
            # Default to agent for ambiguous input (safer for task execution)
            return {
                'mode': 'agent',
                'confidence': 0.6,
                'reasoning': 'No strong indicators, defaulting to agent mode for safety',
                'requires_action': True
            }
        
        # Lower threshold for agent mode - prefer executing over chatting
        if agent_score >= chat_score:
            confidence = min(0.5 + (agent_score - chat_score) * 0.15 + 0.2, 0.98)
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
