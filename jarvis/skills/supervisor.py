"""
Supervisor Skill - Meta-skill that wraps other skills with self-correction.
Implements Plan → Execute → Critique → Refine loop for never-fail execution.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from jarvis.skills.base import BaseSkill, SkillStep, Recovery, RecoveryAction
from jarvis.core.memory import CoreMemory

logger = logging.getLogger(__name__)


class SupervisorSkill(BaseSkill):
    """
    Supervisor skill that orchestrates other skills with quality assurance.
    
    Features:
    - Evaluates outputs against original intent
    - Replans when quality is below threshold
    - Implements critique-refine loops
    - Tracks success patterns for learning
    """
    
    def __init__(self, name: str = "Supervisor", description: str = None):
        super().__init__(name=name, description=description or "Meta-skill for quality-assured task execution")
        self.max_refinement_cycles = 3
        self.quality_threshold = 0.8
        self._memory: Optional[CoreMemory] = None
        
    def set_memory(self, memory: CoreMemory):
        """Inject memory dependency for context retrieval."""
        self._memory = memory
    
    def get_system_prompt(self) -> str:
        return """You are JARVIS Supervisor, a meta-cognitive orchestration layer.

Your role:
1. Evaluate if delegated skills achieved the user's true intent
2. Identify gaps between output and expected outcome
3. Decide whether to accept results or initiate refinement
4. Learn from successful patterns to improve future execution

Always maintain awareness of:
- The original user goal
- Constraints and preferences from memory
- Quality standards for completion
- When to stop refining vs when to continue"""

    def can_handle(self, task: str) -> float:
        # Supervisor can handle any task by delegating
        return 1.0
    
    def plan(self, task: str) -> List[SkillStep]:
        """
        Create a supervision plan with built-in critique cycles.
        """
        steps = [
            SkillStep(
                id="supervise_0",
                name="Initialize Supervision",
                action="init_supervision",
                params={"task": task}
            ),
            SkillStep(
                id="delegate_1",
                name="Delegate to Specialized Skill",
                action="delegate_execution",
                params={"task": task}
            ),
            SkillStep(
                id="critique_2",
                name="Critique Output Quality",
                action="evaluate_quality",
                params={"task": task}
            ),
            SkillStep(
                id="refine_3",
                name="Refine if Needed",
                action="refinement_loop",
                params={"max_cycles": self.max_refinement_cycles}
            ),
            SkillStep(
                id="finalize_4",
                name="Finalize and Store Learning",
                action="finalize_execution",
                params={}
            )
        ]
        
        self.executed_steps = steps
        return steps
    
    def execute(self, plan: List[SkillStep]) -> Dict[str, Any]:
        """
        Execute supervision loop with critique and refinement.
        """
        self.initialize()
        
        try:
            # Step 1: Initialize
            init_result = self._run_step_action(plan[0])
            if not init_result.get('success'):
                return {'success': False, 'error': init_result.get('error')}
            
            # Step 2: Delegate execution
            delegation_result = self._run_step_action(plan[1])
            if not delegation_result.get('success'):
                return {'success': False, 'error': delegation_result.get('error')}
            
            execution_output = delegation_result.get('output', {})
            cycle_count = 0
            
            # Steps 3-4: Critique and Refine loop
            while cycle_count < self.max_refinement_cycles:
                critique_result = self._run_step_action(plan[2])
                
                quality_score = critique_result.get('quality_score', 0.0)
                gaps = critique_result.get('gaps', [])
                
                logger.info(f"Critique cycle {cycle_count + 1}: quality={quality_score:.2f}, gaps={len(gaps)}")
                
                # Check if quality meets threshold
                if quality_score >= self.quality_threshold and not gaps:
                    logger.info(f"Quality threshold met ({quality_score:.2f} >= {self.quality_threshold})")
                    break
                
                # Attempt refinement
                refine_result = self._run_step_action(plan[3])
                if not refine_result.get('success'):
                    logger.warning("Refinement failed, accepting current output")
                    break
                
                # Update execution output with refined version
                execution_output = refine_result.get('output', execution_output)
                cycle_count += 1
            
            # Step 5: Finalize
            final_result = self._run_step_action(plan[4])
            
            return {
                'success': True,
                'output': execution_output,
                'cycles_run': cycle_count,
                'final_quality': critique_result.get('quality_score', 0.0),
                'finalize_details': final_result
            }
            
        except Exception as e:
            logger.error(f"Supervision failed: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            self.cleanup()
    
    def handle_failure(self, step: SkillStep, error: Exception) -> Recovery:
        """
        Handle failures with intelligent recovery strategies.
        """
        error_msg = str(error)
        
        # Strategy based on step type
        if step.action == "delegate_execution":
            # Delegation failed - try alternative skill
            return Recovery(
                action=RecoveryAction.ALTERNATIVE,
                message=f"Primary skill failed: {error_msg}. Attempting alternative approach.",
                retry_count=0,
                max_retries=self.max_refinement_cycles
            )
        
        elif step.action == "evaluate_quality":
            # Critique failed - assume acceptable and continue
            return Recovery(
                action=RecoveryAction.SKIP,
                message=f"Quality evaluation failed: {error_msg}. Proceeding with current output.",
                skip_to_step="finalize_4"
            )
        
        elif step.action == "refinement_loop":
            # Refinement failed - retry with different strategy
            return Recovery(
                action=RecoveryAction.RETRY,
                message=f"Refinement failed: {error_msg}. Retrying with adjusted parameters.",
                retry_count=0,
                max_retries=2
            )
        
        else:
            # Generic failure - abort supervision
            return Recovery(
                action=RecoveryAction.ABORT,
                message=f"Critical failure in {step.name}: {error_msg}"
            )
    
    def rollback(self) -> Dict[str, Any]:
        """
        Rollback is typically not needed for supervision (read-only orchestration).
        """
        return {
            'rolled_back': False,
            'reason': 'Supervision is read-only orchestration, no state changes to rollback'
        }
    
    def summarize(self) -> str:
        """Provide summary of supervised execution."""
        cycles = len([s for s in self.executed_steps if s.completed])
        return f"Supervised task execution with {cycles} refinement cycles completed."
    
    def _run_step_action(self, step: SkillStep) -> Dict[str, Any]:
        """Execute individual supervision steps."""
        
        if step.action == "init_supervision":
            task = step.params.get('task', '')
            self.save_state('original_task', task)
            self.save_state('start_time', datetime.now().isoformat())
            
            # Retrieve relevant context from memory
            if self._memory:
                context = self._memory.retrieve_context(query=task, limit=3)
                self.save_state('retrieved_context', context)
            
            return {'success': True, 'makes_changes': False}
        
        elif step.action == "delegate_execution":
            # This would be implemented by actually calling other skills
            # For now, return placeholder
            task = self.load_state('original_task', '')
            return {
                'success': True,
                'output': {'task': task, 'status': 'executed'},
                'makes_changes': False
            }
        
        elif step.action == "evaluate_quality":
            task = self.load_state('original_task', '')
            output = self.load_state('current_output', {})
            
            # Simple heuristic evaluation (would use LLM in production)
            quality_score = 0.85  # Placeholder
            gaps = []
            
            # Check if output addresses task keywords
            task_keywords = set(task.lower().split())
            output_text = str(output).lower()
            missing_keywords = [k for k in task_keywords if k not in output_text and len(k) > 3]
            
            if missing_keywords:
                gaps.append(f"Missing coverage of: {', '.join(missing_keywords[:3])}")
                quality_score -= len(missing_keywords) * 0.1
            
            quality_score = max(0.0, min(1.0, quality_score))
            
            return {
                'success': True,
                'quality_score': quality_score,
                'gaps': gaps,
                'makes_changes': False
            }
        
        elif step.action == "refinement_loop":
            # Refine based on identified gaps
            gaps = self.load_state('identified_gaps', [])
            current_output = self.load_state('current_output', {})
            
            # Placeholder refinement logic
            refined_output = current_output.copy()
            refined_output['refined'] = True
            
            self.save_state('current_output', refined_output)
            
            return {
                'success': True,
                'output': refined_output,
                'makes_changes': False
            }
        
        elif step.action == "finalize_execution":
            # Store learning in memory
            if self._memory:
                task = self.load_state('original_task', '')
                output = self.load_state('current_output', {})
                success = True
                
                self._memory.log_interaction(
                    task=task,
                    plan=str(self.executed_steps),
                    outcome=str(output),
                    success=success
                )
            
            return {
                'success': True,
                'stored_learning': True,
                'makes_changes': False
            }
        
        else:
            return {'success': False, 'error': f'Unknown action: {step.action}'}


__all__ = ['SupervisorSkill']
