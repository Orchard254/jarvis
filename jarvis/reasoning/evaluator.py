"""
Path Evaluator for Tree of Thoughts (ToT) Architecture
Evaluates and scores different reasoning paths using heuristics and LLM feedback.
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EvaluationCriteria(Enum):
    """Criteria for evaluating thought paths."""
    RELEVANCE = "relevance"  # How relevant to the original goal
    FEASIBILITY = "feasibility"  # How feasible is the execution
    EFFICIENCY = "efficiency"  # How efficient/direct the path is
    COMPLETENESS = "completeness"  # Does it address all aspects
    ROBUSTNESS = "robustness"  # How well it handles edge cases/failures


@dataclass
class PathEvaluation:
    """Result of evaluating a single path."""
    path_id: str
    path_nodes: List[str]  # List of node IDs in the path
    overall_score: float  # 0.0 to 1.0
    criteria_scores: Dict[EvaluationCriteria, float]
    reasoning: str
    estimated_success_probability: float
    risk_level: str  # "low", "medium", "high"
    recommended: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "path_nodes": self.path_nodes,
            "overall_score": self.overall_score,
            "criteria_scores": {k.value: v for k, v in self.criteria_scores.items()},
            "reasoning": self.reasoning,
            "estimated_success_probability": self.estimated_success_probability,
            "risk_level": self.risk_level,
            "recommended": self.recommended
        }


class PathEvaluator:
    """
    Evaluates multiple reasoning paths from the Tree of Thoughts.
    
    Uses both heuristic scoring and LLM-based evaluation to assess:
    - Relevance to goal
    - Feasibility of execution
    - Efficiency (shortest viable path)
    - Completeness of solution
    - Robustness against failures
    
    Supports batch evaluation for comparing multiple paths simultaneously.
    """
    
    def __init__(self, llm_interface=None, weights: Dict[EvaluationCriteria, float] = None):
        """
        Initialize the Path Evaluator.
        
        Args:
            llm_interface: LLM interface for evaluation prompts
            weights: Importance weights for each evaluation criterion
        """
        self.llm = llm_interface
        
        # Default weights (can be customized per use case)
        self.weights = weights or {
            EvaluationCriteria.RELEVANCE: 0.25,
            EvaluationCriteria.FEASIBILITY: 0.25,
            EvaluationCriteria.EFFICIENCY: 0.15,
            EvaluationCriteria.COMPLETENESS: 0.20,
            EvaluationCriteria.ROBUSTNESS: 0.15
        }
        
        # Normalize weights
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            self.weights = {k: v / total_weight for k, v in self.weights.items()}
    
    async def evaluate_path(
        self,
        path_nodes: List[Dict[str, Any]],
        goal: str,
        context: str = ""
    ) -> PathEvaluation:
        """
        Evaluate a single path through the tree of thoughts.
        
        Args:
            path_nodes: List of node dictionaries with content, status, etc.
            goal: The original goal/problem statement
            context: Additional context for evaluation
            
        Returns:
            PathEvaluation with scores and reasoning
        """
        path_id = path_nodes[0].get("id", "unknown") if path_nodes else "empty"
        
        # Build path description
        path_description = self._build_path_description(path_nodes)
        
        # Evaluate each criterion
        criteria_scores = {}
        criteria_reasoning = {}
        
        # 1. Relevance Score
        relevance_score, relevance_reasoning = await self._evaluate_relevance(
            path_description, goal, context
        )
        criteria_scores[EvaluationCriteria.RELEVANCE] = relevance_score
        criteria_reasoning["relevance"] = relevance_reasoning
        
        # 2. Feasibility Score
        feasibility_score, feasibility_reasoning = await self._evaluate_feasibility(
            path_description, context
        )
        criteria_scores[EvaluationCriteria.FEASIBILITY] = feasibility_score
        criteria_reasoning["feasibility"] = feasibility_reasoning
        
        # 3. Efficiency Score
        efficiency_score, efficiency_reasoning = await self._evaluate_efficiency(
            path_nodes, goal
        )
        criteria_scores[EvaluationCriteria.EFFICIENCY] = efficiency_score
        criteria_reasoning["efficiency"] = efficiency_reasoning
        
        # 4. Completeness Score
        completeness_score, completeness_reasoning = await self._evaluate_completeness(
            path_description, goal
        )
        criteria_scores[EvaluationCriteria.COMPLETENESS] = completeness_score
        criteria_reasoning["completeness"] = completeness_reasoning
        
        # 5. Robustness Score
        robustness_score, robustness_reasoning = await self._evaluate_robustness(
            path_description, context
        )
        criteria_scores[EvaluationCriteria.ROBUSTNESS] = robustness_score
        criteria_reasoning["robustness"] = robustness_reasoning
        
        # Calculate weighted overall score
        overall_score = sum(
            criteria_scores[criteria] * self.weights.get(criteria, 0)
            for criteria in EvaluationCriteria
        )
        
        # Determine risk level
        risk_level = self._determine_risk_level(overall_score, criteria_scores)
        
        # Estimate success probability
        success_probability = self._estimate_success_probability(
            overall_score, criteria_scores, path_nodes
        )
        
        # Build combined reasoning
        reasoning = self._build_reasoning(criteria_reasoning, overall_score)
        
        return PathEvaluation(
            path_id=path_id,
            path_nodes=[n.get("id", "") for n in path_nodes],
            overall_score=round(overall_score, 3),
            criteria_scores=criteria_scores,
            reasoning=reasoning,
            estimated_success_probability=round(success_probability, 3),
            risk_level=risk_level
        )
    
    async def evaluate_multiple_paths(
        self,
        paths: List[List[Dict[str, Any]]],
        goal: str,
        context: str = "",
        top_k: int = 3
    ) -> List[PathEvaluation]:
        """
        Evaluate multiple paths and rank them.
        
        Args:
            paths: List of paths, where each path is a list of node dicts
            goal: The original goal/problem statement
            context: Additional context
            top_k: Number of top paths to mark as recommended
            
        Returns:
            List of PathEvaluations sorted by overall score (descending)
        """
        evaluations = []
        
        # Evaluate all paths (can be parallelized for large batches)
        for path in paths:
            evaluation = await self.evaluate_path(path, goal, context)
            evaluations.append(evaluation)
        
        # Sort by overall score
        evaluations.sort(key=lambda e: e.overall_score, reverse=True)
        
        # Mark top_k as recommended
        for i, eval_result in enumerate(evaluations[:top_k]):
            eval_result.recommended = True
        
        return evaluations
    
    def _build_path_description(self, path_nodes: List[Dict[str, Any]]) -> str:
        """Build a text description of the path for evaluation."""
        descriptions = []
        for i, node in enumerate(path_nodes):
            content = node.get("content", "")
            action_type = node.get("metadata", {}).get("action_type", "general")
            score = node.get("value_score", 0)
            descriptions.append(
                f"Step {i+1} [{action_type}] (score: {score:.2f}): {content}"
            )
        return "\n".join(descriptions)
    
    async def _evaluate_relevance(
        self,
        path_description: str,
        goal: str,
        context: str
    ) -> Tuple[float, str]:
        """Evaluate how relevant the path is to the goal."""
        if not self.llm:
            # Heuristic fallback: check keyword overlap
            return self._heuristic_relevance(path_description, goal)
        
        prompt = f"""
Goal: {goal}
{f'Context: {context}' if context else ''}

Proposed Solution Path:
{path_description}

Evaluate how relevant each step is to achieving the goal.
Consider:
1. Does each step directly contribute to the goal?
2. Are there any irrelevant or tangential steps?
3. Does the path maintain focus throughout?

Rate relevance on a scale of 0.0 to 1.0.
Return JSON: {{"score": 0.85, "reasoning": "brief explanation"}}
"""
        try:
            response = await self.llm.generate_async(prompt, temperature=0.2)
            result = self._parse_json_response(response)
            return result.get("score", 0.5), result.get("reasoning", "")
        except Exception as e:
            logger.debug(f"LLM relevance evaluation failed: {e}")
            return self._heuristic_relevance(path_description, goal)
    
    def _heuristic_relevance(
        self,
        path_description: str,
        goal: str
    ) -> Tuple[float, str]:
        """Heuristic relevance scoring without LLM."""
        goal_words = set(goal.lower().split())
        path_words = set(path_description.lower().split())
        
        # Simple word overlap ratio
        overlap = len(goal_words & path_words)
        union = len(goal_words | path_words)
        
        score = overlap / union if union > 0 else 0.5
        reasoning = f"Word overlap ratio: {overlap}/{union}"
        
        return min(1.0, score * 2), reasoning  # Scale up for heuristic
    
    async def _evaluate_feasibility(
        self,
        path_description: str,
        context: str
    ) -> Tuple[float, str]:
        """Evaluate how feasible the path is to execute."""
        if not self.llm:
            # Heuristic: assume medium feasibility
            return 0.6, "Default feasibility score (no LLM)"
        
        prompt = f"""
{f'Context: {context}' if context else ''}

Proposed Solution Path:
{path_description}

Evaluate the feasibility of executing this path. Consider:
1. Are the required tools/resources available?
2. Is each step technically possible?
3. Are there any obvious blockers or constraints?
4. Is the sequence of steps logical?

Rate feasibility on a scale of 0.0 to 1.0.
Return JSON: {{"score": 0.75, "reasoning": "brief explanation"}}
"""
        try:
            response = await self.llm.generate_async(prompt, temperature=0.2)
            result = self._parse_json_response(response)
            return result.get("score", 0.5), result.get("reasoning", "")
        except Exception as e:
            logger.debug(f"LLM feasibility evaluation failed: {e}")
            return 0.6, "Feasibility evaluation error"
    
    async def _evaluate_efficiency(
        self,
        path_nodes: List[Dict[str, Any]],
        goal: str
    ) -> Tuple[float, str]:
        """Evaluate the efficiency of the path (shorter is better)."""
        num_steps = len(path_nodes)
        
        # Ideal step count depends on goal complexity
        # For now, use a simple heuristic: 3-5 steps is optimal
        optimal_steps = 4
        if num_steps <= optimal_steps:
            score = 1.0 - (optimal_steps - num_steps) * 0.1
        else:
            score = max(0.3, 1.0 - (num_steps - optimal_steps) * 0.15)
        
        reasoning = f"Path has {num_steps} steps (optimal: ~{optimal_steps})"
        return score, reasoning
    
    async def _evaluate_completeness(
        self,
        path_description: str,
        goal: str
    ) -> Tuple[float, str]:
        """Evaluate whether the path addresses all aspects of the goal."""
        if not self.llm:
            # Heuristic: check for solution indicators
            has_solution_keywords = any(
                kw in path_description.lower()
                for kw in ["solution", "complete", "finish", "result", "achieve"]
            )
            score = 0.7 if has_solution_keywords else 0.5
            return score, "Heuristic completeness check"
        
        prompt = f"""
Goal: {goal}

Proposed Solution Path:
{path_description}

Evaluate whether this path completely addresses the goal. Consider:
1. Are all aspects of the goal covered?
2. Does the path lead to a complete solution?
3. Are there any missing components or gaps?

Rate completeness on a scale of 0.0 to 1.0.
Return JSON: {{"score": 0.8, "reasoning": "brief explanation"}}
"""
        try:
            response = await self.llm.generate_async(prompt, temperature=0.2)
            result = self._parse_json_response(response)
            return result.get("score", 0.5), result.get("reasoning", "")
        except Exception as e:
            logger.debug(f"LLM completeness evaluation failed: {e}")
            return 0.6, "Completeness evaluation error"
    
    async def _evaluate_robustness(
        self,
        path_description: str,
        context: str
    ) -> Tuple[float, str]:
        """Evaluate how robust the path is against failures."""
        if not self.llm:
            # Check for fallback/error handling keywords
            has_error_handling = any(
                kw in path_description.lower()
                for kw in ["error", "fallback", "retry", "handle", "check", "verify"]
            )
            score = 0.7 if has_error_handling else 0.4
            return score, "Heuristic robustness check"
        
        prompt = f"""
{f'Context: {context}' if context else ''}

Proposed Solution Path:
{path_description}

Evaluate the robustness of this path. Consider:
1. Does the path include error checking?
2. Are there fallback strategies for potential failures?
3. Does it handle edge cases?
4. Is there validation at critical points?

Rate robustness on a scale of 0.0 to 1.0.
Return JSON: {{"score": 0.65, "reasoning": "brief explanation"}}
"""
        try:
            response = await self.llm.generate_async(prompt, temperature=0.2)
            result = self._parse_json_response(response)
            return result.get("score", 0.5), result.get("reasoning", "")
        except Exception as e:
            logger.debug(f"LLM robustness evaluation failed: {e}")
            return 0.5, "Robustness evaluation error"
    
    def _determine_risk_level(
        self,
        overall_score: float,
        criteria_scores: Dict[EvaluationCriteria, float]
    ) -> str:
        """Determine the risk level based on scores."""
        if overall_score >= 0.8:
            return "low"
        elif overall_score >= 0.6:
            return "medium"
        else:
            return "high"
    
    def _estimate_success_probability(
        self,
        overall_score: float,
        criteria_scores: Dict[EvaluationCriteria, float],
        path_nodes: List[Dict[str, Any]]
    ) -> float:
        """Estimate the probability of success for this path."""
        # Base probability from overall score
        base_prob = overall_score
        
        # Adjust based on individual node scores if available
        if path_nodes:
            node_scores = [n.get("value_score", 0.5) for n in path_nodes]
            avg_node_score = sum(node_scores) / len(node_scores)
            # Blend overall evaluation with node-level scores
            base_prob = 0.7 * base_prob + 0.3 * avg_node_score
        
        # Slight penalty for high-risk paths
        feasibility = criteria_scores.get(EvaluationCriteria.FEASIBILITY, 0.5)
        if feasibility < 0.5:
            base_prob *= 0.9
        
        return min(1.0, max(0.0, base_prob))
    
    def _build_reasoning(
        self,
        criteria_reasoning: Dict[str, str],
        overall_score: float
    ) -> str:
        """Build a combined reasoning string."""
        parts = [f"Overall Score: {overall_score:.2f}"]
        for criterion, reasoning in criteria_reasoning.items():
            if reasoning:
                parts.append(f"- {criterion.capitalize()}: {reasoning}")
        return "\n".join(parts)
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        import json
        import re
        
        try:
            # Try to find JSON object pattern
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}
        except Exception:
            return {}


def get_evaluator(llm_interface=None, **kwargs) -> PathEvaluator:
    """Factory function to create a PathEvaluator instance."""
    return PathEvaluator(llm_interface=llm_interface, **kwargs)
