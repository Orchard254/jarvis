"""
Adaptive Intent Scorer for JARVIS
Continuously learns and scores user intents to determine chat vs agent mode
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class AdaptiveIntentScorer:
    """
    Scores user intents on a 0-100 scale to determine execution mode:
    - 85-100: Auto-execute (agent mode)
    - 60-84: Show plan + quick confirm
    - 0-59: Chat response only
    
    Learns from user interactions to improve over time.
    """
    
    # Base agentic verbs that strongly indicate action intent
    AGENTIC_VERBS = {
        'open', 'close', 'kill', 'start', 'stop', 'run', 'execute',
        'write', 'type', 'input', 'delete', 'clear', 'remove', 'copy',
        'move', 'rename', 'create', 'save', 'send', 'click', 'press',
        'focus', 'switch', 'minimize', 'maximize', 'resize', 'scroll',
        'search', 'find', 'download', 'upload', 'install', 'uninstall',
        'enable', 'disable', 'set', 'change', 'update', 'configure'
    }
    
    # Chat indicators that suggest conversation
    CHAT_INDICATORS = {
        'hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening',
        'how are you', 'what can you do', 'who are you', 'tell me', 'explain',
        'what is', 'what are', 'how does', 'why', 'when', 'where', 'which',
        'define', 'describe', 'summarize', 'list', 'show me how', 'can you',
        'could you', 'would you', 'please tell', 'i want to know', 'what about'
    }
    
    # Explicit trigger phrases for agent mode
    EXPLICIT_TRIGGERS = [
        'do this:', 'execute:', 'run:', 'perform:', 'action:',
        'just do it', 'go ahead', 'proceed', 'do it', 'make it happen'
    ]
    
    def __init__(self, memory_path: str = "jarvis_data/intent_memory.json"):
        self.memory_path = memory_path
        self.learned_phrases: Dict[str, float] = {}  # phrase -> confidence score
        self.user_preferences: Dict[str, any] = {}
        self.interaction_history: List[Dict] = []
        self.context_window: List[str] = []  # Recent commands
        self.max_context_size = 10
        
        # Load persisted memory
        self._load_memory()
        
    def _load_memory(self):
        """Load learned patterns from disk"""
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, 'r') as f:
                    data = json.load(f)
                    self.learned_phrases = data.get('learned_phrases', {})
                    self.user_preferences = data.get('user_preferences', {})
                    self.interaction_history = data.get('interaction_history', [])[-100:]  # Keep last 100
                logger.info(f"Loaded intent memory: {len(self.learned_phrases)} learned phrases")
            except Exception as e:
                logger.error(f"Failed to load intent memory: {e}")
                self.learned_phrases = {}
    
    def _save_memory(self):
        """Persist learned patterns to disk"""
        try:
            os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
            data = {
                'learned_phrases': self.learned_phrases,
                'user_preferences': self.user_preferences,
                'interaction_history': self.interaction_history[-100:]
            }
            with open(self.memory_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save intent memory: {e}")
    
    def score_intent(self, user_input: str, context: Optional[Dict] = None) -> Tuple[int, str]:
        user_input_lower = user_input.lower().strip()
        reasons = []

        # 1. Explicit triggers — immediate return
        for trigger in self.EXPLICIT_TRIGGERS:
            if trigger in user_input_lower:
                return 95, f"Explicit trigger: '{trigger}'"

        # 2. Determine if any agentic verb is present
        words = set(re.findall(r'\b\w+\b', user_input_lower))
        has_agentic_verb = bool(words & self.AGENTIC_VERBS)

        # 3. Chat block — only fires when there is NO agentic verb
        #    Fixes: 'write hello world' was blocked because 'hello' matched chat
        #    Now: 'hello' alone with no action verb = chat
        chat_score = self._check_chat_indicators_strict(user_input_lower, has_agentic_verb)
        if chat_score > 0 and not has_agentic_verb:
            return 20, f"Chat message — no action verb detected"

        # 4. Collect positive signals — take MAX not average
        #    Averaging was the bug: context score of 30 dragged 90+70+90 down to 65
        positive_scores = []

        learned_score = self._check_learned_phrases(user_input_lower)
        if learned_score > 0:
            positive_scores.append(learned_score * 0.9)
            reasons.append(f"Learned pattern ({int(learned_score * 0.9)})")

        verb_score = self._check_agentic_verbs(user_input_lower)
        if verb_score > 0:
            positive_scores.append(verb_score)
            reasons.append(f"Agentic verb ({int(verb_score)})")

        sim_score = self._check_similarity_to_executed(user_input_lower)
        if sim_score > 0:
            positive_scores.append(sim_score)
            reasons.append(f"Similar to past commands ({sim_score:.0f})")

        # 5. Context is a small flat boost — never a drag
        #    Old code added context score of 30 into the average which HURT the score
        #    New code: context only adds +5 boost if strongly relevant, never hurts
        if positive_scores:
            ctx_score = self._check_context(user_input_lower, context)
            if ctx_score >= 40:
                positive_scores[0] = positive_scores[0] + 5  # tiny boost only

        # 6. Final = MAX of all positive signals
        if not positive_scores:
            base = self._base_command_score(user_input_lower)
            return base, "Base command analysis"

        final_score = int(max(positive_scores))
        final_score = max(0, min(100, final_score))
        return final_score, "; ".join(reasons)
    
    def _check_learned_phrases(self, user_input: str) -> float:
        """Check against learned phrase database"""
        best_match = 0.0
        
        for phrase, confidence in self.learned_phrases.items():
            # Exact match
            if phrase == user_input:
                return confidence
            
            # Partial match
            similarity = SequenceMatcher(None, phrase, user_input).ratio()
            if similarity > 0.7:
                match_score = confidence * similarity
                best_match = max(best_match, match_score)
        
        return best_match
    
    def _check_agentic_verbs(self, user_input: str) -> float:
        """Score based on presence of agentic verbs"""
        words = re.findall(r'\b\w+\b', user_input)
        found_verbs = set(words) & self.AGENTIC_VERBS
        
        if not found_verbs:
            return 0
        
        # More verbs = higher confidence
        verb_count = len(found_verbs)
        base_score = 60 + (verb_count * 10)  # 60-90 range
        return min(90, base_score)
    
    def _check_chat_indicators_strict(self, user_input: str, has_agentic_verb: bool) -> float:
        """
        Only returns a chat score when input is genuinely conversational.
        Does NOT match 'hello' inside 'hello world' or 'write hello'.
        """
        words = re.findall(r'\b\w+\b', user_input)
        first_word = words[0] if words else ''

        # Pure greetings — first word only, short sentence, no action verb
        pure_greetings = {'hello', 'hi', 'hey', 'howdy', 'greetings'}
        if first_word in pure_greetings and len(words) <= 5 and not has_agentic_verb:
            return 80

        # Time-of-day greetings
        time_greetings = ['good morning', 'good afternoon', 'good evening', 'good night']
        for g in time_greetings:
            if user_input.startswith(g) and not has_agentic_verb:
                return 80

        # Conversational question openers — only without action verbs
        question_starters = [
            'how are you', 'what can you do', 'who are you', 'tell me about',
            'what is ', 'what are ', 'how does ', 'why do', 'when did',
            'can you explain', 'could you explain', 'do you know',
            'i want to know', 'what about'
        ]
        if not has_agentic_verb:
            for q in question_starters:
                if q in user_input:
                    return 80

        # Questions — only without action verb
        if user_input.endswith('?') and not has_agentic_verb:
            return 70

        return 0

    def _check_chat_indicators(self, user_input: str) -> float:
        words = set(re.findall(r'\b\w+\b', user_input))
        has_verb = bool(words & self.AGENTIC_VERBS)
        return self._check_chat_indicators_strict(user_input, has_verb)
    
    def _check_context(self, user_input: str, context: Optional[Dict]) -> float:
        """Score based on recent context"""
        if not context:
            return 0
        
        score = 0
        
        # If an app was just opened/used, related commands are more likely agentic
        active_app = context.get('active_app')
        if active_app:
            app_keywords = {
                'notepad': ['write', 'type', 'delete', 'clear', 'save', 'open'],
                'browser': ['open', 'navigate', 'search', 'click', 'scroll'],
                'cmd': ['run', 'execute', 'type', 'command'],
            }
            
            app_words = app_keywords.get(active_app.lower(), [])
            input_words = set(re.findall(r'\b\w+\b', user_input))
            
            if any(word in input_words for word in app_words):
                score += 40
        
        # Recent command sequence suggests continuation
        if self.context_window:
            last_cmd = self.context_window[-1]
            # If last command was executed, similar follow-up likely agentic
            similarity = SequenceMatcher(None, last_cmd, user_input).ratio()
            if similarity > 0.5:
                score += 30
        
        return min(score, 70)
    
    def _check_similarity_to_executed(self, user_input: str) -> float:
        """Check similarity to previously executed commands"""
        executed_commands = [
            h['command'] for h in self.interaction_history 
            if h.get('executed', False)
        ]
        
        best_similarity = 0
        for cmd in executed_commands:
            similarity = SequenceMatcher(None, cmd, user_input).ratio()
            best_similarity = max(best_similarity, similarity)
        
        if best_similarity > 0.6:
            return 60 + (best_similarity * 30)  # 60-90 range
        
        return 0
    
    def _base_command_score(self, user_input: str) -> int:
        """Base scoring when no strong signals found"""
        # Short imperative sentences often commands
        words = user_input.split()
        
        if len(words) <= 4 and words[0] in self.AGENTIC_VERBS:
            return 75
        
        if len(words) <= 3:
            return 65
        
        return 50
    
    def learn_from_interaction(self, command: str, executed: bool, 
                                user_feedback: Optional[str] = None):
        """
        Learn from interaction outcome
        
        Args:
            command: The user's command
            executed: Whether the command was executed as agent action
            user_feedback: Optional feedback like "why didn't you do it?"
        """
        command_lower = command.lower().strip()
        
        # Add to context window
        self.context_window.append(command_lower)
        if len(self.context_window) > self.max_context_size:
            self.context_window.pop(0)
        
        # Record interaction
        interaction = {
            'timestamp': datetime.now().isoformat(),
            'command': command_lower,
            'executed': executed,
            'feedback': user_feedback
        }
        self.interaction_history.append(interaction)
        
        # Strong positive signal: executed successfully
        if executed:
            if command_lower in self.learned_phrases:
                # Increase confidence
                self.learned_phrases[command_lower] = min(100, 
                    self.learned_phrases[command_lower] + 5)
            else:
                # Add new learned phrase
                self.learned_phrases[command_lower] = 80
            
            logger.info(f"Learned agentic pattern: '{command_lower}' (confidence: 80+)")
        
        # Negative signal: should have executed but didn't
        elif user_feedback and any(x in user_feedback.lower() 
                                   for x in ['why didn\'t', 'why not', 'should have', 
                                            'just do it', 'do it']):
            if command_lower in self.learned_phrases:
                self.learned_phrases[command_lower] = min(100, 
                    self.learned_phrases[command_lower] + 15)  # Big boost
            else:
                self.learned_phrases[command_lower] = 85
            
            logger.warning(f"Corrected misclassification: '{command_lower}' boosted to 85")
        
        # Save to disk
        self._save_memory()
    
    def get_mode_recommendation(self, score: int) -> str:
        """Get recommended mode based on score"""
        if score >= 85:
            return "agent_auto"
        elif score >= 60:
            return "agent_confirm"
        else:
            return "chat"
    
    def analyze_and_score(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        """
        Full analysis with scoring and recommendation
        
        Returns dict with score, reasoning, mode, and confidence level
        """
        score, reasoning = self.score_intent(user_input, context)
        mode = self.get_mode_recommendation(score)
        
        confidence = "high" if score >= 80 else "medium" if score >= 60 else "low"
        
        return {
            'score': score,
            'reasoning': reasoning,
            'mode': mode,
            'confidence': confidence,
            'should_execute': mode != "chat"
        }
