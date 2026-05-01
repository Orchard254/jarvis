"""
Reflector - Outcome analyzer and learning system.
Analyzes completed tasks to extract lessons and improve future performance.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class Reflector:
    """
    Analyzes task outcomes to learn and improve.
    Stores reflections for future reference.
    """
    
    def __init__(self, ollama_client=None, memory_manager=None):
        """
        Initialize the reflector.
        
        Args:
            ollama_client: OllamaClient instance for reflection
            memory_manager: MemoryManager for storing lessons
        """
        self.ollama_client = ollama_client
        self.memory_manager = memory_manager
        self.reflection_history = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def set_memory_manager(self, manager) -> None:
        """Set the memory manager."""
        self.memory_manager = manager
    
    def reflect(self, goal: str, plan: Dict[str, Any],
                results: List[Dict[str, Any]], 
                final_outcome: str) -> Dict[str, Any]:
        """
        Reflect on a completed task.
        
        Args:
            goal: Original goal
            plan: The plan that was executed
            results: Results from each step
            final_outcome: Final outcome description
            
        Returns:
            Dictionary with reflection results:
            {
                'success': bool,
                'lessons_learned': list of lessons,
                'what_went_well': list of successes,
                'what_went_wrong': list of failures,
                'improvements': list of improvement suggestions,
                'patterns': detected patterns,
                'store_in_memory': bool
            }
        """
        # Analyze results
        analysis = self._analyze_results(results)
        
        # Generate reflection
        if self.ollama_client:
            llm_reflection = self._llm_reflect(goal, plan, results, final_outcome)
            
            # Merge with heuristic analysis
            reflection = {
                'success': analysis['success'],
                'lessons_learned': list(set(
                    llm_reflection.get('lessons', []) + 
                    analysis.get('lessons', [])
                )),
                'what_went_well': list(set(
                    llm_reflection.get('went_well', []) +
                    analysis.get('went_well', [])
                )),
                'what_went_wrong': list(set(
                    llm_reflection.get('went_wrong', []) +
                    analysis.get('went_wrong', [])
                )),
                'improvements': llm_reflection.get('improvements', []),
                'patterns': analysis.get('patterns', []),
                'store_in_memory': len(analysis.get('lessons', [])) > 0
            }
        else:
            reflection = analysis
        
        # Store in memory if significant
        if reflection.get('store_in_memory') and self.memory_manager:
            self._store_lessons(reflection, goal)
        
        # Store in history
        self.reflection_history.append({
            'goal': goal,
            'reflection': reflection,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep history bounded
        if len(self.reflection_history) > 50:
            self.reflection_history = self.reflection_history[-50:]
        
        return reflection
    
    def _analyze_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Heuristic analysis of results."""
        went_well = []
        went_wrong = []
        lessons = []
        patterns = []
        
        total_steps = len(results)
        successful_steps = sum(1 for r in results if r.get('success', False))
        
        success_rate = successful_steps / max(total_steps, 1)
        
        # Overall success assessment
        success = success_rate >= 0.8
        
        # Analyze each step
        tool_failures = {}
        error_patterns = {}
        
        for i, result in enumerate(results):
            tool_name = result.get('tool', 'unknown')
            step_success = result.get('success', False)
            error = result.get('error', '')
            
            if step_success:
                went_well.append(f"Step {i+1} ({tool_name}) completed successfully")
            else:
                went_wrong.append(f"Step {i+1} ({tool_name}) failed: {error}")
                
                # Track tool failures
                tool_failures[tool_name] = tool_failures.get(tool_name, 0) + 1
                
                # Track error patterns
                if error:
                    error_key = error[:50]  # Normalize error
                    error_patterns[error_key] = error_patterns.get(error_key, 0) + 1
        
        # Detect patterns
        if tool_failures:
            for tool, count in tool_failures.items():
                if count >= 2:
                    patterns.append(f"Tool '{tool}' failed {count} times - may need alternative approach")
        
        if error_patterns:
            for error, count in error_patterns.items():
                if count >= 2:
                    patterns.append(f"Same error occurred {count} times: {error}")
        
        # Generate lessons
        if success_rate < 0.5:
            lessons.append("Consider breaking down complex tasks into smaller steps")
        
        if any('timeout' in str(r.get('error', '')).lower() for r in results):
            lessons.append("Some operations timed out - consider adding retry logic")
        
        if any('permission' in str(r.get('error', '')).lower() for r in results):
            lessons.append("Permission errors encountered - verify access rights before operations")
        
        if success_rate == 1.0 and total_steps > 3:
            lessons.append("Efficient execution - this approach works well for similar tasks")
        
        return {
            'success': success,
            'success_rate': success_rate,
            'went_well': went_well,
            'went_wrong': went_wrong,
            'lessons': lessons,
            'patterns': patterns
        }
    
    def _llm_reflect(self, goal: str, plan: Dict[str, Any],
                     results: List[Dict[str, Any]], 
                     final_outcome: str) -> Dict[str, Any]:
        """Use LLM for deep reflection."""
        plan_str = "\n".join([
            f"{i+1}. {s.get('tool', '')}: {s.get('params', {})}"
            for i, s in enumerate(plan.get('steps', []))
        ])
        
        results_str = "\n".join([
            f"{i+1}. {'✓' if r.get('success') else '✗'} {r.get('tool', '')}: {r.get('output', r.get('error', ''))}"
            for i, r in enumerate(results)
        ])
        
        prompt = f"""Reflect on this completed task.

Goal: {goal}

Plan:
{plan_str}

Results:
{results_str}

Final Outcome: {final_outcome}

Analyze what happened and provide insights:
- What went well?
- What went wrong?
- What lessons can be learned?
- How could this be done better next time?
- Are there any patterns worth noting?

Respond in JSON format:
{{
    "went_well": ["list of things that went well"],
    "went_wrong": ["list of things that went wrong"],
    "lessons": ["list of lessons learned"],
    "improvements": ["suggestions for improvement"],
    "patterns": ["detected patterns"]
}}

Be specific and actionable."""
        
        try:
            response = self.ollama_client.chat(
                messages=[{'role': 'user', 'content': prompt}],
                response_format='json'
            )
            
            import json
            content = response.get('content', '{}')
            return json.loads(content)
            
        except Exception as e:
            return {
                'went_well': [],
                'went_wrong': [],
                'lessons': [],
                'improvements': [],
                'patterns': []
            }
    
    def _store_lessons(self, reflection: Dict[str, Any], goal: str) -> None:
        """Store lessons in procedural memory."""
        if not self.memory_manager:
            return
        
        lessons = reflection.get('lessons_learned', [])
        
        for lesson in lessons:
            # Create a procedure name from the goal
            proc_name = f"lesson_{goal[:30].replace(' ', '_').lower()}"
            
            self.memory_manager.learn_procedure(
                name=proc_name,
                steps=[{'lesson': lesson}],
                context=f"Learned from task: {goal}"
            )
    
    def quick_reflect(self, success: bool, error: str = None) -> Dict[str, Any]:
        """
        Quick reflection for simple operations.
        
        Args:
            success: Whether the operation succeeded
            error: Optional error message
            
        Returns:
            Simple reflection dictionary
        """
        if success:
            return {
                'outcome': 'success',
                'action': 'continue',
                'note': 'Operation completed successfully'
            }
        else:
            return {
                'outcome': 'failure',
                'action': 'retry_or_alternative',
                'error': error,
                'note': 'Operation failed - consider alternative approach'
            }
    
    def get_reflection_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent reflection history."""
        return self.reflection_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear reflection history."""
        self.reflection_history = []


# Singleton instance
_reflector_instance = None

def get_reflector(ollama_client=None, memory_manager=None) -> Reflector:
    """Get the singleton Reflector instance."""
    global _reflector_instance
    if _reflector_instance is None:
        _reflector_instance = Reflector(ollama_client, memory_manager)
    else:
        if ollama_client:
            _reflector_instance.set_client(ollama_client)
        if memory_manager:
            _reflector_instance.set_memory_manager(memory_manager)
    return _reflector_instance
