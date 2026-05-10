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
        """
        Score output against enabled criteria.
        
        In production, this would use LLM-based evaluation.
        Here we use heuristic-based scoring as a placeholder.
        """
        scores = []
        
        for criterion in self._enabled_criteria:
            score, confidence, reasoning, suggestions = self._evaluate_criterion(
                criterion, output, context, user_intent
            )
            scores.append(ReflectionScore(
                criterion=criterion,
                score=score,
                confidence=confidence,
                reasoning=reasoning,
                suggestions=suggestions
            ))
        
        return scores
    
    def _evaluate_criterion(self, criterion: ReflectionCriterion, output: str,
                            context: Optional[Dict], user_intent: Optional[str]
                            ) -> Tuple[float, float, str, List[str]]:
        """
        Evaluate output against a single criterion.
        
        Returns: (score, confidence, reasoning, suggestions)
        """
        suggestions = []
        
        if criterion == ReflectionCriterion.ACCURACY:
            # Placeholder: check for uncertainty markers
            uncertainty_phrases = ["might", "could be", "possibly", "i think", "perhaps"]
            count = sum(1 for phrase in uncertainty_phrases if phrase.lower() in output.lower())
            score = max(0.5, 1.0 - (count * 0.1))
            confidence = 0.6
            reasoning = f"Found {count} uncertainty markers in output"
            if count > 2:
                suggestions.append("Reduce hedging language for more confident statements")
        
        elif criterion == ReflectionCriterion.COMPLETENESS:
            # Placeholder: check output length and structure
            word_count = len(output.split())
            has_structure = any(marker in output for marker in ["**", "##", "-", "1.", "```"])
            score = min(1.0, word_count / 100) * (1.2 if has_structure else 1.0)
            score = min(score, 1.0)
            confidence = 0.5
            reasoning = f"Output has {word_count} words, {'has' if has_structure else 'lacks'} structure"
            if word_count < 50:
                suggestions.append("Consider expanding with more detail")
            if not has_structure:
                suggestions.append("Add formatting (lists, headers, code blocks) for clarity")
        
        elif criterion == ReflectionCriterion.CLARITY:
            # Placeholder: check sentence complexity
            sentences = output.replace('!', '.').replace('?', '.').split('.')
            avg_length = sum(len(s.split()) for s in sentences if s.strip()) / max(len(sentences), 1)
            score = max(0.5, 1.0 - max(0, (avg_length - 20) * 0.02))
            confidence = 0.5
            reasoning = f"Average sentence length: {avg_length:.1f} words"
            if avg_length > 25:
                suggestions.append("Break down long sentences for better readability")
        
        elif criterion == ReflectionCriterion.EFFICIENCY:
            # Placeholder: check for redundancy
            words = output.lower().split()
            unique_ratio = len(set(words)) / max(len(words), 1)
            score = min(1.0, unique_ratio + 0.2)
            confidence = 0.4
            reasoning = f"Unique word ratio: {unique_ratio:.2f}"
            if unique_ratio < 0.5:
                suggestions.append("Reduce repetition of words and phrases")
        
        elif criterion == ReflectionCriterion.SAFETY:
            # Placeholder: basic safety check
            risky_patterns = ["delete", "drop", "rm -rf", "sudo", "password", "secret"]
            found_risky = [p for p in risky_patterns if p in output.lower()]
            score = 0.3 if found_risky else 1.0
            confidence = 0.7
            reasoning = f"{'Found risky patterns' if found_risky else 'No obvious safety concerns'}: {found_risky}"
            if found_risky:
                suggestions.append("Review potentially dangerous operations and add warnings")
        
        elif criterion == ReflectionCriterion.RELEVANCE:
            # Placeholder: check keyword overlap with user intent
            if user_intent:
                intent_words = set(user_intent.lower().split())
                output_words = set(output.lower().split())
                overlap = len(intent_words & output_words) / max(len(intent_words), 1)
                score = min(1.0, overlap * 2 + 0.3)
                confidence = 0.5
                reasoning = f"Keyword overlap with intent: {overlap:.2f}"
                if overlap < 0.3:
                    suggestions.append("Ensure response directly addresses user's query")
            else:
                score = 0.7
                confidence = 0.3
                reasoning = "No user intent provided for relevance comparison"
        
        elif criterion == ReflectionCriterion.CONSISTENCY:
            # Placeholder: check for contradictions
            contradictions = ["however", "but", "although", "on the other hand"]
            count = sum(1 for c in contradictions if c.lower() in output.lower())
            # Some contrast is good, too much might indicate inconsistency
            score = 0.9 if 0 < count < 5 else (0.6 if count >= 5 else 0.7)
            confidence = 0.4
            reasoning = f"Found {count} contrast markers"
            if count >= 5:
                suggestions.append("Review for potential contradictions or unclear positioning")
        
        return score, confidence, reasoning, suggestions
    
    def _generate_revision(self, output: str, scores: List[ReflectionScore],
                           context: Optional[Dict], user_intent: Optional[str]) -> Optional[str]:
        """
        Generate a revised version based on reflection scores.
        
        In production, this would use the LLM to rewrite.
        """
        if not self.llm_client:
            return None
        
        # Collect all suggestions
        all_suggestions = []
        for score in scores:
            all_suggestions.extend(score.suggestions)
        
        if not all_suggestions:
            return None
        
        # Build revision prompt
        improvement_areas = ", ".join(set(s.criterion.value for s in scores if s.suggestions))
        
        prompt = f"""Please revise the following output to address these issues:

Issues to fix:
{chr(10).join('- ' + s for s in all_suggestions)}

Focus areas: {improvement_areas}

Original output:
{output}

Provide only the revised output:"""
        
        try:
            # This would call the actual LLM in production
            # revised = self.llm_client.generate(prompt)
            logger.debug(f"Would generate revision with prompt length: {len(prompt)}")
            return None  # Placeholder
        except Exception as e:
            logger.error(f"Error generating revision: {e}")
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
            "most_common_improvements": self._get_common_improvements(all_results)
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
