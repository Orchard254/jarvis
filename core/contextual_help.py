"""
Contextual Help System for JARVIS Phase 4.
Analyzes current task state to suggest relevant commands.
Detects stuck states and offers proactive help.
"""
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class HelpTrigger(Enum):
    """Triggers that can activate contextual help."""
    USER_REQUEST = "user_request"
    ERROR_DETECTED = "error_detected"
    STUCK_STATE = "stuck_state"
    REPEATED_FAILURE = "repeated_failure"
    CAPABILITY_DISCOVERY = "capability_discovery"
    MILESTONE_REACHED = "milestone_reached"


@dataclass
class HelpSuggestion:
    """Represents a contextual help suggestion."""
    trigger: HelpTrigger
    message: str
    suggested_actions: List[str]
    confidence: float  # 0.0 to 1.0
    context_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.context_data is None:
            self.context_data = {}
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "trigger": self.trigger.value,
            "message": self.message,
            "suggested_actions": self.suggested_actions,
            "confidence": self.confidence,
            "context_data": self.context_data
        }


class ContextualHelpEngine:
    """
    Provides context-aware help suggestions based on task state.
    Maintains a library of hints and detects patterns requiring assistance.
    """
    
    def __init__(self):
        self._hint_library = self._build_hint_library()
        self._error_patterns = self._build_error_patterns()
        self._capability_hints = self._build_capability_hints()
        self._failure_counts: Dict[str, int] = {}
        self._last_context: Dict[str, Any] = {}
        logger.info("ContextualHelpEngine initialized")
    
    def _build_hint_library(self) -> Dict[str, Dict[str, Any]]:
        """Build the library of contextual hints."""
        return {
            "file_not_found": {
                "triggers": ["FileNotFoundError", "ENOENT", "no such file"],
                "message": "I couldn't find the specified file.",
                "suggestions": [
                    "Would you like me to search for similar files?",
                    "Should I check the current directory structure?",
                    "Would you prefer to provide the full path?"
                ],
                "actions": ["search_files", "list_directory", "request_path"]
            },
            "permission_denied": {
                "triggers": ["PermissionError", "EACCES", "permission denied"],
                "message": "I don't have permission to access this resource.",
                "suggestions": [
                    "Would you like me to try with elevated privileges?",
                    "Should I suggest an alternative location?",
                    "Would you like to check file permissions?"
                ],
                "actions": ["check_permissions", "suggest_alternative", "request_elevation"]
            },
            "network_timeout": {
                "triggers": ["timeout", "connection timed out", "ETIMEDOUT"],
                "message": "The network request timed out.",
                "suggestions": [
                    "Would you like me to retry with a longer timeout?",
                    "Should I check network connectivity first?",
                    "Would you prefer to use a cached version if available?"
                ],
                "actions": ["retry_with_backoff", "check_network", "use_cache"]
            },
            "rate_limit": {
                "triggers": ["rate limit", "too many requests", "429"],
                "message": "We've hit a rate limit on this service.",
                "suggestions": [
                    "Would you like me to wait and retry automatically?",
                    "Should I switch to a different API endpoint?",
                    "Would you like to continue with reduced frequency?"
                ],
                "actions": ["wait_and_retry", "switch_endpoint", "throttle_requests"]
            },
            "parse_error": {
                "triggers": ["JSONDecodeError", "parse error", "invalid syntax"],
                "message": "I encountered an error parsing the data.",
                "suggestions": [
                    "Would you like me to try a different parsing approach?",
                    "Should I show you the raw data for inspection?",
                    "Would you like to specify a different format?"
                ],
                "actions": ["try_alternative_parser", "show_raw_data", "change_format"]
            },
            "memory_pressure": {
                "triggers": ["MemoryError", "out of memory", "OOM"],
                "message": "The operation requires more memory than available.",
                "suggestions": [
                    "Would you like me to process the data in smaller chunks?",
                    "Should I use a more memory-efficient algorithm?",
                    "Would you prefer to work with a subset of the data?"
                ],
                "actions": ["chunk_processing", "optimize_memory", "filter_data"]
            },
            "api_error": {
                "triggers": ["APIError", "HTTP 5", "server error"],
                "message": "The external service encountered an error.",
                "suggestions": [
                    "Would you like me to retry the request?",
                    "Should I try an alternative service?",
                    "Would you like to check the service status?"
                ],
                "actions": ["retry_request", "use_alternative", "check_status"]
            },
            "ambiguous_request": {
                "triggers": ["unclear", "ambiguous", "multiple matches"],
                "message": "Your request could be interpreted multiple ways.",
                "suggestions": [
                    "Could you clarify which option you prefer?",
                    "Would you like me to list all possibilities?",
                    "Should I proceed with the most common interpretation?"
                ],
                "actions": ["request_clarification", "list_options", "use_default"]
            }
        }
    
    def _build_error_patterns(self) -> Dict[str, List[str]]:
        """Build error pattern matching rules."""
        return {
            "file_not_found": ["FileNotFoundError", "ENOENT", "no such file or directory"],
            "permission_denied": ["PermissionError", "EACCES", "permission denied", "access denied"],
            "network_timeout": ["timeout", "timed out", "ETIMEDOUT", "connection reset"],
            "rate_limit": ["rate limit", "too many requests", "429", "quota exceeded"],
            "parse_error": ["JSONDecodeError", "XMLParseError", "invalid JSON", "parse error"],
            "memory_pressure": ["MemoryError", "out of memory", "cannot allocate memory"],
            "api_error": ["HTTP 5", "502", "503", "504", "Internal Server Error"],
        }
    
    def _build_capability_hints(self) -> List[Dict[str, Any]]:
        """Build capability discovery hints."""
        return [
            {
                "context": "file_operations",
                "keywords": ["file", "read", "write", "save", "load"],
                "hint": "I can also search for files, watch directories for changes, or convert between formats.",
                "capabilities": ["file_search", "directory_watch", "format_conversion"]
            },
            {
                "context": "web_operations",
                "keywords": ["url", "website", "download", "fetch", "scrape"],
                "hint": "I can handle authentication, follow redirects, and extract structured data from web pages.",
                "capabilities": ["auth_handling", "redirect_following", "data_extraction"]
            },
            {
                "context": "code_operations",
                "keywords": ["code", "run", "execute", "test", "debug"],
                "hint": "I can run code in isolated environments, generate tests, or explain complex code sections.",
                "capabilities": ["sandboxed_execution", "test_generation", "code_explanation"]
            },
            {
                "context": "data_analysis",
                "keywords": ["analyze", "plot", "chart", "statistics", "data"],
                "hint": "I can create visualizations, perform statistical analysis, or export results in various formats.",
                "capabilities": ["visualization", "statistical_analysis", "export_formats"]
            },
            {
                "context": "automation",
                "keywords": ["automate", "schedule", "repeat", "cron", "workflow"],
                "hint": "I can set up scheduled tasks, create workflows, or monitor for specific conditions.",
                "capabilities": ["task_scheduling", "workflow_creation", "condition_monitoring"]
            }
        ]
    
    def analyze_error(self, error_message: str, 
                     context: Optional[Dict[str, Any]] = None) -> Optional[HelpSuggestion]:
        """
        Analyze an error message and provide contextual help.
        
        Args:
            error_message: The error message to analyze
            context: Additional context about the error
        
        Returns:
            HelpSuggestion if a matching pattern is found, None otherwise
        """
        error_lower = error_message.lower()
        
        for hint_key, hint_data in self._hint_library.items():
            for trigger in hint_data["triggers"]:
                if trigger.lower() in error_lower:
                    logger.debug(f"Matched error pattern: {hint_key}")
                    return HelpSuggestion(
                        trigger=HelpTrigger.ERROR_DETECTED,
                        message=hint_data["message"],
                        suggested_actions=hint_data["suggestions"],
                        confidence=0.8,
                        context_data={
                            "error_type": hint_key,
                            "original_error": error_message,
                            **(context or {})
                        }
                    )
        
        return None
    
    def detect_stuck_state(self, task_state: Dict[str, Any]) -> Optional[HelpSuggestion]:
        """
        Detect if a task appears to be stuck and offer help.
        
        Args:
            task_state: Current state of the task
        
        Returns:
            HelpSuggestion if stuck state detected, None otherwise
        """
        # Check for repeated failures on same step
        step_name = task_state.get("current_step", "")
        failure_count = self._failure_counts.get(step_name, 0)
        
        if failure_count >= 3:
            return HelpSuggestion(
                trigger=HelpTrigger.STUCK_STATE,
                message=f"I notice we've had difficulty with '{step_name}' multiple times.",
                suggested_actions=[
                    "Would you like me to try a completely different approach?",
                    "Should we skip this step and continue with the rest?",
                    "Would you like to manually provide the expected output?"
                ],
                confidence=0.9,
                context_data={
                    "step_name": step_name,
                    "failure_count": failure_count,
                    "total_time": task_state.get("elapsed_seconds", 0)
                }
            )
        
        # Check for long-running operations without progress
        elapsed = task_state.get("elapsed_seconds", 0)
        last_update = task_state.get("seconds_since_last_update", 0)
        
        if last_update > 120 and elapsed > 180:
            return HelpSuggestion(
                trigger=HelpTrigger.STUCK_STATE,
                message="It seems like the task hasn't made progress recently.",
                suggested_actions=[
                    "Would you like me to provide a detailed status update?",
                    "Should I check for any blocking conditions?",
                    "Would you like to pause and resume later?"
                ],
                confidence=0.7,
                context_data={
                    "elapsed_seconds": elapsed,
                    "idle_seconds": last_update
                }
            )
        
        return None
    
    def record_failure(self, step_name: str):
        """Record a failure for a specific step."""
        self._failure_counts[step_name] = self._failure_counts.get(step_name, 0) + 1
        logger.debug(f"Recorded failure for step {step_name}: count={self._failure_counts[step_name]}")
    
    def reset_failures(self, step_name: Optional[str] = None):
        """Reset failure counts."""
        if step_name:
            self._failure_counts.pop(step_name, None)
        else:
            self._failure_counts.clear()
    
    def get_capability_hint(self, context_keywords: List[str]) -> Optional[HelpSuggestion]:
        """
        Get capability discovery hints based on context keywords.
        
        Args:
            context_keywords: Keywords describing current context
        
        Returns:
            HelpSuggestion with capability hints if applicable
        """
        context_lower = [k.lower() for k in context_keywords]
        
        for hint in self._capability_hints:
            matching_keywords = sum(1 for kw in context_lower 
                                   if any(hint_kw in kw for hint_kw in hint["keywords"]))
            
            if matching_keywords >= 2:  # At least 2 keyword matches
                return HelpSuggestion(
                    trigger=HelpTrigger.CAPABILITY_DISCOVERY,
                    message=hint["hint"],
                    suggested_actions=[
                        f"Tell me more about {cap.replace('_', ' ')}"
                        for cap in hint["capabilities"][:3]
                    ],
                    confidence=0.6,
                    context_data={
                        "matched_context": hint["context"],
                        "available_capabilities": hint["capabilities"]
                    }
                )
        
        return None
    
    def get_milestone_hint(self, milestone_name: str) -> Optional[HelpSuggestion]:
        """
        Get hints appropriate for reaching a milestone.
        
        Args:
            milestone_name: Name of the achieved milestone
        
        Returns:
            HelpSuggestion with next-step guidance
        """
        milestone_hints = {
            "files_read": {
                "message": "I've finished reading the files.",
                "suggestions": [
                    "Would you like me to summarize the contents?",
                    "Should I proceed with analysis?",
                    "Would you like to specify what to do next?"
                ]
            },
            "analysis_complete": {
                "message": "Analysis is complete.",
                "suggestions": [
                    "Would you like to see a detailed report?",
                    "Should I create visualizations of the findings?",
                    "Would you like to export the results?"
                ]
            },
            "code_executed": {
                "message": "Code execution completed successfully.",
                "suggestions": [
                    "Would you like to see the output?",
                    "Should I save the results to a file?",
                    "Would you like to modify and re-run?"
                ]
            },
            "download_complete": {
                "message": "Download finished.",
                "suggestions": [
                    "Would you like me to verify the downloaded content?",
                    "Should I extract/process the downloaded files?",
                    "Would you like to organize them in a specific way?"
                ]
            }
        }
        
        hint_data = milestone_hints.get(milestone_name)
        if hint_data:
            return HelpSuggestion(
                trigger=HelpTrigger.MILESTONE_REACHED,
                message=hint_data["message"],
                suggested_actions=hint_data["suggestions"],
                confidence=0.85,
                context_data={"milestone": milestone_name}
            )
        
        return None
    
    def get_help_for_context(self, task_state: Dict[str, Any],
                            explicit_request: bool = False) -> List[HelpSuggestion]:
        """
        Get all relevant help suggestions for current context.
        
        Args:
            task_state: Current task state
            explicit_request: Whether user explicitly requested help
        
        Returns:
            List of HelpSuggestion objects, ordered by confidence
        """
        suggestions = []
        
        if explicit_request:
            # User asked for help - provide comprehensive options
            suggestions.append(HelpSuggestion(
                trigger=HelpTrigger.USER_REQUEST,
                message="Here are some things I can help you with:",
                suggested_actions=[
                    "Explain current progress",
                    "Show available commands",
                    "Describe what I'm doing",
                    "Provide troubleshooting options"
                ],
                confidence=1.0,
                context_data=task_state
            ))
        
        # Check for errors in task state
        if "error" in task_state:
            error_hint = self.analyze_error(task_state["error"], task_state)
            if error_hint:
                suggestions.append(error_hint)
        
        # Check for stuck state
        stuck_hint = self.detect_stuck_state(task_state)
        if stuck_hint:
            suggestions.append(stuck_hint)
        
        # Sort by confidence (highest first)
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        
        return suggestions[:3]  # Return top 3 suggestions


# Global instance
contextual_help = ContextualHelpEngine()
