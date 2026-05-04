"""
Reflector - Outcome analyzer and learning system.
Analyzes completed tasks to extract lessons and improve future performance.

MUST run after every completed task.
Extracts learnings: what_worked, what_failed, time_taken, 
                   user_correction_needed, pattern_to_remember
Feeds learnings directly into memory/semantic.py and memory/procedural.py
NEVER slows down response to user — runs in background thread
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import threading
import json


class ReflectionResult:
    """Result of a reflection."""
    
    def __init__(
        self,
        what_worked: List[str] = None,
        what_failed: List[str] = None,
        time_taken: float = 0.0,
        user_correction_needed: bool = False,
        pattern_to_remember: str = None,
        lessons_learned: List[str] = None
    ):
        self.what_worked = what_worked or []
        self.what_failed = what_failed or []
        self.time_taken = time_taken
        self.user_correction_needed = user_correction_needed
        self.pattern_to_remember = pattern_to_remember
        self.lessons_learned = lessons_learned or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'what_worked': self.what_worked,
            'what_failed': self.what_failed,
            'time_taken': self.time_taken,
            'user_correction_needed': self.user_correction_needed,
            'pattern_to_remember': self.pattern_to_remember,
            'lessons_learned': self.lessons_learned
        }


class Reflector:
    """
    Analyzes task outcomes to learn and improve.
    
    Runs AFTER every completed task.
    Extracts learnings and feeds them into memory systems.
    NEVER blocks user response - always runs in background thread.
    """
    
    def __init__(self, ollama_client=None, memory_manager=None,
                 semantic_memory=None, procedural_memory=None):
        """
        Initialize the reflector.
        
        Args:
            ollama_client: OllamaClient instance for reflection
            memory_manager: MemoryManager for storing lessons (legacy)
            semantic_memory: SemanticMemory instance for facts
            procedural_memory: ProceduralMemory instance for patterns
        """
        self.ollama_client = ollama_client
        self.memory_manager = memory_manager
        self.semantic_memory = semantic_memory
        self.procedural_memory = procedural_memory
        self.reflection_history = []
        self._background_threads = []
    
    def set_client(self, client) -> None:
        """Set the Ollama client."""
        self.ollama_client = client
    
    def set_memory_manager(self, manager) -> None:
        """Set the memory manager (legacy)."""
        self.memory_manager = manager
    
    def set_semantic_memory(self, memory) -> None:
        """Set semantic memory instance."""
        self.semantic_memory = memory
    
    def set_procedural_memory(self, memory) -> None:
        """Set procedural memory instance."""
        self.procedural_memory = memory
    
    def reflect(self, goal: str, plan: Dict[str, Any],
                results: List[Dict[str, Any]], 
                final_outcome: str,
                start_time: datetime = None,
                end_time: datetime = None,
                user_correction: bool = False,
                blocking: bool = False) -> Optional[ReflectionResult]:
        """
        Reflect on a completed task.
        
        MUST run after every completed task.
        By default runs in background thread to NOT slow down user response.
        
        Args:
            goal: Original goal
            plan: The plan that was executed
            results: Results from each step
            final_outcome: Final outcome description
            start_time: When execution started
            end_time: When execution ended
            user_correction: Whether user had to correct something
            blocking: If True, wait for completion (NOT recommended)
            
        Returns:
            ReflectionResult if blocking=True, None otherwise (runs async)
        """
        # Calculate time taken
        time_taken = 0.0
        if start_time and end_time:
            time_taken = (end_time - start_time).total_seconds()
        elif isinstance(plan, dict):
            # Try to get duration from plan
            time_taken = plan.get('estimated_duration', 0)
            if isinstance(time_taken, str):
                # Parse duration string like "2 minutes"
                try:
                    parts = time_taken.split()
                    if len(parts) >= 2:
                        value = float(parts[0])
                        unit = parts[1].lower()
                        if 'minute' in unit:
                            time_taken = value * 60
                        elif 'hour' in unit:
                            time_taken = value * 3600
                        else:
                            time_taken = value
                except:
                    time_taken = 0.0
        
        # Create reflection task
        def do_reflect():
            # Analyze results
            analysis = self._analyze_results(results)
            
            # Generate reflection
            if self.ollama_client:
                llm_reflection = self._llm_reflect(goal, plan, results, final_outcome)
                
                # Merge with heuristic analysis
                reflection_result = ReflectionResult(
                    what_worked=list(set(
                        llm_reflection.get('went_well', []) + 
                        analysis.get('went_well', [])
                    )),
                    what_failed=list(set(
                        llm_reflection.get('went_wrong', []) +
                        analysis.get('went_wrong', [])
                    )),
                    time_taken=time_taken,
                    user_correction_needed=user_correction,
                    pattern_to_remember=self._extract_pattern(
                        goal, analysis, llm_reflection
                    ),
                    lessons_learned=list(set(
                        llm_reflection.get('lessons', []) + 
                        analysis.get('lessons', [])
                    ))
                )
            else:
                reflection_result = ReflectionResult(
                    what_worked=analysis.get('went_well', []),
                    what_failed=analysis.get('went_wrong', []),
                    time_taken=time_taken,
                    user_correction_needed=user_correction,
                    pattern_to_remember=self._extract_pattern(goal, analysis, {}),
                    lessons_learned=analysis.get('lessons', [])
                )
            
            # Feed learnings into memory systems
            self._feed_memories(reflection_result, goal, results)
            
            # Store in history
            self.reflection_history.append({
                'goal': goal,
                'reflection': reflection_result.to_dict(),
                'timestamp': datetime.now().isoformat()
            })
            
            # Keep history bounded
            if len(self.reflection_history) > 50:
                self.reflection_history = self.reflection_history[-50:]
            
            return reflection_result
        
        # Run in background thread by default to NOT slow down user response
        if not blocking:
            thread = threading.Thread(target=do_reflect, daemon=True)
            thread.start()
            self._background_threads.append(thread)
            # Clean up old threads
            self._background_threads = [
                t for t in self._background_threads if t.is_alive()
            ]
            return None
        else:
            return do_reflect()
    
    def _analyze_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Heuristic analysis of results."""
        went_well = []
        went_wrong = []
        lessons = []
        
        total_steps = len(results)
        successful_steps = sum(1 for r in results if r.get('success', False))
        
        success_rate = successful_steps / max(total_steps, 1)
        
        # Overall success assessment
        success = success_rate >= 0.8
        
        # Analyze each step
        tool_failures = {}
        error_patterns = {}
        
        for i, result in enumerate(results):
            tool_name = result.get('tool', result.get('tool_or_skill', 'unknown'))
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
                    lessons.append(
                        f"Tool '{tool}' failed {count} times - may need alternative approach"
                    )
        
        if error_patterns:
            for error, count in error_patterns.items():
                if count >= 2:
                    lessons.append(f"Same error occurred {count} times: {error[:50]}...")
        
        # Generate lessons based on common patterns
        if success_rate < 0.5:
            lessons.append("Consider breaking down complex tasks into smaller steps")
        
        if any('timeout' in str(r.get('error', '')).lower() for r in results):
            lessons.append("Some operations timed out - consider adding retry logic")
        
        if any('permission' in str(r.get('error', '')).lower() for r in results):
            lessons.append(
                "Permission errors encountered - verify access rights before operations"
            )
        
        if success_rate == 1.0 and total_steps > 3:
            lessons.append("Efficient execution - this approach works well for similar tasks")
        
        return {
            'success': success,
            'success_rate': success_rate,
            'went_well': went_well,
            'went_wrong': went_wrong,
            'lessons': lessons
        }
    
    def _llm_reflect(self, goal: str, plan: Dict[str, Any],
                     results: List[Dict[str, Any]], 
                     final_outcome: str) -> Dict[str, Any]:
        """Use LLM for deep reflection."""
        # Get steps from plan
        if isinstance(plan, dict):
            steps_data = plan.get('steps', [])
        else:
            steps_data = []
        
        plan_str = "\n".join([
            f"{i+1}. {s.get('tool_or_skill', s.get('tool', ''))}: {s.get('params', {})}"
            for i, s in enumerate(steps_data)
        ])
        
        results_str = "\n".join([
            f"{i+1}. {'✓' if r.get('success') else '✗'} {r.get('tool', r.get('tool_or_skill', ''))}: {r.get('output', r.get('error', ''))}"
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
- Are there any patterns worth remembering?

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
                
            )
            
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
    
    def _extract_pattern(self, goal: str, analysis: Dict[str, Any],
                         llm_reflection: Dict[str, Any]) -> Optional[str]:
        """Extract a memorable pattern from the reflection."""
        # Look for patterns in LLM reflection first
        patterns = llm_reflection.get('patterns', [])
        if patterns:
            return patterns[0]
        
        # Generate pattern from successful execution
        if analysis.get('success', False) and analysis.get('went_well'):
            went_well = analysis['went_well']
            if len(went_well) >= 2:
                # Create a summary pattern
                tools_used = []
                for item in went_well[:3]:
                    # Extract tool name from "Step X (tool_name) completed successfully"
                    if '(' in item and ')' in item:
                        tool = item.split('(')[1].split(')')[0]
                        tools_used.append(tool)
                
                if tools_used:
                    return f"For {goal[:50]}...: use sequence [{', '.join(tools_used)}]"
        
        # Generate pattern from failures
        if analysis.get('went_wrong'):
            went_wrong = analysis['went_wrong']
            if went_wrong:
                # Extract lesson from first failure
                first_wrong = went_wrong[0]
                if 'failed' in first_wrong:
                    return f"Avoid: {first_wrong[:100]}"
        
        return None
    
    def _feed_memories(self, reflection: ReflectionResult, goal: str,
                       results: List[Dict[str, Any]]) -> None:
        """
        Feed learnings directly into memory systems.
        
        Writes to both:
        - memory/semantic.py for factual learnings
        - memory/procedural.py for action patterns
        """
        # Feed to semantic memory (facts about what worked/failed)
        if self.semantic_memory:
            # Store lessons as semantic facts
            for lesson in reflection.lessons_learned:
                if lesson:
                    self.semantic_memory.add_fact(
                        content=lesson,
                        category='lesson',
                        metadata={
                            'source_goal': goal[:100],
                            'timestamp': datetime.now().isoformat()
                        }
                    )
            
            # Store what worked
            for item in reflection.what_worked:
                if item:
                    self.semantic_memory.add_fact(
                        content=f"Successful approach: {item}",
                        category='success_pattern',
                        metadata={'source_goal': goal[:100]}
                    )
            
            # Store what failed
            for item in reflection.what_failed:
                if item:
                    self.semantic_memory.add_fact(
                        content=f"Failed approach: {item}",
                        category='failure_pattern',
                        metadata={'source_goal': goal[:100]}
                    )
        
        # Feed to procedural memory (action patterns)
        if self.procedural_memory and reflection.pattern_to_remember:
            # Extract tool sequence from results
            tool_sequence = []
            for result in results:
                tool_name = result.get('tool', result.get('tool_or_skill', ''))
                if tool_name and result.get('success', False):
                    tool_sequence.append({
                        'tool': tool_name,
                        'params': result.get('params', {})
                    })
            
            if tool_sequence:
                # Learn this as a procedural pattern
                pattern_name = f"learned_{goal[:30].replace(' ', '_').lower()}"
                self.procedural_memory.learn_pattern(
                    name=pattern_name,
                    steps=tool_sequence,
                    context={
                        'goal_pattern': goal[:100],
                        'success_rate': sum(1 for r in results if r.get('success')) / max(len(results), 1)
                    }
                )
        
        # Legacy support for memory_manager
        if self.memory_manager:
            lessons = reflection.lessons_learned
            
            for lesson in lessons:
                if lesson:
                    proc_name = f"lesson_{goal[:30].replace(' ', '_').lower()}"
                    
                    self.memory_manager.learn_procedure(
                        name=proc_name,
                        steps=[{'lesson': lesson}],
                        context=f"Learned from task: {goal}"
                    )
    
    def quick_reflect(self, success: bool, error: str = None,
                      time_taken: float = 0.0) -> ReflectionResult:
        """
        Quick reflection for simple operations.
        
        Args:
            success: Whether the operation succeeded
            error: Optional error message
            time_taken: Time taken for the operation
            
        Returns:
            Simple reflection result
        """
        if success:
            return ReflectionResult(
                what_worked=['Operation completed successfully'],
                time_taken=time_taken,
                user_correction_needed=False
            )
        else:
            return ReflectionResult(
                what_failed=[f'Operation failed: {error}'],
                time_taken=time_taken,
                user_correction_needed=True,
                lessons_learned=['Consider alternative approach']
            )
    
    def get_reflection_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent reflection history."""
        return self.reflection_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear reflection history."""
        self.reflection_history = []


# Singleton instance
_reflector_instance = None

def get_reflector(ollama_client=None, memory_manager=None,
                  semantic_memory=None, procedural_memory=None) -> Reflector:
    """Get the singleton Reflector instance."""
    global _reflector_instance
    if _reflector_instance is None:
        _reflector_instance = Reflector(
            ollama_client, memory_manager,
            semantic_memory=semantic_memory,
            procedural_memory=procedural_memory
        )
    else:
        if ollama_client:
            _reflector_instance.set_client(ollama_client)
        if memory_manager:
            _reflector_instance.set_memory_manager(memory_manager)
        if semantic_memory:
            _reflector_instance.set_semantic_memory(semantic_memory)
        if procedural_memory:
            _reflector_instance.set_procedural_memory(procedural_memory)
    return _reflector_instance
