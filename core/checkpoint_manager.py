"""
Checkpoint Manager Module
Provides resumable execution with intermediate state saving for long-running tasks.
"""
import asyncio
import json
import os
import time
import hashlib
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Represents a saved state of task execution."""
    checkpoint_id: str
    task_id: str
    timestamp: float
    step_index: int
    state: Dict[str, Any]
    context: Dict[str, Any]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        return cls(**data)


class CheckpointManager:
    """
    Manages checkpoints for long-running autonomous tasks.
    Supports automatic saving, recovery, and cleanup.
    """

    def __init__(self, storage_path: str = "./checkpoints", auto_save_interval: int = 60):
        self.storage_path = storage_path
        self.auto_save_interval = auto_save_interval
        self._active_checkpoints: Dict[str, Checkpoint] = {}
        self._last_save_time: Dict[str, float] = {}
        
        # Ensure storage directory exists
        os.makedirs(storage_path, exist_ok=True)

    def _generate_checkpoint_id(self, task_id: str, step_index: int) -> str:
        """Generate a unique checkpoint ID."""
        content = f"{task_id}:{step_index}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_checkpoint_path(self, task_id: str, checkpoint_id: str) -> str:
        """Get the file path for a checkpoint."""
        safe_task_id = task_id.replace("/", "_").replace("\\", "_")
        return os.path.join(self.storage_path, f"{safe_task_id}_{checkpoint_id}.json")

    async def save_checkpoint(
        self,
        task_id: str,
        step_index: int,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False
    ) -> str:
        """
        Save a checkpoint for the given task.
        
        Args:
            task_id: Unique identifier for the task
            step_index: Current step number
            state: The execution state to save
            context: Additional context (e.g., user intent, environment)
            metadata: Extra metadata (e.g., memory usage, duration)
            force: If True, save immediately regardless of interval
            
        Returns:
            checkpoint_id: The ID of the saved checkpoint
        """
        current_time = time.time()
        
        # Check if auto-save is needed
        last_save = self._last_save_time.get(task_id, 0)
        if not force and (current_time - last_save) < self.auto_save_interval:
            logger.debug(f"Skipping auto-save for {task_id} (interval not met)")
            return self._active_checkpoints.get(task_id, Checkpoint(
                checkpoint_id="none", task_id=task_id, timestamp=current_time,
                step_index=step_index, state={}, context={}, metadata={}
            )).checkpoint_id

        checkpoint_id = self._generate_checkpoint_id(task_id, step_index)
        
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            task_id=task_id,
            timestamp=current_time,
            step_index=step_index,
            state=state,
            context=context or {},
            metadata=metadata or {
                "created_at": datetime.now().isoformat(),
                "step_index": step_index
            }
        )

        # Save to disk
        path = self._get_checkpoint_path(task_id, checkpoint_id)
        try:
            with open(path, 'w') as f:
                json.dump(checkpoint.to_dict(), f, indent=2, default=str)
            
            self._active_checkpoints[task_id] = checkpoint
            self._last_save_time[task_id] = current_time
            
            # Cleanup old checkpoints for this task (keep last 3)
            await self._cleanup_old_checkpoints(task_id, keep_count=3)
            
            logger.info(f"Saved checkpoint {checkpoint_id} for task {task_id} at step {step_index}")
            return checkpoint_id
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint for {task_id}: {e}", exc_info=True)
            raise

    async def load_latest_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """
        Load the most recent checkpoint for a task.
        
        Returns:
            Checkpoint object if found, None otherwise
        """
        # Check memory cache first
        if task_id in self._active_checkpoints:
            logger.info(f"Loaded checkpoint from cache for {task_id}")
            return self._active_checkpoints[task_id]

        # Scan disk for checkpoints
        safe_task_id = task_id.replace("/", "_").replace("\\", "_")
        prefix = f"{safe_task_id}_"
        
        try:
            checkpoints = []
            for filename in os.listdir(self.storage_path):
                if filename.startswith(prefix) and filename.endswith(".json"):
                    filepath = os.path.join(self.storage_path, filename)
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                            checkpoints.append(Checkpoint.from_dict(data))
                    except Exception as e:
                        logger.warning(f"Failed to load checkpoint file {filename}: {e}")
            
            if not checkpoints:
                return None
            
            # Sort by timestamp descending
            checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
            latest = checkpoints[0]
            
            self._active_checkpoints[task_id] = latest
            logger.info(f"Loaded latest checkpoint {latest.checkpoint_id} for {task_id}")
            return latest
            
        except Exception as e:
            logger.error(f"Error scanning checkpoints for {task_id}: {e}", exc_info=True)
            return None

    async def load_checkpoint_by_id(self, task_id: str, checkpoint_id: str) -> Optional[Checkpoint]:
        """Load a specific checkpoint by ID."""
        path = self._get_checkpoint_path(task_id, checkpoint_id)
        
        if not os.path.exists(path):
            # Try to find it by scanning
            return await self.load_latest_checkpoint(task_id)
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                checkpoint = Checkpoint.from_dict(data)
                self._active_checkpoints[task_id] = checkpoint
                return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint {checkpoint_id}: {e}", exc_info=True)
            return None

    async def delete_checkpoint(self, task_id: str, checkpoint_id: str) -> bool:
        """Delete a specific checkpoint."""
        path = self._get_checkpoint_path(task_id, checkpoint_id)
        try:
            if os.path.exists(path):
                os.remove(path)
                if task_id in self._active_checkpoints and \
                   self._active_checkpoints[task_id].checkpoint_id == checkpoint_id:
                    del self._active_checkpoints[task_id]
                logger.info(f"Deleted checkpoint {checkpoint_id} for {task_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}", exc_info=True)
            return False

    async def _cleanup_old_checkpoints(self, task_id: str, keep_count: int = 3) -> int:
        """Remove old checkpoints, keeping only the most recent ones."""
        safe_task_id = task_id.replace("/", "_").replace("\\", "_")
        prefix = f"{safe_task_id}_"
        
        try:
            checkpoints = []
            for filename in os.listdir(self.storage_path):
                if filename.startswith(prefix) and filename.endswith(".json"):
                    filepath = os.path.join(self.storage_path, filename)
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                            checkpoints.append((data['timestamp'], filepath))
                    except (IOError, json.JSONDecodeError, KeyError):
                        continue
            
            # Sort by timestamp descending
            checkpoints.sort(key=lambda x: x[0], reverse=True)
            
            deleted = 0
            for _, filepath in checkpoints[keep_count:]:
                try:
                    os.remove(filepath)
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete old checkpoint {filepath}: {e}")
            
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old checkpoints for {task_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Error cleaning up checkpoints for {task_id}: {e}", exc_info=True)
            return 0

    async def list_checkpoints(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available checkpoints, optionally filtered by task_id."""
        result = []
        
        try:
            for filename in os.listdir(self.storage_path):
                if not filename.endswith(".json"):
                    continue
                
                if task_id:
                    safe_task_id = task_id.replace("/", "_").replace("\\", "_")
                    if not filename.startswith(f"{safe_task_id}_"):
                        continue
                
                filepath = os.path.join(self.storage_path, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        result.append({
                            "checkpoint_id": data.get("checkpoint_id"),
                            "task_id": data.get("task_id"),
                            "timestamp": data.get("timestamp"),
                            "step_index": data.get("step_index"),
                            "created_at": data.get("metadata", {}).get("created_at")
                        })
                except (IOError, json.JSONDecodeError):
                    continue
            
            result.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return result
            
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}", exc_info=True)
            return []

    def get_checkpoint_summary(self, task_id: str) -> Dict[str, Any]:
        """Get a summary of checkpoint status for a task."""
        checkpoint = self._active_checkpoints.get(task_id)
        if not checkpoint:
            return {"has_checkpoint": False}
        
        return {
            "has_checkpoint": True,
            "checkpoint_id": checkpoint.checkpoint_id,
            "step_index": checkpoint.step_index,
            "timestamp": checkpoint.timestamp,
            "age_seconds": time.time() - checkpoint.timestamp,
            "state_keys": list(checkpoint.state.keys()),
            "context_keys": list(checkpoint.context.keys())
        }


class ResumableTask:
    """
    Wrapper for creating tasks that support automatic checkpointing.
    """
    
    def __init__(self, task_id: str, checkpoint_manager: CheckpointManager):
        self.task_id = task_id
        self.cp_manager = checkpoint_manager
        self.current_step = 0
        self.state: Dict[str, Any] = {}
        self.context: Dict[str, Any] = {}

    async def run_with_checkpoints(
        self,
        execution_func: callable,
        initial_state: Optional[Dict[str, Any]] = None,
        checkpoint_every_n_steps: int = 1
    ) -> Any:
        """
        Run a task with automatic checkpointing.
        
        Args:
            execution_func: Async function that takes (step, state, context) and yields results
            initial_state: Starting state
            checkpoint_every_n_steps: Save checkpoint every N steps
            
        Returns:
            Final result of the execution
        """
        # Try to resume from checkpoint
        checkpoint = await self.cp_manager.load_latest_checkpoint(self.task_id)
        
        if checkpoint:
            logger.info(f"Resuming task {self.task_id} from step {checkpoint.step_index}")
            self.current_step = checkpoint.step_index
            self.state = checkpoint.state
            self.context = checkpoint.context
        else:
            logger.info(f"Starting fresh task {self.task_id}")
            self.state = initial_state or {}
            self.current_step = 0

        final_result = None
        
        async for step_result in execution_func(self.current_step, self.state, self.context):
            self.state.update(step_result.get("state_updates", {}))
            
            if step_result.get("is_complete"):
                final_result = step_result.get("result")
                break
            
            self.current_step += 1
            
            # Auto-checkpoint
            if self.current_step % checkpoint_every_n_steps == 0:
                await self.cp_manager.save_checkpoint(
                    task_id=self.task_id,
                    step_index=self.current_step,
                    state=self.state,
                    context=self.context,
                    metadata={"step_result": str(step_result)[:100]}
                )
        
        # Final checkpoint
        await self.cp_manager.save_checkpoint(
            task_id=self.task_id,
            step_index=self.current_step,
            state=self.state,
            context=self.context,
            metadata={"status": "completed" if final_result else "interrupted"},
            force=True
        )
        
        return final_result
