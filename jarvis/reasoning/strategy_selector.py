"""
Strategy Selector - Picks reasoning depth based on task complexity.
Decides when to use simple execution vs full planning/critique/reflection cycle.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class StrategySelector:
    """
    Selects the appropriate reasoning strategy for each task.
    
    Strategies:
    - direct: Execute immediately (simple queries)
    - plan_only: Create and execute a plan (moderate tasks)
    - plan_and_review: Plan, critique, then execute (complex tasks)
    - full_cycle: Plan, review, execute, reflect (critical/learning tasks)
    """
    
    def __init__(self):
        """Initialize the strategy selector."""
        self.strategy_history = []
        
        # Complexity thresholds
        self.thresholds = {
            'direct_max_words': 10,
            'plan_min_words': 8,
            'review_min_complexity': 2,
            'reflect_min_steps': 3
        }
    
    def select_strategy(self, user_input: str, intent: Dict[str, Any] = None,
                        context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Select the best strategy for the given input.
        
        Args:
            user_input: User's request
            intent: Intent classification result (optional)
            context: Additional context (optional)
            
        Returns:
            Dictionary with strategy selection:
            {
                'strategy': str,
                'reasoning': str,
                'estimated_complexity': int 1-5,
                'requires_planning': bool,
                'requires_review': bool,
                'requires_reflection': bool
            }
        """
        # Analyze input characteristics
        analysis = self._analyze_input(user_input, intent, context)
        
        # Determine strategy
        strategy, reasoning = self._determine_strategy(analysis)
        
        result = {
            'strategy': strategy,
            'reasoning': reasoning,
            'estimated_complexity': analysis['complexity'],
            'requires_planning': strategy in ['plan_only', 'plan_and_review', 'full_cycle'],
            'requires_review': strategy in ['plan_and_review', 'full_cycle'],
            'requires_reflection': strategy == 'full_cycle'
        }
        
        # Store in history
        self.strategy_history.append({
            'input': user_input[:100],
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep history bounded
        if len(self.strategy_history) > 50:
            self.strategy_history = self.strategy_history[-50:]
        
        return result
    
    def _analyze_input(self, user_input: str, intent: Dict[str, Any] = None,
                       context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze input characteristics."""
        words = user_input.split()
        word_count = len(words)
        
        # Check for complexity indicators
        complexity_indicators = [
            'then', 'after', 'before', 'if', 'when', 'while',
            'make sure', 'verify', 'check', 'confirm',
            'all', 'every', 'each', 'multiple',
            'first', 'second', 'third', 'finally',
            'backup', 'save', 'copy', 'duplicate',
            'compare', 'analyze', 'optimize', 'improve'
        ]
        
        indicator_count = sum(
            1 for ind in complexity_indicators 
            if ind in user_input.lower()
        )
        
        # Check for action verbs (suggests agent mode)
        action_verbs = [
            'open', 'close', 'create', 'delete', 'move', 'copy',
            'run', 'execute', 'install', 'configure', 'set up',
            'find', 'search', 'download', 'upload', 'send'
        ]
        
        has_action = any(verb in user_input.lower() for verb in action_verbs)
        
        # Check for risk indicators
        risk_indicators = [
            'delete', 'remove', 'erase', 'destroy',
            'shutdown', 'restart', 'kill', 'terminate',
            'format', 'reset', 'overwrite'
        ]
        
        has_risk = any(ind in user_input.lower() for ind in risk_indicators)
        
        # Calculate complexity score (1-5)
        complexity = 1
        
        if word_count > 15:
            complexity += 1
        if word_count > 30:
            complexity += 1
        if indicator_count >= 2:
            complexity += 1
        if indicator_count >= 4:
            complexity += 1
        if has_risk:
            complexity = max(complexity, 3)
        
        complexity = min(complexity, 5)
        
        # Determine mode
        mode = 'agent' if has_action else 'chat'
        if intent and intent.get('mode') == 'agent':
            mode = 'agent'
        elif intent and intent.get('mode') == 'chat':
            mode = 'chat'
        
        return {
            'word_count': word_count,
            'indicator_count': indicator_count,
            'has_action': has_action,
            'has_risk': has_risk,
            'complexity': complexity,
            'mode': mode
        }
    
    def _determine_strategy(self, analysis: Dict[str, Any]) -> Tuple[str, str]:
        """Determine the best strategy based on analysis."""
        complexity = analysis['complexity']
        mode = analysis['mode']
        has_risk = analysis['has_risk']
        word_count = analysis['word_count']
        
        # Chat mode always uses direct strategy
        if mode == 'chat':
            return 'direct', 'Chat mode - no tool execution needed'
        
        # Very short inputs without risk -> direct
        if word_count <= 5 and not has_risk and complexity <= 2:
            return 'direct', 'Simple request - execute directly'
        
        # High risk -> always review
        if has_risk:
            return 'plan_and_review', 'Risky operation requires planning and review'
        
        # Complexity-based selection
        if complexity <= 2:
            return 'plan_only', 'Moderate task - create and execute plan'
        elif complexity <= 4:
            return 'plan_and_review', 'Complex task - plan should be reviewed'
        else:
            return 'full_cycle', 'Very complex task - full reasoning cycle recommended'
    
    def get_strategies(self) -> Dict[str, Dict[str, Any]]:
        """Get all available strategies with descriptions."""
        return {
            'direct': {
                'name': 'Direct Execution',
                'description': 'Execute tool calls immediately without planning',
                'use_when': 'Simple requests, chat mode, or single tool calls',
                'steps': ['Parse tool call', 'Validate', 'Execute', 'Return result']
            },
            'plan_only': {
                'name': 'Plan and Execute',
                'description': 'Create a plan then execute it',
                'use_when': 'Multi-step tasks with clear procedures',
                'steps': ['Generate plan', 'Execute steps', 'Return results']
            },
            'plan_and_review': {
                'name': 'Plan, Review, Execute',
                'description': 'Create plan, have critic review it, then execute',
                'use_when': 'Complex tasks or risky operations',
                'steps': ['Generate plan', 'Critic review', 'Refine if needed', 'Execute', 'Return results']
            },
            'full_cycle': {
                'name': 'Full Reasoning Cycle',
                'description': 'Complete plan-review-execute-reflect cycle',
                'use_when': 'Critical tasks, learning opportunities, or very complex goals',
                'steps': ['Generate plan', 'Critic review', 'Refine', 'Execute', 'Reflect', 'Store lessons']
            }
        }
    
    def adapt_thresholds(self, success_rate: float, strategy: str) -> None:
        """
        Adapt thresholds based on observed success rates.
        
        Args:
            success_rate: Recent success rate for the strategy
            strategy: The strategy used
        """
        # Simple adaptive logic
        if success_rate < 0.6:
            # Strategy is failing too often - be more conservative
            if strategy == 'direct':
                self.thresholds['direct_max_words'] = max(5, 
                    self.thresholds['direct_max_words'] - 1)
            elif strategy == 'plan_only':
                self.thresholds['review_min_complexity'] = max(1,
                    self.thresholds['review_min_complexity'] - 1)
        elif success_rate > 0.9:
            # Strategy is working well - can be more aggressive
            if strategy == 'plan_and_review':
                self.thresholds['review_min_complexity'] = min(5,
                    self.thresholds['review_min_complexity'] + 1)
    
    def get_strategy_history(self, limit: int = 20) -> list:
        """Get recent strategy selection history."""
        return self.strategy_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear strategy history."""
        self.strategy_history = []


# Singleton instance
_selector_instance = None

def get_strategy_selector() -> StrategySelector:
    """Get the singleton StrategySelector instance."""
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = StrategySelector()
    return _selector_instance
