"""
Self-Reflection Module for JARVIS Phase 5.
Enables the agent to critique its own output, identify improvements,
and iteratively refine its responses before presenting to users.
"""
import logging
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


class ReflectionCriterion(Enum):
    """Criteria for self-evaluation."""
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    CLARITY = "clarity"
    EFFICIENCY = "efficiency"
    SAFETY = "safety"
    RELEVANCE = "relevance"
    CONSISTENCY = "consistency"


@dataclass
class ReflectionScore:
    """Score for a single reflection criterion."""
    criterion: ReflectionCriterion
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    reasoning: str
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ReflectionResult:
    """Complete self-reflection result."""
    task_id: str
    original_output: str
    scores: List[ReflectionScore]
    overall_score: float
    needs_improvement: bool
    improvement_areas: List[str]
    revised_output: Optional[str] = None
    reflection_iterations: int = 1
    timestamp: float = field(default_factory=time.time)


class SelfReflector:
    """
    Enables autonomous self-reflection for the agent.
    
    The reflector critiques outputs against multiple criteria,
    identifies areas for improvement, and can trigger revision cycles.
    """
    
    def __init__(self, llm_client=None, max_reflection_iterations: int = 3,
                 min_improvement_threshold: float = 0.1):
        """
        Initialize the self-reflector.
        
        Args:
            llm_client: LLM client for generating critiques and revisions
            max_reflection_iterations: Maximum refinement cycles
            min_improvement_threshold: Minimum score improvement to continue iterating
        """
        self.llm_client = llm_client
        self.max_reflection_iterations = max_reflection_iterations
        self.min_improvement_threshold = min_improvement_threshold
        self._reflection_history: Dict[str, List[ReflectionResult]] = {}
        self._enabled_criteria = set(ReflectionCriterion)
        
        logger.info("SelfReflector initialized")
    
    def enable_criterion(self, criterion: ReflectionCriterion):
        """Enable a specific reflection criterion."""
        self._enabled_criteria.add(criterion)
        logger.debug(f"Enabled reflection criterion: {criterion.value}")
    
    def disable_criterion(self, criterion: ReflectionCriterion):
        """Disable a specific reflection criterion."""
        self._enabled_criteria.discard(criterion)
        logger.debug(f"Disabled reflection criterion: {criterion.value}")
    
    def reflect(self, task_id: str, output: str, context: Optional[Dict] = None,
                user_intent: Optional[str] = None) -> ReflectionResult:
        """
        Perform self-reflection on an output.
        
        Args:
            task_id: Unique task identifier
            output: The agent's generated output to critique
            context: Additional context about the task
            user_intent: Original user intent/query
            
        Returns:
            ReflectionResult with scores and potential revisions
        """
        logger.info(f"Starting self-reflection for task {task_id}")
        
        if task_id not in self._reflection_history:
            self._reflection_history[task_id] = []
        
        current_output = output
        best_result = None
        prev_overall_score = 0.0
        
        for iteration in range(1, self.max_reflection_iterations + 1):
            # Score the current output
            scores = self._score_output(current_output, context, user_intent)
            overall_score = sum(s.score * s.confidence for s in scores) / len(scores) if scores else 0.0
            
            # Identify improvement areas
            improvement_areas = [
                s.criterion.value for s in scores 
                if s.score < 0.7 and s.confidence > 0.5
            ]
            
            needs_improvement = overall_score < 0.8 and len(improvement_areas) > 0
            
            result = ReflectionResult(
                task_id=task_id,
                original_output=output if iteration == 1 else current_output,
                scores=scores,
                overall_score=overall_score,
                needs_improvement=needs_improvement,
                improvement_areas=improvement_areas,
                reflection_iterations=iteration
            )
            
            # Track best result
            if best_result is None or overall_score > best_result.overall_score:
                best_result = result
            
            logger.info(f"Reflection iteration {iteration}: score={overall_score:.2f}, "
                       f"improvements={improvement_areas}")
            
            if not needs_improvement:
                logger.info(f"Self-reflection complete for {task_id}: score={overall_score:.2f}")
                break
            
            # Attempt revision if we have an LLM client
            if self.llm_client and iteration < self.max_reflection_iterations:
                revised = self._generate_revision(
                    current_output, scores, context, user_intent
                )
                
                if revised and revised != current_output:
                    # Check if revision actually improves things
                    new_scores = self._score_output(revised, context, user_intent)
                    new_overall = sum(s.score * s.confidence for s in new_scores) / len(new_scores)
                    
                    if new_overall > overall_score + self.min_improvement_threshold:
                        logger.info(f"Revision improved score from {overall_score:.2f} to {new_overall:.2f}")
                        current_output = revised
                        prev_overall_score = overall_score
                        continue
                    else:
                        logger.info(f"Revision did not meet improvement threshold")
                        break
            
            # No further improvement possible
            break
        
        # Store result
        self._reflection_history[task_id].append(best_result)
        
        # Set revised output if different from original
        if best_result and current_output != output:
            best_result.revised_output = current_output
        
        return best_result
    
    def _score_output(self, output: str, context: Optional[Dict],
                      user_intent: Optional[str]) -> List[ReflectionScore]:
        """Score output against enabled criteria using LLM or heuristic fallback."""
        # Try LLM-based scoring first
        llm_scores = self._llm_score_output(output, context, user_intent)
        if llm_scores:
            return llm_scores

        # Heuristic fallback
        scores = []
        for criterion in self._enabled_criteria:
            score, confidence, reasoning, suggestions = self._heuristic_evaluate(
                criterion, output, context, user_intent
            )
            scores.append(ReflectionScore(
                criterion=criterion, score=score, confidence=confidence,
                reasoning=reasoning, suggestions=suggestions
            ))
        return scores

    def _llm_score_output(self, output: str, context: Optional[Dict],
                          user_intent: Optional[str]) -> Optional[List[ReflectionScore]]:
        """Use the LLM to evaluate output quality. Returns None on failure."""
        try:
            from brain.ollama_client import chat
        except ImportError:
            return None

        criteria_names = [c.value for c in self._enabled_criteria]
        prompt = (
            "You are a quality evaluator. Score the following agent output on each criterion.\n"
            f"User intent: {user_intent or 'unknown'}\n"
            f"Criteria: {', '.join(criteria_names)}\n\n"
            f"Agent output:\n{output[:2000]}\n\n"
            "Respond with ONLY valid JSON — an array of objects, one per criterion:\n"
            '[{"criterion": "...", "score": 0.0-1.0, "reasoning": "...", "suggestions": ["..."]}]'
        )
        try:
            result = chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, max_retries=1,
            )
            import json as _json
            text = result.get("content", "")
            # Extract JSON array from response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                return None
            parsed = _json.loads(text[start:end])
            scores = []
            for item in parsed:
                crit_name = item.get("criterion", "")
                try:
                    criterion = ReflectionCriterion(crit_name)
                except ValueError:
                    continue
                scores.append(ReflectionScore(
                    criterion=criterion,
                    score=max(0.0, min(1.0, float(item.get("score", 0.5)))),
                    confidence=0.85,
                    reasoning=str(item.get("reasoning", "")),
                    suggestions=item.get("suggestions", []),
                ))
            return scores if scores else None
        except Exception as e:
            logger.debug(f"LLM reflection scoring failed: {e}")
            return None

    def _heuristic_evaluate(self, criterion: ReflectionCriterion, output: str,
                            context: Optional[Dict], user_intent: Optional[str]
                            ) -> Tuple[float, float, str, List[str]]:
        """Heuristic fallback scoring when LLM is unavailable."""
        suggestions = []

        if criterion == ReflectionCriterion.ACCURACY:
            uncertainty_phrases = ["might", "could be", "possibly", "i think", "perhaps"]
            count = sum(1 for phrase in uncertainty_phrases if phrase.lower() in output.lower())
            score = max(0.5, 1.0 - (count * 0.1))
            return score, 0.4, f"Found {count} uncertainty markers", \
                ["Reduce hedging language"] if count > 2 else []

        elif criterion == ReflectionCriterion.COMPLETENESS:
            word_count = len(output.split())
            has_structure = any(m in output for m in ["**", "##", "-", "1.", "```"])
            score = min(1.0, word_count / 100) * (1.2 if has_structure else 1.0)
            return min(score, 1.0), 0.4, f"{word_count} words", \
                ["Consider expanding with more detail"] if word_count < 50 else []

        elif criterion == ReflectionCriterion.CLARITY:
            sentences = output.replace('!', '.').replace('?', '.').split('.')
            avg_len = sum(len(s.split()) for s in sentences if s.strip()) / max(len(sentences), 1)
            score = max(0.5, 1.0 - max(0, (avg_len - 20) * 0.02))
            return score, 0.4, f"Avg sentence length: {avg_len:.1f} words", \
                ["Break down long sentences"] if avg_len > 25 else []

        elif criterion == ReflectionCriterion.EFFICIENCY:
            words = output.lower().split()
            unique_ratio = len(set(words)) / max(len(words), 1)
            return min(1.0, unique_ratio + 0.2), 0.3, f"Unique word ratio: {unique_ratio:.2f}", \
                ["Reduce repetition"] if unique_ratio < 0.5 else []

        elif criterion == ReflectionCriterion.SAFETY:
            risky = [p for p in ["delete", "drop", "rm -rf", "sudo", "password", "secret"]
                     if p in output.lower()]
            return (0.3 if risky else 1.0), 0.6, \
                f"Risky patterns: {risky}" if risky else "No safety concerns", \
                ["Review dangerous operations"] if risky else []

        elif criterion == ReflectionCriterion.RELEVANCE:
            if user_intent:
                intent_words = set(user_intent.lower().split())
                output_words = set(output.lower().split())
                overlap = len(intent_words & output_words) / max(len(intent_words), 1)
                return min(1.0, overlap * 2 + 0.3), 0.4, f"Keyword overlap: {overlap:.2f}", \
                    ["Address user's query more directly"] if overlap < 0.3 else []
            return 0.7, 0.3, "No user intent provided", []

        elif criterion == ReflectionCriterion.CONSISTENCY:
            count = sum(1 for c in ["however", "but", "although", "on the other hand"]
                        if c.lower() in output.lower())
            score = 0.9 if 0 < count < 5 else (0.6 if count >= 5 else 0.7)
            return score, 0.3, f"{count} contrast markers", \
                ["Review for contradictions"] if count >= 5 else []

        return 0.5, 0.2, "Unknown criterion", []
    
    def _generate_revision(self, output: str, scores: List[ReflectionScore],
                           context: Optional[Dict], user_intent: Optional[str]) -> Optional[str]:
        """Generate a revised version using the LLM based on reflection scores."""
        all_suggestions = [s for score in scores for s in score.suggestions]
        if not all_suggestions:
            return None

        improvement_areas = ", ".join(set(s.criterion.value for s in scores if s.suggestions))
        prompt = (
            f"Revise this agent output to fix these issues:\n"
            f"{chr(10).join('- ' + s for s in all_suggestions)}\n\n"
            f"Focus areas: {improvement_areas}\n\n"
            f"Original output:\n{output}\n\n"
            f"Provide ONLY the revised output, nothing else."
        )
        try:
            from brain.ollama_client import chat
            result = chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_retries=1,
            )
            revised = result.get("content", "").strip()
            return revised if revised and revised != output else None
        except Exception as e:
            logger.debug(f"Revision generation failed: {e}")
            return None
    
    def get_reflection_history(self, task_id: Optional[str] = None) -> Dict[str, List[ReflectionResult]]:
        """Get reflection history, optionally filtered by task_id."""
        if task_id:
            return {task_id: self._reflection_history.get(task_id, [])}
        return self._reflection_history.copy()
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all reflections."""
        all_results = []
        for results in self._reflection_history.values():
            all_results.extend(results)
        
        if not all_results:
            return {"total_reflections": 0}
        
        avg_score = sum(r.overall_score for r in all_results) / len(all_results)
        avg_iterations = sum(r.reflection_iterations for r in all_results) / len(all_results)
        revisions_made = sum(1 for r in all_results if r.revised_output is not None)
        
        return {
            "total_reflections": len(all_results),
            "average_score": avg_score,
            "average_iterations": avg_iterations,
            "revision_rate": revisions_made / len(all_results),
            "most_common_improvements": self._get_common_improvement_areas(all_results)
        }
    
    def _get_common_improvement_areas(self, results: List[ReflectionResult]) -> List[str]:
        """Find most common improvement areas."""
        area_counts = {}
        for result in results:
            for area in result.improvement_areas:
                area_counts[area] = area_counts.get(area, 0) + 1
        
        sorted_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)
        return [area for area, _ in sorted_areas[:5]]


# Singleton instance
self_reflector = SelfReflector()


def reflect_output(task_id: str, output: str, context: Optional[Dict] = None,
                   user_intent: Optional[str] = None) -> ReflectionResult:
    """Convenience function to reflect on output using the singleton."""
    return self_reflector.reflect(task_id, output, context, user_intent)
