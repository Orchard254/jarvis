"""
Parallel Executor Module
Enables simultaneous tool execution with dependency tracking and resource management.
"""
import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DependencyStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class TaskNode:
    """Represents a single tool execution task within a DAG."""
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    dependencies: Set[str] = field(default_factory=set)
    status: DependencyStatus = DependencyStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def is_ready(self) -> bool:
        """Check if all dependencies are completed."""
        if self.status != DependencyStatus.PENDING:
            return False
        # Dependencies are task_ids that must be completed
        return True  # Logic handled by executor

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class ParallelExecutor:
    """
    Executes multiple tools in parallel while respecting dependency constraints.
    Uses a DAG (Directed Acyclic Graph) approach to schedule tasks.
    """

    def __init__(self, max_concurrency: int = 5):
        self.max_concurrency = max_concurrency
        self.tasks: Dict[str, TaskNode] = {}
        self.execution_order: List[str] = []
        self._semaphore: Optional[asyncio.Semaphore] = None

    def add_task(
        self,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        dependencies: Optional[List[str]] = None
    ) -> None:
        """Add a task to the execution graph."""
        if task_id in self.tasks:
            raise ValueError(f"Task {task_id} already exists")
        
        self.tasks[task_id] = TaskNode(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            dependencies=set(dependencies or [])
        )
        logger.debug(f"Added task {task_id} ({tool_name}) with deps: {dependencies}")

    def _validate_graph(self) -> bool:
        """Detect cycles in the dependency graph."""
        visited = set()
        rec_stack = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            node = self.tasks.get(node_id)
            if node:
                for dep in node.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            
            rec_stack.remove(node_id)
            return False

        for task_id in self.tasks:
            if task_id not in visited:
                if has_cycle(task_id):
                    logger.error(f"Cycle detected in execution graph involving {task_id}")
                    return False
        return True

    def _get_ready_tasks(self) -> List[TaskNode]:
        """Identify tasks that are pending and have all dependencies met."""
        ready = []
        for task in self.tasks.values():
            if task.status != DependencyStatus.PENDING:
                continue
            
            # Check if all dependencies are completed successfully
            deps_met = all(
                self.tasks.get(dep_id, TaskNode("", "", {})).status == DependencyStatus.COMPLETED
                for dep_id in task.dependencies
            )
            
            # Check if any dependency failed (fail fast)
            deps_failed = any(
                self.tasks.get(dep_id, TaskNode("", "", {})).status == DependencyStatus.FAILED
                for dep_id in task.dependencies
            )

            if deps_failed:
                task.status = DependencyStatus.BLOCKED
                task.error = "Blocked by failed dependency"
                continue
            
            if deps_met:
                ready.append(task)
        
        return ready

    async def _execute_task(
        self, 
        task: TaskNode, 
        tool_registry: Any, 
        progress_callback: Optional[Callable] = None
    ) -> None:
        """Execute a single task."""
        task.status = DependencyStatus.RUNNING
        task.started_at = time.time()
        
        logger.info(f"Executing task {task.task_id}: {task.tool_name}")
        if progress_callback:
            callback_result = progress_callback("start", task)
            if asyncio.iscoroutine(callback_result):
                await callback_result

        try:
            # Resolve tool from registry
            if not hasattr(tool_registry, 'get_tool'):
                raise ValueError("Invalid tool registry")
            
            tool = tool_registry.get_tool(task.tool_name)
            if not tool:
                raise ValueError(f"Tool {task.tool_name} not found")

            # Execute tool
            result = await tool.execute(**task.arguments)
            
            task.result = result
            task.status = DependencyStatus.COMPLETED
            logger.info(f"Task {task.task_id} completed successfully")
            
        except Exception as e:
            task.error = str(e)
            task.status = DependencyStatus.FAILED
            logger.error(f"Task {task.task_id} failed: {e}", exc_info=True)
        
        finally:
            task.completed_at = time.time()
            if progress_callback:
                callback_result = progress_callback("end", task)
                if asyncio.iscoroutine(callback_result):
                    await callback_result

    async def execute_all(
        self, 
        tool_registry: Any, 
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute all added tasks respecting dependencies and concurrency limits.
        Returns a map of task_id -> result.
        """
        if not self._validate_graph():
            raise RuntimeError("Invalid execution graph: Cycle detected")

        if not self.tasks:
            return {}

        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        running_tasks: Set[asyncio.Task] = set()

        while True:
            # Get tasks ready to run
            ready_tasks = self._get_ready_tasks()
            
            # Schedule new tasks up to concurrency limit
            for task in ready_tasks:
                if len(running_tasks) >= self.max_concurrency:
                    break
                
                async def wrapped_exec(t):
                    async with self._semaphore:
                        await self._execute_task(t, tool_registry, progress_callback)
                
                coro = wrapped_exec(task)
                async_task = asyncio.create_task(coro)
                running_tasks.add(async_task)
                async_task.add_done_callback(lambda t: running_tasks.discard(t))

            # If nothing is running and nothing is ready, we are done or stuck
            if not running_tasks:
                pending_count = sum(1 for t in self.tasks.values() if t.status == DependencyStatus.PENDING)
                if pending_count > 0:
                    logger.warning(f"{pending_count} tasks remain pending (possible missing dependencies)")
                break

            # Wait for at least one task to complete
            done, running_tasks = await asyncio.wait(
                running_tasks, 
                return_when=asyncio.FIRST_COMPLETED
            )

        # Compile results
        results = {}
        for task_id, task in self.tasks.items():
            results[task_id] = {
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "duration": task.duration
            }
        
        return results

    def get_execution_plan(self) -> List[Dict[str, Any]]:
        """Return a static analysis of the execution plan."""
        plan = []
        for task in self.tasks.values():
            plan.append({
                "id": task.task_id,
                "tool": task.tool_name,
                "deps": list(task.dependencies),
                "estimated_parallel_group": 0 # Could be calculated with topological sort levels
            })
        return plan
