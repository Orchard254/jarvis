"""
Phase 3: Distributed Task Queue & Priority Management

Enables horizontal scaling with distributed task queues,
priority-based scheduling, and load balancing across workers.
"""
import time
import json
import logging
import heapq
import threading
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import os
from collections import defaultdict

logger = logging.getLogger(__name__)

class TaskPriority(Enum):
    CRITICAL = 0  # System-critical, immediate execution
    HIGH = 1      # User-facing, low latency required
    NORMAL = 2    # Default priority
    LOW = 3       # Background tasks, batch operations
    BULK = 4      # Bulk operations, can be delayed

class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass(order=True)
class PrioritizedTask:
    priority: int
    timestamp: float
    task_id: str = field(compare=False)
    skill_name: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)
    status: TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    worker_id: Optional[str] = field(compare=False, default=None)
    retry_count: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)
    created_at: float = field(compare=False, default_factory=time.time)
    started_at: Optional[float] = field(compare=False, default=None)
    completed_at: Optional[float] = field(compare=False, default=None)
    result: Optional[Any] = field(compare=False, default=None)
    error: Optional[str] = field(compare=False, default=None)
    
    def to_dict(self) -> dict:
        d = {
            'task_id': self.task_id,
            'priority': self.priority,
            'skill_name': self.skill_name,
            'payload': self.payload,
            'status': self.status.value,
            'worker_id': self.worker_id,
            'retry_count': self.retry_count,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'error': self.error
        }
        if self.result is not None:
            try:
                d['result'] = str(self.result)[:500]  # Truncate large results
            except:
                d['result'] = "<non-serializable>"
        return d

class PriorityQueue:
    """Thread-safe priority queue implementation."""
    
    def __init__(self):
        self._heap: List[PrioritizedTask] = []
        self._lock = threading.Lock()
        self._task_index: Dict[str, PrioritizedTask] = {}
        
    def push(self, task: PrioritizedTask):
        with self._lock:
            heapq.heappush(self._heap, task)
            self._task_index[task.task_id] = task
            
    def pop(self) -> Optional[PrioritizedTask]:
        with self._lock:
            while self._heap:
                task = heapq.heappop(self._heap)
                if task.task_id in self._task_index:
                    del self._task_index[task.task_id]
                    return task
            return None
            
    def peek(self) -> Optional[PrioritizedTask]:
        with self._lock:
            return self._heap[0] if self._heap else None
            
    def remove(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._task_index:
                del self._task_index[task_id]
                return True
            return False
            
    def update_priority(self, task_id: str, new_priority: int):
        """Update priority of a pending task."""
        with self._lock:
            if task_id in self._task_index:
                task = self._task_index[task_id]
                # Remove old entry
                del self._task_index[task_id]
                # Create new entry with updated priority
                new_task = PrioritizedTask(
                    priority=new_priority,
                    timestamp=time.time(),
                    task_id=task.task_id,
                    skill_name=task.skill_name,
                    payload=task.payload,
                    status=task.status,
                    worker_id=task.worker_id,
                    retry_count=task.retry_count,
                    max_retries=task.max_retries,
                    created_at=task.created_at
                )
                heapq.heappush(self._heap, new_task)
                self._task_index[task_id] = new_task
                
    def size(self) -> int:
        with self._lock:
            return len(self._task_index)
            
    def get_all(self) -> List[PrioritizedTask]:
        with self._lock:
            return list(self._task_index.values())

class WorkerRegistry:
    """Tracks available workers and their load."""
    
    def __init__(self):
        self.workers: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        
    def register_worker(self, worker_id: str, capabilities: List[str]):
        with self._lock:
            self.workers[worker_id] = {
                'worker_id': worker_id,
                'capabilities': capabilities,
                'current_tasks': 0,
                'max_concurrent': 10,
                'last_heartbeat': time.time(),
                'status': 'active'
            }
            
    def unregister_worker(self, worker_id: str):
        with self._lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
                
    def heartbeat(self, worker_id: str, current_tasks: int):
        with self._lock:
            if worker_id in self.workers:
                self.workers[worker_id]['last_heartbeat'] = time.time()
                self.workers[worker_id]['current_tasks'] = current_tasks
                
    def get_available_worker(self, skill_name: str) -> Optional[str]:
        """Get the least-loaded worker capable of handling the skill."""
        with self._lock:
            candidates = [
                w for w in self.workers.values()
                if w['status'] == 'active'
                and skill_name in w['capabilities']
                and w['current_tasks'] < w['max_concurrent']
            ]
            if not candidates:
                return None
            # Return worker with lowest load ratio
            return min(candidates, key=lambda w: w['current_tasks'] / w['max_concurrent'])['worker_id']
            
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_workers = len(self.workers)
            active_workers = sum(1 for w in self.workers.values() if w['status'] == 'active')
            total_load = sum(w['current_tasks'] for w in self.workers.values())
            return {
                'total_workers': total_workers,
                'active_workers': active_workers,
                'total_load': total_load,
                'avg_load_per_worker': total_load / active_workers if active_workers > 0 else 0
            }

class DistributedQueueManager:
    """Main interface for distributed task management."""
    
    def __init__(self, storage_path: str = "output/task_queue.json"):
        self.storage_path = storage_path
        self.queues: Dict[TaskPriority, PriorityQueue] = {
            p: PriorityQueue() for p in TaskPriority
        }
        self.worker_registry = WorkerRegistry()
        self.all_tasks: Dict[str, PrioritizedTask] = {}
        self._lock = threading.Lock()
        self._ensure_storage_dir()
        self._load_existing()
        
    def _ensure_storage_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
    def _load_existing(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for task_data in data.get('tasks', []):
                        task_data['status'] = TaskStatus(task_data['status'])
                        task = PrioritizedTask(**task_data)
                        if task.status == TaskStatus.PENDING:
                            self.enqueue(task)
                        self.all_tasks[task.task_id] = task
                logger.info(f"Loaded {len(self.all_tasks)} tasks from persistence")
            except Exception as e:
                logger.error(f"Failed to load task queue: {e}")

    def _persist(self):
        try:
            data = {
                'tasks': [t.to_dict() for t in self.all_tasks.values()]
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist task queue: {e}")

    def enqueue(self, task: PrioritizedTask) -> str:
        """Add a task to the appropriate priority queue."""
        task.status = TaskStatus.QUEUED
        priority = TaskPriority(task.priority)
        self.queues[priority].push(task)
        
        with self._lock:
            self.all_tasks[task.task_id] = task
            
        self._persist()
        logger.debug(f"Enqueued task {task.task_id} with priority {priority.name}")
        return task.task_id

    def submit(self, skill_name: str, payload: Dict[str, Any], 
               priority: TaskPriority = TaskPriority.NORMAL,
               max_retries: int = 3) -> str:
        """Submit a new task."""
        task = PrioritizedTask(
            priority=priority.value,
            timestamp=time.time(),
            task_id=str(uuid.uuid4()),
            skill_name=skill_name,
            payload=payload,
            max_retries=max_retries
        )
        return self.enqueue(task)

    def dequeue(self, worker_id: Optional[str] = None) -> Optional[PrioritizedTask]:
        """Get the next task for a worker."""
        # Try each priority level in order
        for priority in TaskPriority:
            task = self.queues[priority].pop()
            if task:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                if worker_id:
                    task.worker_id = worker_id
                self._persist()
                logger.debug(f"Dequeued task {task.task_id} for worker {worker_id}")
                return task
        return None

    def complete_task(self, task_id: str, result: Any):
        """Mark a task as completed."""
        with self._lock:
            if task_id in self.all_tasks:
                task = self.all_tasks[task_id]
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                task.result = result
                self.queues[TaskPriority(task.priority)].remove(task_id)
                self._persist()

    def fail_task(self, task_id: str, error: str) -> bool:
        """Mark a task as failed, potentially requeuing for retry."""
        with self._lock:
            if task_id not in self.all_tasks:
                return False
                
            task = self.all_tasks[task_id]
            task.retry_count += 1
            task.error = error
            
            if task.retry_count <= task.max_retries:
                # Requeue for retry with exponential backoff consideration
                task.status = TaskStatus.QUEUED
                task.started_at = None
                task.worker_id = None
                logger.info(f"Requeuing task {task_id} for retry #{task.retry_count}")
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self.queues[TaskPriority(task.priority)].remove(task_id)
                logger.warning(f"Task {task_id} failed after {task.retry_count} retries")
                
            self._persist()
            return True

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending/queued task."""
        with self._lock:
            if task_id not in self.all_tasks:
                return False
            task = self.all_tasks[task_id]
            if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                self.queues[TaskPriority(task.priority)].remove(task_id)
                self._persist()
                return True
            return False

    def promote_task(self, task_id: str, new_priority: TaskPriority) -> bool:
        """Promote a task to higher priority."""
        with self._lock:
            if task_id not in self.all_tasks:
                return False
            task = self.all_tasks[task_id]
            if task.status == TaskStatus.QUEUED:
                old_priority = TaskPriority(task.priority)
                self.queues[old_priority].update_priority(task_id, new_priority.value)
                task.priority = new_priority.value
                self._persist()
                logger.info(f"Promoted task {task_id} to {new_priority.name}")
                return True
            return False

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get comprehensive queue statistics."""
        stats = {
            'queue_lengths': {p.name: self.queues[p].size() for p in TaskPriority},
            'total_pending': sum(self.queues[p].size() for p in TaskPriority),
            'worker_stats': self.worker_registry.get_stats(),
            'task_statuses': defaultdict(int)
        }
        for task in self.all_tasks.values():
            stats['task_statuses'][task.status.value] += 1
        stats['task_statuses'] = dict(stats['task_statuses'])
        return stats

# Global instance
queue_manager = DistributedQueueManager()

def get_queue_manager() -> DistributedQueueManager:
    return queue_manager
