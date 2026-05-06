"""
8. AI Internal Tools (3 tools)
Model-to-model intelligence layer.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class ReasoningResult:
    """Result of reasoning operation."""
    conclusion: str
    confidence: float
    steps: list
    assumptions: list
    alternatives: list


class ReasoningEngine:
    """
    reasoning_engine: GPT-OSS 120B main planner
    
    Core reasoning and planning using the large language model.
    """
    
    def __init__(self, model=None, max_tokens: int = 4096):
        self.model = model
        self.max_tokens = max_tokens
        self._reasoning_history = []
    
    def execute(self, task: str, context: Optional[dict] = None,
                reasoning_type: str = "plan", **kwargs) -> dict:
        """
        Perform reasoning on a task.
        
        Args:
            task: Task or question to reason about
            context: Additional context information
            reasoning_type: One of 'plan', 'analyze', 'decide', 'explain'
            
        Returns:
            Reasoning result with conclusions and steps
        """
        try:
            start_time = time.time()
            
            # Use model if available
            if self.model:
                result = self._reason_with_model(task, context, reasoning_type)
            else:
                # Fallback heuristic reasoning
                result = self._heuristic_reasoning(task, context, reasoning_type)
            
            reasoning_time = time.time() - start_time
            
            # Store in history
            self._reasoning_history.append({
                "task": task,
                "type": reasoning_type,
                "result": result,
                "time": reasoning_time
            })
            
            return {
                "success": True,
                "output": {
                    **result,
                    "reasoning_time_seconds": reasoning_time,
                    "model": "gpt-oss-120b" if self.model else "heuristic"
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _reason_with_model(self, task: str, context: dict, 
                           reasoning_type: str) -> dict:
        """Reason using GPT-OSS 120B model."""
        # TODO: Integrate with actual GPT-OSS 120B model
        logger.info(f"Reasoning with model: {task[:50]}...")
        
        return {
            "conclusion": f"Model-based conclusion for: {task}",
            "confidence": 0.92,
            "steps": [
                "Analyzed task requirements",
                "Evaluated available capabilities",
                "Generated optimal approach"
            ],
            "assumptions": ["User has necessary permissions", "Resources are available"],
            "alternatives": ["Alternative approach 1", "Alternative approach 2"]
        }
    
    def _heuristic_reasoning(self, task: str, context: dict,
                             reasoning_type: str) -> dict:
        """Fallback heuristic reasoning without model."""
        logger.warning("Using heuristic reasoning (no model available)")
        
        # Simple task analysis
        task_lower = task.lower()
        
        if "search" in task_lower or "find" in task_lower:
            conclusion = "Task involves information retrieval"
            steps = ["Identify search terms", "Select appropriate sources", "Execute search", "Filter results"]
        elif "create" in task_lower or "write" in task_lower:
            conclusion = "Task involves content creation"
            steps = ["Gather requirements", "Plan structure", "Generate content", "Review and refine"]
        elif "analyze" in task_lower or "understand" in task_lower:
            conclusion = "Task involves analysis"
            steps = ["Collect data", "Identify patterns", "Draw conclusions", "Validate findings"]
        else:
            conclusion = "General task identified"
            steps = ["Understand requirements", "Plan approach", "Execute", "Verify"]
        
        return {
            "conclusion": conclusion,
            "confidence": 0.6,
            "steps": steps,
            "assumptions": ["Standard operating conditions"],
            "alternatives": ["Manual execution", "Delegated execution"]
        }
    
    def get_history(self, limit: int = 10) -> list:
        """Get recent reasoning history."""
        return self._reasoning_history[-limit:]
    
    def clear_history(self):
        """Clear reasoning history."""
        self._reasoning_history.clear()


class VisionReasoningBridge:
    """
    vision_reasoning_bridge: Gemma → text reasoning conversion
    
    Converts vision model outputs into text reasoning format.
    """
    
    def __init__(self, vision_model=None, reasoning_model=None):
        self.vision_model = vision_model
        self.reasoning_model = reasoning_model
    
    def execute(self, vision_output: dict, task: str,
                **kwargs) -> dict:
        """
        Convert vision output to reasoning format.
        
        Args:
            vision_output: Output from vision analyzer
            task: Current task context
            
        Returns:
            Bridged reasoning result
        """
        try:
            # Extract key information from vision output
            description = vision_output.get("description", "")
            objects = vision_output.get("objects", [])
            ui_elements = vision_output.get("ui_elements", [])
            
            # Generate reasoning from visual information
            reasoning = self._bridge_vision_to_reasoning(
                description, objects, ui_elements, task
            )
            
            return {
                "success": True,
                "output": {
                    "visual_summary": reasoning["summary"],
                    "actionable_items": reasoning["actions"],
                    "reasoning_chain": reasoning["chain"],
                    "confidence": reasoning["confidence"]
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _bridge_vision_to_reasoning(self, description: str, objects: list,
                                     ui_elements: list, task: str) -> dict:
        """Convert vision data to reasoning format."""
        
        # Analyze what's visible
        summary_parts = []
        actions = []
        
        if description:
            summary_parts.append(f"Scene: {description[:200]}")
        
        if objects:
            summary_parts.append(f"Objects detected: {len(objects)}")
        
        if ui_elements:
            summary_parts.append(f"UI elements: {len(ui_elements)}")
            
            # Generate potential actions based on UI
            for elem in ui_elements[:5]:  # Limit to first 5
                elem_type = elem.get("type", "unknown")
                if elem_type == "button":
                    actions.append(f"Can click: {elem.get('text', 'button')}")
                elif elem_type == "input":
                    actions.append(f"Can type in: {elem.get('label', 'input field')}")
        
        # Build reasoning chain
        chain = [
            "Received visual input",
            f"Identified {len(objects)} objects and {len(ui_elements)} UI elements",
            "Mapped visual elements to potential actions",
            "Generated actionable recommendations"
        ]
        
        return {
            "summary": ". ".join(summary_parts),
            "actions": actions if actions else ["No immediate actions identified"],
            "chain": chain,
            "confidence": 0.85 if ui_elements else 0.6
        }


class ToolSelfEvaluator:
    """
    tool_self_evaluator: Checks tool outputs for errors
    
    Validates tool execution results and suggests corrections.
    """
    
    def __init__(self, evaluation_threshold: float = 0.7):
        self.threshold = evaluation_threshold
        self._evaluation_log = []
    
    def execute(self, tool_name: str, tool_output: dict,
                expected_schema: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Evaluate tool execution result.
        
        Args:
            tool_name: Name of the executed tool
            tool_output: Output from tool execution
            expected_schema: Expected output schema for validation
            
        Returns:
            Evaluation result with quality metrics
        """
        try:
            # Check basic success
            success = tool_output.get("success", False)
            error = tool_output.get("error")
            output = tool_output.get("output")
            
            # Evaluate quality
            quality_score = self._calculate_quality(tool_output, expected_schema)
            
            # Identify issues
            issues = []
            if not success:
                issues.append({
                    "type": "execution_failure",
                    "severity": "high",
                    "message": error or "Tool execution failed"
                })
            
            if output is None and success:
                issues.append({
                    "type": "empty_output",
                    "severity": "medium", 
                    "message": "Tool succeeded but returned no output"
                })
            
            if quality_score < self.threshold:
                issues.append({
                    "type": "low_quality",
                    "severity": "medium",
                    "message": f"Output quality ({quality_score:.2f}) below threshold"
                })
            
            # Generate recommendations
            recommendations = self._generate_recommendations(tool_name, issues)
            
            # Log evaluation
            eval_result = {
                "tool": tool_name,
                "quality_score": quality_score,
                "issues": issues,
                "recommendations": recommendations,
                "passed": quality_score >= self.threshold and not issues
            }
            self._evaluation_log.append(eval_result)
            
            return {
                "success": True,
                "output": eval_result
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _calculate_quality(self, output: dict, schema: Optional[dict]) -> float:
        """Calculate output quality score."""
        score = 1.0
        
        # Penalize for errors
        if output.get("error"):
            score -= 0.5
        
        # Penalize for empty output
        if not output.get("output"):
            score -= 0.3
        
        # Check against schema if provided
        if schema:
            actual_output = output.get("output", {})
            if isinstance(actual_output, dict):
                missing_keys = set(schema.keys()) - set(actual_output.keys())
                if missing_keys:
                    score -= len(missing_keys) * 0.1
        
        return max(0.0, min(1.0, score))
    
    def _generate_recommendations(self, tool_name: str, 
                                   issues: list) -> list:
        """Generate recommendations based on issues."""
        recommendations = []
        
        for issue in issues:
            if issue["type"] == "execution_failure":
                recommendations.append(
                    f"Retry {tool_name} with adjusted parameters or check dependencies"
                )
            elif issue["type"] == "empty_output":
                recommendations.append(
                    f"Verify {tool_name} configuration and input data"
                )
            elif issue["type"] == "low_quality":
                recommendations.append(
                    f"Review {tool_name} output format and consider alternative approaches"
                )
        
        if not recommendations:
            recommendations.append("No issues detected - output is satisfactory")
        
        return recommendations
    
    def get_evaluation_summary(self) -> dict:
        """Get summary of evaluations."""
        if not self._evaluation_log:
            return {"total": 0, "passed": 0, "average_quality": 0}
        
        total = len(self._evaluation_log)
        passed = sum(1 for e in self._evaluation_log if e["passed"])
        avg_quality = sum(e["quality_score"] for e in self._evaluation_log) / total
        
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 0,
            "average_quality": avg_quality
        }


# Factory functions
def get_reasoning_engine(model=None, max_tokens: int = 4096) -> ReasoningEngine:
    return ReasoningEngine(model=model, max_tokens=max_tokens)


def get_vision_reasoning_bridge(vision_model=None, 
                                 reasoning_model=None) -> VisionReasoningBridge:
    return VisionReasoningBridge(
        vision_model=vision_model,
        reasoning_model=reasoning_model
    )


def get_tool_self_evaluator(threshold: float = 0.7) -> ToolSelfEvaluator:
    return ToolSelfEvaluator(evaluation_threshold=threshold)
