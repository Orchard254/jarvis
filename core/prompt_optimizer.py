"""
Automated Prompt Optimization Module for JARVIS Phase 5.
Dynamically improves prompts based on feedback signals and performance metrics.
Implements A/B testing, multi-armed bandits, and evolutionary strategies.
"""
import logging
import json
import time
import random
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    """Strategies for prompt optimization."""
    A_B_TESTING = "ab_testing"
    MULTI_ARMED_BANDIT = "multi_armed_bandit"
    EVOLUTIONARY = "evolutionary"
    BAYESIAN = "bayesian"
    REINFORCEMENT = "reinforcement"


@dataclass
class PromptVariant:
    """Represents a variant of a prompt template."""
    id: str
    template: str
    base_prompt_id: str
    created_at: float = field(default_factory=time.time)
    wins: int = 0
    trials: int = 0
    avg_score: float = 0.0
    score_history: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_score(self, score: float):
        """Update statistics with a new score."""
        self.trials += 1
        self.score_history.append(score)
        # Exponential moving average
        alpha = 0.3
        if len(self.score_history) == 1:
            self.avg_score = score
        else:
            self.avg_score = alpha * score + (1 - alpha) * self.avg_score
    
    def record_win(self):
        """Record a win for this variant."""
        self.wins += 1
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        return self.wins / max(self.trials, 1)
    
    @property
    def confidence(self) -> float:
        """Calculate confidence based on number of trials."""
        # Simple confidence: more trials = more confidence
        return min(1.0, self.trials / 30)


@dataclass
class OptimizationResult:
    """Result of prompt optimization."""
    prompt_id: str
    selected_variant_id: str
    strategy_used: OptimizationStrategy
    variants_tested: int
    best_score: float
    improvement_over_baseline: float
    total_trials: int
    timestamp: float = field(default_factory=time.time)


class PromptOptimizer:
    """
    Automated prompt optimization system.
    
    Continuously improves prompts through:
    - A/B testing of variants
    - Multi-armed bandit selection
    - Evolutionary mutation and crossover
    - Performance-based ranking
    """
    
    def __init__(self, llm_client=None, strategy: OptimizationStrategy = OptimizationStrategy.MULTI_ARMED_BANDIT,
                 exploration_rate: float = 0.1, mutation_rate: float = 0.2):
        """
        Initialize the prompt optimizer.
        
        Args:
            llm_client: LLM client for generating variants
            strategy: Default optimization strategy
            exploration_rate: Rate of exploring vs exploiting (for bandits)
            mutation_rate: Rate of mutation in evolutionary approach
        """
        self.llm_client = llm_client
        self.strategy = strategy
        self.exploration_rate = exploration_rate
        self.mutation_rate = mutation_rate
        
        # Storage
        self._prompts: Dict[str, Dict[str, PromptVariant]] = defaultdict(dict)  # prompt_id -> {variant_id: variant}
        self._baselines: Dict[str, str] = {}  # prompt_id -> baseline_variant_id
        self._feedback_history: Dict[str, List[Tuple[str, float, Dict]]] = defaultdict(list)
        self._optimization_results: List[OptimizationResult] = []
        
        # Bandit state
        self._bandit_state: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        logger.info(f"PromptOptimizer initialized with strategy: {strategy.value}")
    
    def register_prompt(self, prompt_id: str, template: str, is_baseline: bool = True) -> PromptVariant:
        """
        Register a new prompt template.
        
        Args:
            prompt_id: Unique identifier for this prompt
            template: The prompt template string
            is_baseline: Whether this is the baseline variant
            
        Returns:
            The created PromptVariant
        """
        variant_id = f"{prompt_id}_v{len(self._prompts[prompt_id]) + 1}"
        variant = PromptVariant(
            id=variant_id,
            template=template,
            base_prompt_id=prompt_id
        )
        
        self._prompts[prompt_id][variant_id] = variant
        
        if is_baseline or prompt_id not in self._baselines:
            self._baselines[prompt_id] = variant_id
            logger.info(f"Registered baseline variant {variant_id} for prompt {prompt_id}")
        else:
            logger.debug(f"Registered variant {variant_id} for prompt {prompt_id}")
        
        return variant
    
    def get_best_variant(self, prompt_id: str) -> PromptVariant:
        """
        Get the best performing variant for a prompt using the configured strategy.
        
        Args:
            prompt_id: The prompt identifier
            
        Returns:
            The selected PromptVariant
        """
        if prompt_id not in self._prompts or not self._prompts[prompt_id]:
            raise ValueError(f"No variants found for prompt {prompt_id}")
        
        variants = list(self._prompts[prompt_id].values())
        
        if len(variants) == 1:
            return variants[0]
        
        if self.strategy == OptimizationStrategy.A_B_TESTING:
            return self._select_ab_testing(variants)
        elif self.strategy == OptimizationStrategy.MULTI_ARMED_BANDIT:
            return self._select_bandit(prompt_id, variants)
        elif self.strategy == OptimizationStrategy.EVOLUTIONARY:
            return self._select_evolutionary(prompt_id, variants)
        else:
            # Default: highest average score
            return max(variants, key=lambda v: v.avg_score)
    
    def _select_ab_testing(self, variants: List[PromptVariant]) -> PromptVariant:
        """Select variant using A/B testing (round-robin with statistical significance)."""
        # Simple round-robin for now; production would use statistical tests
        min_trials = min(v.trials for v in variants)
        candidates = [v for v in variants if v.trials == min_trials]
        return random.choice(candidates) if candidates else random.choice(variants)
    
    def _select_bandit(self, prompt_id: str, variants: List[PromptVariant]) -> PromptVariant:
        """Select variant using Upper Confidence Bound (UCB1) algorithm."""
        if random.random() < self.exploration_rate:
            # Exploration: pick random variant
            return random.choice(variants)
        
        # Exploitation: UCB1 selection
        total_trials = sum(v.trials for v in variants) or 1
        
        ucb_scores = []
        for v in variants:
            if v.trials == 0:
                # Never tried: infinite UCB
                ucb_scores.append((float('inf'), v))
            else:
                # UCB1 formula
                exploration_bonus = (2 * total_trials / v.trials) ** 0.5
                ucb = v.avg_score + exploration_bonus
                ucb_scores.append((ucb, v))
        
        return max(ucb_scores, key=lambda x: x[0])[1]
    
    def _select_evolutionary(self, prompt_id: str, variants: List[PromptVariant]) -> PromptVariant:
        """Select variant using tournament selection."""
        # Tournament selection
        tournament_size = min(3, len(variants))
        tournament = random.sample(variants, tournament_size)
        return max(tournament, key=lambda v: v.avg_score)
    
    def record_feedback(self, prompt_id: str, variant_id: str, score: float,
                        context: Optional[Dict] = None):
        """
        Record feedback for a prompt variant.
        
        Args:
            prompt_id: The prompt identifier
            variant_id: The variant that was used
            score: Performance score (higher is better)
            context: Additional context about the evaluation
        """
        if prompt_id not in self._prompts or variant_id not in self._prompts[prompt_id]:
            logger.warning(f"Cannot record feedback for unknown variant {variant_id}")
            return
        
        # Update variant statistics
        variant = self._prompts[prompt_id][variant_id]
        variant.update_score(score)
        
        # Record feedback
        self._feedback_history[prompt_id].append((variant_id, score, context or {}))
        
        # Check if this variant should be marked as a winner
        baseline_id = self._baselines.get(prompt_id)
        if baseline_id and variant_id != baseline_id:
            baseline_variant = self._prompts[prompt_id].get(baseline_id)
            if baseline_variant and variant.avg_score > baseline_variant.avg_score:
                variant.record_win()
        
        logger.debug(f"Recorded feedback for {variant_id}: score={score:.2f}, avg={variant.avg_score:.2f}")
    
    def generate_variants(self, prompt_id: str, num_variants: int = 3,
                          mutation_types: Optional[List[str]] = None) -> List[PromptVariant]:
        """
        Generate new prompt variants through mutation.
        
        Args:
            prompt_id: The base prompt to mutate
            num_variants: Number of variants to generate
            mutation_types: Types of mutations to apply
            
        Returns:
            List of newly created PromptVariants
        """
        if prompt_id not in self._prompts:
            raise ValueError(f"Prompt {prompt_id} not found")
        
        if not self.llm_client:
            logger.warning("No LLM client available; cannot generate variants")
            return []
        
        base_variant = self._prompts[prompt_id].get(self._baselines.get(prompt_id))
        if not base_variant:
            return []
        
        mutation_types = mutation_types or [
            "rephrase", "add_examples", "change_tone", "adjust_length",
            "add_constraints", "reorder_instructions"
        ]
        
        new_variants = []
        
        for i in range(num_variants):
            mutation = random.choice(mutation_types)
            
            # In production, this would call LLM to generate mutated prompt
            # For now, create simple heuristic mutations
            mutated_template = self._apply_mutation(base_variant.template, mutation)
            
            variant_id = f"{prompt_id}_v{len(self._prompts[prompt_id]) + 1}"
            variant = PromptVariant(
                id=variant_id,
                template=mutated_template,
                base_prompt_id=prompt_id,
                metadata={"mutation_type": mutation, "parent_id": base_variant.id}
            )
            
            self._prompts[prompt_id][variant_id] = variant
            new_variants.append(variant)
            logger.info(f"Generated variant {variant_id} via {mutation}")
        
        return new_variants
    
    def _apply_mutation(self, template: str, mutation_type: str) -> str:
        """Apply a specific mutation type to a template."""
        # Placeholder mutations - production would use LLM
        if mutation_type == "rephrase":
            # Add rephrasing prefix
            return f"Please consider carefully: {template}"
        elif mutation_type == "add_examples":
            return f"{template}\n\nExample format: Show your reasoning step by step."
        elif mutation_type == "change_tone":
            return f"Be concise and professional. {template}"
        elif mutation_type == "adjust_length":
            return f"Provide a detailed, comprehensive answer. {template}"
        elif mutation_type == "add_constraints":
            return f"{template}\n\nConstraints: Be accurate, cite sources when possible."
        elif mutation_type == "reorder_instructions":
            # Simple reorder simulation
            parts = template.split('\n')
            if len(parts) > 1:
                parts = [parts[-1]] + parts[:-1]
            return '\n'.join(parts)
        else:
            return template
    
    def run_optimization_round(self, prompt_id: str, eval_function: Callable[[str], float],
                               num_iterations: int = 10) -> OptimizationResult:
        """
        Run an optimization round for a prompt.
        
        Args:
            prompt_id: The prompt to optimize
            eval_function: Function that takes a prompt template and returns a score
            num_iterations: Number of evaluation iterations
            
        Returns:
            OptimizationResult with findings
        """
        if prompt_id not in self._prompts:
            raise ValueError(f"Prompt {prompt_id} not found")
        
        variants = list(self._prompts[prompt_id].values())
        baseline_id = self._baselines.get(prompt_id)
        baseline_variant = self._prompts[prompt_id].get(baseline_id) if baseline_id else None
        
        logger.info(f"Starting optimization round for {prompt_id} with {len(variants)} variants")
        
        # Run evaluations
        for _ in range(num_iterations):
            selected = self.get_best_variant(prompt_id)
            score = eval_function(selected.template)
            self.record_feedback(prompt_id, selected.id, score)
        
        # Find best variant
        best_variant = max(variants, key=lambda v: v.avg_score)
        
        # Calculate improvement over baseline
        baseline_score = baseline_variant.avg_score if baseline_variant else 0
        improvement = best_variant.avg_score - baseline_score
        
        result = OptimizationResult(
            prompt_id=prompt_id,
            selected_variant_id=best_variant.id,
            strategy_used=self.strategy,
            variants_tested=len(variants),
            best_score=best_variant.avg_score,
            improvement_over_baseline=improvement,
            total_trials=sum(v.trials for v in variants)
        )
        
        self._optimization_results.append(result)
        logger.info(f"Optimization complete: best={best_variant.id}, score={best_variant.avg_score:.2f}, "
                   f"improvement={improvement:.2f}")
        
        return result
    
    def get_prompt_stats(self, prompt_id: str) -> Dict[str, Any]:
        """Get statistics for a specific prompt."""
        if prompt_id not in self._prompts:
            return {"error": "Prompt not found"}
        
        variants = self._prompts[prompt_id].values()
        baseline_id = self._baselines.get(prompt_id)
        
        return {
            "prompt_id": prompt_id,
            "baseline_variant_id": baseline_id,
            "total_variants": len(self._prompts[prompt_id]),
            "total_trials": sum(v.trials for v in variants),
            "best_avg_score": max((v.avg_score for v in variants), default=0),
            "variants": [
                {
                    "id": v.id,
                    "is_baseline": v.id == baseline_id,
                    "trials": v.trials,
                    "avg_score": v.avg_score,
                    "win_rate": v.win_rate,
                    "confidence": v.confidence
                }
                for v in variants
            ]
        }
    
    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics across all prompts."""
        all_results = self._optimization_results
        
        if not all_results:
            return {"total_optimizations": 0}
        
        improvements = [r.improvement_over_baseline for r in all_results]
        
        return {
            "total_optimizations": len(all_results),
            "total_prompts": len(self._prompts),
            "total_variants": sum(len(v) for v in self._prompts.values()),
            "average_improvement": statistics.mean(improvements),
            "best_improvement": max(improvements),
            "strategy_distribution": self._get_strategy_distribution()
        }
    
    def _get_strategy_distribution(self) -> Dict[str, int]:
        """Get distribution of strategies used."""
        dist = defaultdict(int)
        for result in self._optimization_results:
            dist[result.strategy_used.value] += 1
        return dict(dist)
    
    def export_prompts(self) -> Dict[str, str]:
        """Export the best variant for each prompt."""
        best_prompts = {}
        for prompt_id in self._prompts:
            best_variant = self.get_best_variant(prompt_id)
            best_prompts[prompt_id] = best_variant.template
        return best_prompts


# Singleton instance
prompt_optimizer = PromptOptimizer()


def optimize_prompt(prompt_id: str, template: str, score: float) -> str:
    """
    Convenience function to register a prompt, record feedback, and get best variant.
    
    Args:
        prompt_id: Unique identifier
        template: Prompt template
        score: Initial feedback score
        
    Returns:
        Template of the best variant
    """
    # Register if new
    if prompt_id not in prompt_optimizer._prompts or not prompt_optimizer._prompts[prompt_id]:
        prompt_optimizer.register_prompt(prompt_id, template)
    
    # Get current best
    best = prompt_optimizer.get_best_variant(prompt_id)
    
    # Record feedback
    prompt_optimizer.record_feedback(prompt_id, best.id, score)
    
    return best.template
