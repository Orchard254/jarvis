"""
Contextual Help System for JARVIS.
Provides proactive suggestions, error recovery hints, and capability discovery.
"""
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import re


class HelpTriggerType(Enum):
    """Types of triggers for contextual help."""
    CONTEXT_BASED = "context_based"
    ERROR_DETECTED = "error_detected"
    STUCK_STATE = "stuck_state"
    USER_QUESTION = "user_question"
    CAPABILITY_DISCOVERY = "capability_discovery"
    MILESTONE_REACHED = "milestone_reached"


@dataclass
class HelpSuggestion:
    """Represents a contextual help suggestion."""
    title: str
    message: str
    trigger_type: HelpTriggerType
    priority: int = 50  # 1-100, higher = more urgent
    action_suggestions: List[str] = field(default_factory=list)
    context_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "message": self.message,
            "trigger_type": self.trigger_type.value,
            "priority": self.priority,
            "action_suggestions": self.action_suggestions,
            "context_data": self.context_data
        }


class ContextAnalyzer:
    """
    Analyzes current task state to determine context for help suggestions.
    """
    
    def __init__(self):
        self._context_patterns: Dict[str, List[str]] = {
            "file_operations": ["read", "write", "file", "path", "directory", "folder"],
            "code_execution": ["run", "execute", "python", "script", "code"],
            "network": ["download", "upload", "http", "url", "api", "request"],
            "installation": ["install", "pip", "npm", "package", "dependency"],
            "debugging": ["error", "bug", "issue", "problem", "fail", "exception"],
            "testing": ["test", "pytest", "unittest", "spec", "coverage"],
            "build": ["build", "compile", "bundle", "webpack", "make"],
            "git": ["git", "commit", "push", "pull", "branch", "merge"],
        }
    
    def analyze(self, current_step: str, recent_logs: List[str],
                error_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze current context to determine relevant help categories.
        
        Returns:
            Dictionary with detected contexts, confidence scores, and metadata
        """
        contexts = {}
        all_text = (current_step + " " + " ".join(recent_logs)).lower()
        
        for context_name, keywords in self._context_patterns.items():
            matches = sum(1 for kw in keywords if kw in all_text)
            if matches > 0:
                confidence = min(1.0, matches / len(keywords))
                contexts[context_name] = {
                    "confidence": confidence,
                    "match_count": matches,
                    "matched_keywords": [kw for kw in keywords if kw in all_text]
                }
        
        # Detect error state
        has_error = error_message is not None or any(
            word in all_text for word in ["error", "failed", "exception", "traceback"]
        )
        
        return {
            "contexts": contexts,
            "has_error": has_error,
            "error_message": error_message,
            "primary_context": max(contexts.items(), key=lambda x: x[1]["confidence"])[0] if contexts else None,
            "step_description": current_step
        }


class HintLibrary:
    """
    Maintains a library of context-aware hints and suggestions.
    """
    
    def __init__(self):
        self._hints: Dict[str, List[Dict[str, Any]]] = {
            "file_operations": [
                {
                    "trigger": "file_not_found",
                    "title": "File Not Found",
                    "message": "The specified file path doesn't exist. Would you like me to:",
                    "suggestions": [
                        "Search for similar files in the directory",
                        "Check if the file extension is correct",
                        "Create the file if it should be new",
                        "List contents of the parent directory"
                    ]
                },
                {
                    "trigger": "permission_denied",
                    "title": "Permission Issue Detected",
                    "message": "I don't have permission to access this file. I can:",
                    "suggestions": [
                        "Try running with elevated permissions",
                        "Check file ownership",
                        "Use an alternative location",
                        "Show available files I can access"
                    ]
                },
                {
                    "trigger": "general",
                    "title": "File Operations Help",
                    "message": "I can help you with file operations:",
                    "suggestions": [
                        "Read/write files",
                        "Search for files by name or content",
                        "List directory contents",
                        "Copy, move, or delete files"
                    ]
                }
            ],
            "code_execution": [
                {
                    "trigger": "syntax_error",
                    "title": "Syntax Error Detected",
                    "message": "There's a syntax error in the code. I can:",
                    "suggestions": [
                        "Highlight the specific error location",
                        "Explain what went wrong",
                        "Suggest a fix",
                        "Run a linter to find other issues"
                    ]
                },
                {
                    "trigger": "runtime_error",
                    "title": "Runtime Error Occurred",
                    "message": "The code ran but encountered an error. Options:",
                    "suggestions": [
                        "Show the full stack trace",
                        "Add debugging statements",
                        "Run in a sandboxed environment",
                        "Check input values and dependencies"
                    ]
                },
                {
                    "trigger": "timeout",
                    "title": "Execution Timeout",
                    "message": "The code took too long to execute. Consider:",
                    "suggestions": [
                        "Optimizing the algorithm",
                        "Adding progress indicators",
                        "Breaking into smaller chunks",
                        "Running asynchronously"
                    ]
                },
                {
                    "trigger": "general",
                    "title": "Code Execution Capabilities",
                    "message": "I can execute code in various ways:",
                    "suggestions": [
                        "Run Python scripts",
                        "Execute shell commands",
                        "Test code snippets",
                        "Profile performance"
                    ]
                }
            ],
            "network": [
                {
                    "trigger": "connection_failed",
                    "title": "Network Connection Failed",
                    "message": "Unable to connect. Let me help troubleshoot:",
                    "suggestions": [
                        "Check internet connectivity",
                        "Verify the URL/endpoint",
                        "Try alternative DNS servers",
                        "Check firewall settings"
                    ]
                },
                {
                    "trigger": "timeout",
                    "title": "Request Timed Out",
                    "message": "The network request timed out. Options:",
                    "suggestions": [
                        "Increase timeout duration",
                        "Retry with exponential backoff",
                        "Check server status",
                        "Use a cached response if available"
                    ]
                },
                {
                    "trigger": "general",
                    "title": "Network Operations",
                    "message": "I can handle various network tasks:",
                    "suggestions": [
                        "Download/upload files",
                        "Make API requests",
                        "Check website availability",
                        "Monitor network status"
                    ]
                }
            ],
            "installation": [
                {
                    "trigger": "package_not_found",
                    "title": "Package Not Found",
                    "message": "The package couldn't be found. Try:",
                    "suggestions": [
                        "Check the package name spelling",
                        "Search in alternative repositories",
                        "Update package manager cache",
                        "Install from source"
                    ]
                },
                {
                    "trigger": "dependency_conflict",
                    "title": "Dependency Conflict",
                    "message": "There's a version conflict. Solutions:",
                    "suggestions": [
                        "Show conflicting packages",
                        "Create isolated virtual environment",
                        "Use compatible versions",
                        "Update all dependencies"
                    ]
                },
                {
                    "trigger": "general",
                    "title": "Installation Help",
                    "message": "I can manage package installations:",
                    "suggestions": [
                        "Install from PyPI, npm, etc.",
                        "Manage virtual environments",
                        "Resolve dependency conflicts",
                        "List installed packages"
                    ]
                }
            ],
            "debugging": [
                {
                    "trigger": "repeated_failure",
                    "title": "Repeated Failures Detected",
                    "message": "This operation has failed multiple times. Let's try:",
                    "suggestions": [
                        "Approach the problem differently",
                        "Break down into smaller steps",
                        "Gather more diagnostic information",
                        "Consult documentation or search online"
                    ]
                },
                {
                    "trigger": "unclear_error",
                    "title": "Unclear Error Message",
                    "message": "The error message isn't very helpful. I can:",
                    "suggestions": [
                        "Search for similar errors online",
                        "Add more logging to understand the issue",
                        "Isolate the problematic code",
                        "Try a minimal reproduction"
                    ]
                },
                {
                    "trigger": "general",
                    "title": "Debugging Assistance",
                    "message": "I can help debug issues:",
                    "suggestions": [
                        "Analyze error messages",
                        "Add strategic print statements",
                        "Use debugger tools",
                        "Review logs systematically"
                    ]
                }
            ],
            "stuck_state": [
                {
                    "trigger": "no_progress",
                    "title": "Task Seems Stuck",
                    "message": "It looks like we're not making progress. Would you like to:",
                    "suggestions": [
                        "Skip this step and continue",
                        "Try an alternative approach",
                        "Get more details about what's blocking",
                        "Cancel and restart with different parameters"
                    ]
                }
            ],
            "capability_discovery": [
                {
                    "trigger": "idle",
                    "title": "Available Capabilities",
                    "message": "Here are things I can help you with:",
                    "suggestions": [
                        "File management and organization",
                        "Code writing and execution",
                        "System automation tasks",
                        "Information retrieval and research",
                        "Application management"
                    ]
                }
            ]
        }
    
    def get_hints(self, context: str, trigger: str = "general") -> List[Dict[str, Any]]:
        """Get hints for a specific context and trigger."""
        context_hints = self._hints.get(context, [])
        
        # Find matching trigger
        for hint in context_hints:
            if hint["trigger"] == trigger:
                return [hint]
        
        # Fall back to general hints for this context
        for hint in context_hints:
            if hint["trigger"] == "general":
                return [hint]
        
        # No hints found
        return []
    
    def get_all_capabilities(self) -> List[str]:
        """Get list of all available capabilities."""
        capabilities = []
        for context_hints in self._hints.values():
            for hint in context_hints:
                if hint["trigger"] == "general":
                    capabilities.extend(hint.get("suggestions", []))
        return list(set(capabilities))


class ContextualHelpSystem:
    """
    Main contextual help system that coordinates analysis and suggestions.
    
    Features:
    - Proactive suggestions based on current context
    - Error recovery hints for common problems
    - Capability discovery when user seems stuck
    - Priority-based suggestion ranking
    """
    
    def __init__(self):
        self._analyzer = ContextAnalyzer()
        self._hint_library = HintLibrary()
        self._error_patterns: Dict[str, List[str]] = {
            "file_not_found": ["no such file", "file not found", "doesn't exist"],
            "permission_denied": ["permission denied", "access denied", "forbidden"],
            "syntax_error": ["syntaxerror", "invalid syntax"],
            "runtime_error": ["runtimeerror", "exception", "traceback"],
            "connection_failed": ["connection refused", "network unreachable", "dns resolution failed"],
            "timeout": ["timed out", "deadline exceeded"],
            "package_not_found": ["no module named", "package not found", "404 not found"],
            "dependency_conflict": ["version conflict", "incompatible", "requires"],
        }
        self._recent_suggestions: List[HelpSuggestion] = []
        self._suggestion_cooldown_seconds: float = 30
    
    def analyze_and_suggest(self, current_step: str, recent_logs: List[str],
                            error_message: Optional[str] = None,
                            is_stuck: bool = False) -> List[HelpSuggestion]:
        """
        Analyze current state and generate contextual help suggestions.
        
        Args:
            current_step: Description of current task step
            recent_logs: Recent log entries
            error_message: Optional error message if one occurred
            is_stuck: Whether the task appears to be stuck
            
        Returns:
            List of HelpSuggestion objects, sorted by priority
        """
        suggestions = []
        
        # Analyze context
        context_info = self._analyzer.analyze(current_step, recent_logs, error_message)
        
        # Check for specific error patterns
        detected_error = self._detect_error_pattern(error_message or "")
        
        # Generate suggestions based on error detection
        if detected_error and context_info["primary_context"]:
            hints = self._hint_library.get_hints(
                context_info["primary_context"], 
                detected_error
            )
            for hint in hints:
                suggestions.append(HelpSuggestion(
                    title=hint["title"],
                    message=hint["message"],
                    trigger_type=HelpTriggerType.ERROR_DETECTED,
                    priority=80,
                    action_suggestions=hint.get("suggestions", []),
                    context_data={"error_type": detected_error}
                ))
        
        # Generate suggestions for stuck state
        if is_stuck:
            hints = self._hint_library.get_hints("stuck_state", "no_progress")
            for hint in hints:
                suggestions.append(HelpSuggestion(
                    title=hint["title"],
                    message=hint["message"],
                    trigger_type=HelpTriggerType.STUCK_STATE,
                    priority=70,
                    action_suggestions=hint.get("suggestions", [])
                ))
        
        # Generate context-based suggestions (lower priority)
        if context_info["primary_context"] and not suggestions:
            hints = self._hint_library.get_hints(context_info["primary_context"])
            for hint in hints:
                suggestions.append(HelpSuggestion(
                    title=hint["title"],
                    message=hint["message"],
                    trigger_type=HelpTriggerType.CONTEXT_BASED,
                    priority=40,
                    action_suggestions=hint.get("suggestions", []),
                    context_data={"context": context_info["primary_context"]}
                ))
        
        # Sort by priority (descending)
        suggestions.sort(key=lambda s: s.priority, reverse=True)
        
        # Store recent suggestion for cooldown tracking
        self._recent_suggestions.extend(suggestions)
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def _detect_error_pattern(self, error_message: str) -> Optional[str]:
        """Detect specific error pattern from error message."""
        error_lower = error_message.lower()
        
        for pattern_name, keywords in self._error_patterns.items():
            if any(kw in error_lower for kw in keywords):
                return pattern_name
        
        return None
    
    def get_capability_suggestions(self) -> List[HelpSuggestion]:
        """Get capability discovery suggestions."""
        hints = self._hint_library.get_hints("capability_discovery", "idle")
        suggestions = []
        
        for hint in hints:
            suggestions.append(HelpSuggestion(
                title=hint["title"],
                message=hint["message"],
                trigger_type=HelpTriggerType.CAPABILITY_DISCOVERY,
                priority=20,
                action_suggestions=hint.get("suggestions", [])
            ))
        
        return suggestions
    
    def should_show_suggestion(self, suggestion: HelpSuggestion) -> bool:
        """
        Check if a suggestion should be shown (respecting cooldown).
        
        Prevents showing the same suggestion type repeatedly.
        """
        import time
        current_time = time.time()
        
        # Check cooldown for similar suggestions
        for recent in self._recent_suggestions:
            if (recent.title == suggestion.title and 
                current_time - getattr(recent, '_created_at', 0) < self._suggestion_cooldown_seconds):
                return False
        
        return True
    
    def clear_history(self):
        """Clear suggestion history."""
        self._recent_suggestions.clear()


# Global instance
contextual_help = ContextualHelpSystem()
