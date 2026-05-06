"""
1. Core Orchestration (4 tools)
Controls decision flow and system state.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: str
    confidence: float
    target_capability: Optional[str] = None
    parameters: dict = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class IntentRouter:
    """
    intent_router: Classifies user command → tool routing
    
    Uses GPT-OSS 120B to analyze natural language input and determine
    which capability should handle the request.
    """
    
    def __init__(self, reasoning_model=None):
        self.reasoning_model = reasoning_model
        self._intent_map = {}
    
    def execute(self, user_input: str, context: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Execute intent classification.
        
        Args:
            user_input: The natural language command from user
            context: Optional context about current state
            
        Returns:
            Classification result
        """
        try:
            result = self.classify(user_input, context)
            return {
                "success": True,
                "output": {
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "target_capability": result.target_capability,
                    "parameters": result.parameters
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def classify(self, user_input: str, context: Optional[dict] = None) -> IntentResult:
        """
        Classify user input into an intent and route to appropriate capability.
        
        Args:
            user_input: The natural language command from user
            context: Optional context about current state
            
        Returns:
            IntentResult with classified intent and target capability
        """
        # TODO: Integrate with GPT-OSS 120B for actual classification
        logger.info(f"Classifying intent: {user_input[:50]}...")
        
        # Placeholder logic - will be replaced by model inference
        intent = self._infer_intent(user_input)
        target = self._route_to_capability(intent)
        
        return IntentResult(
            intent=intent,
            confidence=0.95,
            target_capability=target,
            parameters=self._extract_parameters(user_input)
        )
    
    def _infer_intent(self, text: str) -> str:
        """Infer intent from text (placeholder for model)."""
        text_lower = text.lower()
        if any(word in text_lower for word in ["open", "launch", "start"]):
            return "launch_application"
        elif any(word in text_lower for word in ["close", "quit", "exit"]):
            return "close_application"
        elif any(word in text_lower for word in ["search", "find", "look up"]):
            return "search_information"
        elif any(word in text_lower for word in ["write", "create", "save"]):
            return "create_content"
        else:
            return "general_query"
    
    def _route_to_capability(self, intent: str) -> Optional[str]:
        """Map intent to capability."""
        # This will be populated during registration
        return self._intent_map.get(intent)
    
    def register_intent_mapping(self, intent: str, capability: str):
        """Register mapping between intent and capability."""
        self._intent_map[intent] = capability
    
    def _extract_parameters(self, text: str) -> dict:
        """Extract parameters from text (placeholder)."""
        return {"raw_input": text}


@dataclass
class TaskStep:
    """A single step in a task plan."""
    step_id: int
    description: str
    capability: str
    parameters: dict
    dependencies: list = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass 
class TaskPlan:
    """Complete plan for accomplishing a goal."""
    goal: str
    steps: list[TaskStep]
    estimated_duration: Optional[float] = None


class TaskPlanner:
    """
    task_planner: Breaks goal into steps
    
    Uses GPT-OSS 120B to decompose complex goals into executable steps
    using available capabilities.
    """
    
    def __init__(self, available_capabilities: list[str]):
        self.available_capabilities = available_capabilities
    
    def execute(self, goal: str, context: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Execute task planning.
        
        Args:
            goal: The high-level goal to accomplish
            context: Optional context about current state
            
        Returns:
            Planning result with steps
        """
        try:
            plan = self.plan(goal, context)
            return {
                "success": True,
                "output": {
                    "goal": plan.goal,
                    "steps": [
                        {
                            "step_id": s.step_id,
                            "description": s.description,
                            "capability": s.capability,
                            "parameters": s.parameters,
                            "dependencies": s.dependencies
                        }
                        for s in plan.steps
                    ],
                    "estimated_duration": plan.estimated_duration
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def plan(self, goal: str, context: Optional[dict] = None) -> TaskPlan:
        """
        Decompose a goal into executable steps.
        
        Args:
            goal: The high-level goal to accomplish
            context: Optional context about current state
            
        Returns:
            TaskPlan with ordered steps
        """
        logger.info(f"Planning task: {goal[:50]}...")
        
        # TODO: Integrate with GPT-OSS 120B for planning
        steps = self._decompose_goal(goal)
        
        return TaskPlan(
            goal=goal,
            steps=steps,
            estimated_duration=len(steps) * 5.0  # Estimate 5 sec per step
        )
    
    def _decompose_goal(self, goal: str) -> list[TaskStep]:
        """Decompose goal into steps (placeholder for model)."""
        # Simple heuristic decomposition
        return [
            TaskStep(
                step_id=1,
                description=f"Analyze: {goal}",
                capability="reasoning_engine",
                parameters={"query": goal}
            )
        ]


class ToolDispatcher:
    """
    tool_dispatcher: Executes selected tool
    
    Routes execution requests to the appropriate capability implementation
    with proper error handling and result validation.
    """
    
    def __init__(self):
        self._tools = {}
        self._execution_log = []
    
    def register_tool(self, name: str, tool_instance: Any):
        """Register a tool for dispatch."""
        self._tools[name] = tool_instance
        logger.info(f"Registered tool: {name}")
    
    def execute(self, tool_name: str, parameters: dict, timeout: float = 30.0) -> dict:
        """
        Execute a tool with given parameters.
        
        Args:
            tool_name: Name of the capability to execute
            parameters: Parameters to pass to the tool
            timeout: Maximum execution time in seconds
            
        Returns:
            Execution result with status and output
        """
        if tool_name not in self._tools:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found",
                "output": None
            }
        
        logger.info(f"Dispatching to {tool_name}: {parameters}")
        
        try:
            tool = self._tools[tool_name]
            result = tool.execute(**parameters)
            
            self._log_execution(tool_name, parameters, result, success=True)
            
            return {
                "success": True,
                "error": None,
                "output": result
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool execution failed: {tool_name} - {error_msg}")
            
            self._log_execution(tool_name, parameters, {"error": error_msg}, success=False)
            
            return {
                "success": False,
                "error": error_msg,
                "output": None
            }
    
    def _log_execution(self, tool_name: str, params: dict, result: dict, success: bool):
        """Log tool execution for debugging and evaluation."""
        self._execution_log.append({
            "tool": tool_name,
            "parameters": params,
            "result": result,
            "success": success
        })
    
    def get_available_tools(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())


@dataclass
class MemoryEntry:
    """Entry in the memory system."""
    key: str
    value: Any
    timestamp: float
    ttl: Optional[float] = None  # Time to live in seconds
    tags: list = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class MemoryManager:
    """
    memory_manager: Store/retrieve short + long term context
    
    Manages working memory for current session and persistent memory
    for long-term knowledge.
    """
    
    def __init__(self):
        self._short_term = {}  # Session memory
        self._long_term = {}   # Persistent memory
        self._history = []
    
    def execute(self, action: str, key: Optional[str] = None,
                value: Any = None, long_term: bool = False,
                query: Optional[str] = None, tags: Optional[list] = None,
                ttl: Optional[float] = None, **kwargs) -> dict:
        """
        Execute memory operations.
        
        Args:
            action: One of 'store', 'retrieve', 'search', 'clear', 'summary'
            key: Memory key (for store/retrieve)
            value: Value to store
            long_term: Use persistent memory
            query: Search query
            tags: Search tags
            ttl: Time to live in seconds
            
        Returns:
            Operation result
        """
        try:
            if action == "store":
                if not key:
                    return {"success": False, "error": "key required for store"}
                return {"success": True, "output": {"stored": self.store(key, value, long_term, ttl, tags)}}
            
            elif action == "retrieve":
                if not key:
                    return {"success": False, "error": "key required for retrieve"}
                result = self.retrieve(key, long_term)
                return {"success": True, "output": {"key": key, "value": result}}
            
            elif action == "search":
                results = self.search(query or "", tags, long_term)
                return {"success": True, "output": {"results": results, "count": len(results)}}
            
            elif action == "clear":
                self.clear(long_term)
                return {"success": True, "output": {"cleared": "long_term" if long_term else "short_term"}}
            
            elif action == "summary":
                return {"success": True, "output": self.get_summary()}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def store(self, key: str, value: Any, long_term: bool = False, 
              ttl: Optional[float] = None, tags: list = None) -> bool:
        """
        Store a value in memory.
        
        Args:
            key: Unique identifier for the memory
            value: Data to store
            long_term: If True, store in persistent memory
            ttl: Time to live in seconds (None = permanent)
            tags: Optional tags for categorization
            
        Returns:
            True if successful
        """
        import time
        
        entry = MemoryEntry(
            key=key,
            value=value,
            timestamp=time.time(),
            ttl=ttl,
            tags=tags or []
        )
        
        storage = self._long_term if long_term else self._short_term
        storage[key] = entry
        
        self._history.append(("store", key, long_term))
        logger.debug(f"Stored memory: {key} (long_term={long_term})")
        
        return True
    
    def retrieve(self, key: str, long_term: bool = False) -> Optional[Any]:
        """
        Retrieve a value from memory.
        
        Args:
            key: Identifier to look up
            long_term: Search in persistent memory
            
        Returns:
            Value if found, None otherwise
        """
        storage = self._long_term if long_term else self._short_term
        entry = storage.get(key)
        
        if entry is None:
            return None
        
        # Check TTL
        if entry.ttl is not None:
            import time
            if time.time() - entry.timestamp > entry.ttl:
                del storage[key]
                return None
        
        self._history.append(("retrieve", key, long_term))
        return entry.value
    
    def search(self, query: str, tags: Optional[list] = None, 
               long_term: bool = True) -> list[dict]:
        """
        Search memory by content or tags.
        
        Args:
            query: Text to search for in values
            tags: Filter by tags
            long_term: Search in persistent memory
            
        Returns:
            List of matching entries
        """
        storage = self._long_term if long_term else self._short_term
        results = []
        
        for key, entry in storage.items():
            match = False
            
            # Search in value
            if query and query.lower() in str(entry.value).lower():
                match = True
            
            # Search by tags
            if tags and any(tag in entry.tags for tag in tags):
                match = True
            
            if match:
                results.append({
                    "key": key,
                    "value": entry.value,
                    "timestamp": entry.timestamp,
                    "tags": entry.tags
                })
        
        return results
    
    def clear(self, long_term: bool = False):
        """Clear memory."""
        if long_term:
            self._long_term.clear()
        else:
            self._short_term.clear()
        
        logger.info(f"Cleared {'long_term' if long_term else 'short_term'} memory")
    
    def get_summary(self) -> dict:
        """Get summary of memory state."""
        return {
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
            "recent_operations": self._history[-10:]
        }


# Singleton instances for capability registry
_intent_router_instance = None
_task_planner_instance = None
_tool_dispatcher_instance = None
_memory_manager_instance = None


def get_intent_router(reasoning_model=None) -> IntentRouter:
    """Get or create IntentRouter singleton."""
    global _intent_router_instance
    if _intent_router_instance is None:
        _intent_router_instance = IntentRouter(reasoning_model)
    return _intent_router_instance


def get_task_planner(capabilities: list[str]) -> TaskPlanner:
    """Get or create TaskPlanner singleton."""
    global _task_planner_instance
    if _task_planner_instance is None:
        _task_planner_instance = TaskPlanner(capabilities)
    return _task_planner_instance


def get_tool_dispatcher() -> ToolDispatcher:
    """Get or create ToolDispatcher singleton."""
    global _tool_dispatcher_instance
    if _tool_dispatcher_instance is None:
        _tool_dispatcher_instance = ToolDispatcher()
    return _tool_dispatcher_instance


def get_memory_manager() -> MemoryManager:
    """Get or create MemoryManager singleton."""
    global _memory_manager_instance
    if _memory_manager_instance is None:
        _memory_manager_instance = MemoryManager()
    return _memory_manager_instance
