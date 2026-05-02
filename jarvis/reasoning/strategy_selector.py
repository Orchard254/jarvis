"""
Strategy Selector - Task classifier and routing system.
Classifies tasks into complexity levels and determines execution strategy.

Classification categories:
- trivial -> single tool, no planning, no critic
- simple -> 1-3 tools, no planning, critic only  
- complex -> 4+ tools or multi-step, full planning + critic
- strategic -> long-running goal, planning + critic + goal tracking across sessions

Classification is based on:
- Number of verbs in the request
- Presence of sequential words: then, after, next, finally
- Presence of conditional words: if, when, unless
- Whether the task requires verifying a result
"""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass


class TaskComplexity(Enum):
    """Task complexity levels."""
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    COMPLEX = "complex"
    STRATEGIC = "strategic"


@dataclass
class ClassificationResult:
    """Result of task classification."""
    complexity: TaskComplexity
    verb_count: int
    has_sequential: bool
    has_conditional: bool
    requires_verification: bool
    estimated_tools: int
    reasoning: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'complexity': self.complexity.value,
            'verb_count': self.verb_count,
            'has_sequential': self.has_sequential,
            'has_conditional': self.has_conditional,
            'requires_verification': self.requires_verification,
            'estimated_tools': self.estimated_tools,
            'reasoning': self.reasoning
        }


class StrategySelector:
    """
    Classifies tasks and determines execution strategy.
    
    Classification rules:
    - trivial: 1 verb, no sequencing, no conditionals, no verification
    - simple: 2-3 verbs OR has sequencing (but < 4 total actions)
    - complex: 4+ verbs OR has conditionals OR requires verification
    - strategic: contains session-spanning keywords OR explicit long-term goal
    """
    
    ACTION_VERBS = [
        'open', 'close', 'create', 'delete', 'move', 'copy', 'rename',
        'read', 'write', 'save', 'load', 'download', 'upload',
        'run', 'execute', 'launch', 'start', 'stop', 'kill', 'restart',
        'install', 'uninstall', 'configure', 'setup', 'update',
        'find', 'search', 'locate', 'list', 'show', 'display',
        'send', 'receive', 'email', 'message', 'notify', 'alert',
        'verify', 'check', 'confirm', 'validate', 'test', 'ensure',
        'extract', 'parse', 'analyze', 'process', 'transform',
        'compress', 'decompress', 'encrypt', 'decrypt',
        'navigate', 'browse', 'visit', 'go', 'switch',
        'type', 'press', 'click', 'select', 'scroll'
    ]
    
    SEQUENTIAL_WORDS = [
        'then', 'after', 'next', 'finally', 'first', 'second', 'third',
        'before', 'once', 'when done', 'after that', 'subsequently',
        'in order', 'step by step', 'one by one', 'sequentially'
    ]
    
    CONDITIONAL_WORDS = [
        'if', 'when', 'unless', 'otherwise', 'else', 'in case',
        'provided', 'assuming', 'whether', 'depending on',
        'only if', 'as long as', 'so that'
    ]
    
    VERIFICATION_WORDS = [
        'verify', 'check', 'confirm', 'make sure', 'ensure',
        'validate', 'test', 'see if', 'find out if',
        'double-check', 'prove', 'demonstrate'
    ]
    
    STRATEGIC_WORDS = [
        'ongoing', 'continuous', 'monitor', 'track', 'watch',
        'daily', 'weekly', 'monthly', 'every day', 'regularly',
        'automate', 'routine', 'habit', 'workflow', 'pipeline',
        'project', 'goal', 'objective', 'mission', 'campaign',
        'across sessions', 'remember to', 'keep doing', 'maintain'
    ]
    
    def __init__(self, ollama_client=None):
        self.ollama_client = ollama_client
        self.classification_history = []
    
    def set_client(self, client) -> None:
        self.ollama_client = client
    
    def classify(self, task_description: str, context: str = None) -> ClassificationResult:
        task_lower = task_description.lower()
        if context:
            task_lower += " " + context.lower()
        
        verb_count = self._count_verbs(task_lower)
        has_sequential = self._has_words(task_lower, self.SEQUENTIAL_WORDS)
        has_conditional = self._has_words(task_lower, self.CONDITIONAL_WORDS)
        requires_verification = self._has_words(task_lower, self.VERIFICATION_WORDS)
        has_strategic = self._has_words(task_lower, self.STRATEGIC_WORDS)
        estimated_tools = self._estimate_tools(task_lower, verb_count)
        
        complexity = self._determine_complexity(
            verb_count=verb_count, has_sequential=has_sequential,
            has_conditional=has_conditional, requires_verification=requires_verification,
            has_strategic=has_strategic, estimated_tools=estimated_tools
        )
        
        reasoning = self._generate_reasoning(
            complexity=complexity, verb_count=verb_count,
            has_sequential=has_sequential, has_conditional=has_conditional,
            requires_verification=requires_verification, has_strategic=has_strategic,
            estimated_tools=estimated_tools
        )
        
        result = ClassificationResult(
            complexity=complexity, verb_count=verb_count,
            has_sequential=has_sequential, has_conditional=has_conditional,
            requires_verification=requires_verification,
            estimated_tools=estimated_tools, reasoning=reasoning
        )
        
        self.classification_history.append({
            'task': task_description[:200],
            'classification': result.to_dict(),
            'timestamp': __import__('datetime').datetime.now().isoformat()
        })
        
        if len(self.classification_history) > 50:
            self.classification_history = self.classification_history[-50:]
        
        return result
    
    def _count_verbs(self, text: str) -> int:
        import re
        count = 0
        for verb in self.ACTION_VERBS:
            pattern = r'\b' + re.escape(verb) + r'\b'
            matches = re.findall(pattern, text)
            count += len(matches)
        return count
    
    def _has_words(self, text: str, word_list: List[str]) -> bool:
        for word in word_list:
            if word in text:
                return True
        return False
    
    def _estimate_tools(self, text: str, verb_count: int) -> int:
        estimate = verb_count
        for indicator in ['and', 'also', 'plus', 'additionally']:
            if indicator in text:
                estimate += 1
        return min(estimate, 20)
    
    def _determine_complexity(self, verb_count: int, has_sequential: bool,
                              has_conditional: bool, requires_verification: bool,
                              has_strategic: bool, estimated_tools: int) -> TaskComplexity:
        if has_strategic:
            return TaskComplexity.STRATEGIC
        if verb_count >= 4:
            return TaskComplexity.COMPLEX
        if has_conditional:
            return TaskComplexity.COMPLEX
        if requires_verification and verb_count >= 2:
            return TaskComplexity.COMPLEX
        if verb_count >= 2 and verb_count <= 3:
            return TaskComplexity.SIMPLE
        if has_sequential and verb_count >= 2:
            return TaskComplexity.SIMPLE
        if estimated_tools >= 2 and estimated_tools <= 3:
            return TaskComplexity.SIMPLE
        return TaskComplexity.TRIVIAL
    
    def _generate_reasoning(self, complexity: TaskComplexity, verb_count: int,
                           has_sequential: bool, has_conditional: bool,
                           requires_verification: bool, has_strategic: bool,
                           estimated_tools: int) -> str:
        reasons = []
        if has_strategic:
            reasons.append("Contains strategic/long-running indicators")
        if verb_count >= 4:
            reasons.append(f"High verb count ({verb_count}) indicates multiple operations")
        elif verb_count >= 2:
            reasons.append(f"Moderate verb count ({verb_count})")
        if has_conditional:
            reasons.append("Contains conditional logic requiring decision points")
        if has_sequential:
            reasons.append("Has sequential ordering indicating multi-step process")
        if requires_verification:
            reasons.append("Requires verification of results")
        if not reasons:
            reasons.append("Single straightforward operation")
        return f"Classified as {complexity.value}: " + "; ".join(reasons)
    
    def get_execution_strategy(self, complexity: TaskComplexity) -> Dict[str, Any]:
        strategies = {
            TaskComplexity.TRIVIAL: {
                'use_planner': False, 'use_critic': False,
                'parallel_allowed': True, 'max_retries': 1,
                'require_confirmation': False, 'track_in_history': False,
                'description': 'Direct execution - single tool call'
            },
            TaskComplexity.SIMPLE: {
                'use_planner': False, 'use_critic': True,
                'parallel_allowed': True, 'max_retries': 2,
                'require_confirmation': False, 'track_in_history': True,
                'description': 'Quick execution with critic validation'
            },
            TaskComplexity.COMPLEX: {
                'use_planner': True, 'use_critic': True,
                'parallel_allowed': True, 'max_retries': 2,
                'require_confirmation': True, 'track_in_history': True,
                'description': 'Full planning with critic review'
            },
            TaskComplexity.STRATEGIC: {
                'use_planner': True, 'use_critic': True,
                'parallel_allowed': False, 'max_retries': 3,
                'require_confirmation': True, 'track_in_history': True,
                'persist_state': True, 'cross_session_tracking': True,
                'description': 'Strategic execution with goal tracking across sessions'
            }
        }
        return strategies.get(complexity, strategies[TaskComplexity.SIMPLE])
    
    def should_use_planner(self, task_description: str) -> bool:
        result = self.classify(task_description)
        return result.complexity in [TaskComplexity.COMPLEX, TaskComplexity.STRATEGIC]
    
    def should_use_critic(self, task_description: str) -> bool:
        result = self.classify(task_description)
        return result.complexity in [
            TaskComplexity.SIMPLE, TaskComplexity.COMPLEX, TaskComplexity.STRATEGIC
        ]
    
    def llm_assisted_classify(self, task_description: str,
                              heuristic_result: ClassificationResult = None) -> ClassificationResult:
        if self.ollama_client is None:
            return heuristic_result or self.classify(task_description)
        
        prompt = f'''Classify this task by complexity:

Task: "{task_description}"

Categories: trivial, simple, complex, strategic

Respond in JSON format:
{{
    "complexity": "trivial/simple/complex/strategic",
    "verb_count": <number>,
    "estimated_tools": <number>,
    "has_sequential": true/false,
    "has_conditional": true/false,
    "requires_verification": true/false,
    "reasoning": "<brief explanation>"
}}'''
        
        try:
            response = self.ollama_client.chat(messages=[{'role': 'user', 'content': prompt}])
            import json
            llm_result = json.loads(response.get('content', '{}'))
            
            complexity_str = llm_result.get('complexity', 'simple')
            try:
                llm_complexity = TaskComplexity(complexity_str)
            except ValueError:
                llm_complexity = TaskComplexity.SIMPLE
            
            return ClassificationResult(
                complexity=llm_complexity,
                verb_count=llm_result.get('verb_count', 1),
                has_sequential=llm_result.get('has_sequential', False),
                has_conditional=llm_result.get('has_conditional', False),
                requires_verification=llm_result.get('requires_verification', False),
                estimated_tools=llm_result.get('estimated_tools', 1),
                reasoning=llm_result.get('reasoning', 'LLM classification')
            )
        except Exception:
            return heuristic_result or self.classify(task_description)
    
    def get_classification_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.classification_history[-limit:]
    
    def clear_history(self) -> None:
        self.classification_history = []


_selector_instance = None

def get_strategy_selector(ollama_client=None) -> StrategySelector:
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = StrategySelector(ollama_client)
    elif ollama_client:
        _selector_instance.set_client(ollama_client)
    return _selector_instance
