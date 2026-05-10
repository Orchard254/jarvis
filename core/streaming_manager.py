"""
Streaming Response Manager for JARVIS Phase 4.
Implements chunked output with support for mixed content types.
Provides server-sent events (SSE) compatible formatting.
"""
import json
import time
import uuid
from typing import Optional, Dict, Any, List, Generator, AsyncGenerator
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Types of content that can be streamed."""
    TEXT = "text"
    TOOL_CALL = "tool_call"
    STATUS_UPDATE = "status_update"
    THOUGHT = "thought"
    ERROR = "error"
    COMPLETE = "complete"


@dataclass
class StreamChunk:
    """Represents a single chunk of streamed content."""
    content_type: ContentType
    data: Any
    timestamp: float = field(default_factory=time.time)
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sequence_number: int = 0
    task_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "chunk_id": self.chunk_id,
            "content_type": self.content_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "sequence_number": self.sequence_number,
            "task_id": self.task_id
        }
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps(self.to_dict())}\n\n"
    
    def to_json(self) -> str:
        """Format as JSON line."""
        return json.dumps(self.to_dict()) + "\n"


class StreamingResponse:
    """
    Manages streaming responses with support for mixed content types.
    Provides token-level streaming, intermediate thoughts, and tool call visibility.
    """
    
    def __init__(self, task_id: Optional[str] = None, 
                 expose_thoughts: bool = False,
                 format_type: str = "sse"):
        self.task_id = task_id or str(uuid.uuid4())
        self.expose_thoughts = expose_thoughts
        self.format_type = format_type  # "sse" or "json"
        self._chunks: List[StreamChunk] = []
        self._sequence = 0
        self._started = False
        self._completed = False
        self._start_time: Optional[float] = None
        logger.info(f"StreamingResponse initialized for task {self.task_id}")
    
    def start(self):
        """Mark the stream as started."""
        self._started = True
        self._start_time = time.time()
        self._send_status("stream_started", {"task_id": self.task_id})
        logger.debug(f"Stream started for task {self.task_id}")
    
    def _next_sequence(self) -> int:
        """Get next sequence number."""
        seq = self._sequence
        self._sequence += 1
        return seq
    
    def _add_chunk(self, chunk: StreamChunk) -> str:
        """Add a chunk and return formatted output."""
        chunk.sequence_number = self._next_sequence()
        chunk.task_id = self.task_id
        self._chunks.append(chunk)
        
        if self.format_type == "sse":
            return chunk.to_sse()
        else:
            return chunk.to_json()
    
    def send_text(self, text: str, is_token: bool = False) -> str:
        """
        Send text content.
        
        Args:
            text: The text to send
            is_token: If True, treats text as a single token for fine-grained streaming
        
        Returns:
            Formatted chunk string
        """
        if not self._started:
            self.start()
        
        chunk = StreamChunk(
            content_type=ContentType.TEXT,
            data={"text": text, "is_token": is_token}
        )
        return self._add_chunk(chunk)
    
    def send_tool_call(self, tool_name: str, arguments: Dict[str, Any], 
                       call_id: Optional[str] = None) -> str:
        """
        Send a tool call notification.
        
        Args:
            tool_name: Name of the tool being called
            arguments: Arguments being passed to the tool
            call_id: Unique identifier for this tool call
        
        Returns:
            Formatted chunk string
        """
        if not self._started:
            self.start()
        
        chunk = StreamChunk(
            content_type=ContentType.TOOL_CALL,
            data={
                "tool_name": tool_name,
                "arguments": arguments,
                "call_id": call_id or str(uuid.uuid4())[:8]
            }
        )
        logger.info(f"Tool call streamed: {tool_name}")
        return self._add_chunk(chunk)
    
    def send_tool_result(self, tool_name: str, result: Any, 
                         call_id: str) -> str:
        """
        Send a tool call result.
        
        Args:
            tool_name: Name of the tool that was called
            result: Result returned by the tool
            call_id: Identifier matching the original tool call
        
        Returns:
            Formatted chunk string
        """
        chunk = StreamChunk(
            content_type=ContentType.TOOL_CALL,
            data={
                "tool_name": tool_name,
                "result": result,
                "call_id": call_id,
                "is_result": True
            }
        )
        return self._add_chunk(chunk)
    
    def send_status(self, status: str, details: Optional[Dict[str, Any]] = None) -> str:
        """
        Send a status update.
        
        Args:
            status: Status identifier (e.g., "processing", "waiting", "complete")
            details: Additional status details
        
        Returns:
            Formatted chunk string
        """
        if not self._started:
            self.start()
        
        chunk = StreamChunk(
            content_type=ContentType.STATUS_UPDATE,
            data={"status": status, "details": details or {}}
        )
        return self._add_chunk(chunk)
    
    def _send_status(self, status: str, details: Optional[Dict[str, Any]] = None) -> str:
        """Internal method to send status without checking start."""
        chunk = StreamChunk(
            content_type=ContentType.STATUS_UPDATE,
            data={"status": status, "details": details or {}}
        )
        return self._add_chunk(chunk)
    
    def send_thought(self, thought: str, level: str = "info") -> str:
        """
        Send an intermediate thought/reasoning step.
        
        Args:
            thought: The thought content
            level: Importance level ("info", "debug", "reasoning")
        
        Returns:
            Formatted chunk string
        """
        if not self.expose_thoughts:
            logger.debug(f"Thought suppressed: {thought[:50]}...")
            return ""
        
        if not self._started:
            self.start()
        
        chunk = StreamChunk(
            content_type=ContentType.THOUGHT,
            data={"thought": thought, "level": level}
        )
        logger.debug(f"Thought streamed: {thought[:50]}...")
        return self._add_chunk(chunk)
    
    def send_error(self, error_message: str, error_type: str = "generic",
                   recoverable: bool = True) -> str:
        """
        Send an error notification.
        
        Args:
            error_message: Human-readable error message
            error_type: Type/category of error
            recoverable: Whether the error can be recovered from
        
        Returns:
            Formatted chunk string
        """
        if not self._started:
            self.start()
        
        chunk = StreamChunk(
            content_type=ContentType.ERROR,
            data={
                "message": error_message,
                "type": error_type,
                "recoverable": recoverable
            }
        )
        logger.error(f"Error streamed: {error_message}")
        return self._add_chunk(chunk)
    
    def complete(self, final_summary: Optional[str] = None) -> str:
        """
        Mark the stream as complete.
        
        Args:
            final_summary: Optional summary of the entire response
        
        Returns:
            Formatted chunk string
        """
        if self._completed:
            return ""
        
        elapsed = time.time() - self._start_time if self._start_time else 0
        chunk = StreamChunk(
            content_type=ContentType.COMPLETE,
            data={
                "summary": final_summary,
                "total_chunks": len(self._chunks),
                "elapsed_seconds": elapsed
            }
        )
        self._completed = True
        logger.info(f"Stream completed for task {self.task_id} with {len(self._chunks)} chunks")
        return self._add_chunk(chunk)
    
    def get_chunks(self) -> List[StreamChunk]:
        """Get all chunks sent so far."""
        return self._chunks.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the stream."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        chunk_counts = {}
        for chunk in self._chunks:
            ct = chunk.content_type.value
            chunk_counts[ct] = chunk_counts.get(ct, 0) + 1
        
        return {
            "task_id": self.task_id,
            "total_chunks": len(self._chunks),
            "chunk_counts": chunk_counts,
            "elapsed_seconds": elapsed,
            "chunks_per_second": len(self._chunks) / elapsed if elapsed > 0 else 0,
            "completed": self._completed
        }
    
    def generate_stream(self) -> Generator[str, None, None]:
        """
        Generator that yields all chunks as formatted strings.
        Useful for iterating over historical chunks.
        """
        for chunk in self._chunks:
            if self.format_type == "sse":
                yield chunk.to_sse()
            else:
                yield chunk.to_json()


# Global streaming manager instance
class StreamingManager:
    """
    Centralized manager for all active streaming responses.
    Tracks multiple concurrent streams and provides cleanup.
    """
    
    def __init__(self):
        self._streams: Dict[str, StreamingResponse] = {}
        self._lock = threading.Lock() if 'threading' in globals() else None
        logger.info("StreamingManager initialized")
    
    def create_stream(self, task_id: Optional[str] = None,
                      expose_thoughts: bool = False,
                      format_type: str = "sse") -> StreamingResponse:
        """Create a new streaming response."""
        stream = StreamingResponse(
            task_id=task_id,
            expose_thoughts=expose_thoughts,
            format_type=format_type
        )
        
        if self._lock:
            with self._lock:
                self._streams[stream.task_id] = stream
        else:
            self._streams[stream.task_id] = stream
        
        logger.debug(f"Created stream for task {stream.task_id}")
        return stream
    
    def get_stream(self, task_id: str) -> Optional[StreamingResponse]:
        """Get an existing stream by task ID."""
        if self._lock:
            with self._lock:
                return self._streams.get(task_id)
        return self._streams.get(task_id)
    
    def close_stream(self, task_id: str) -> bool:
        """Close and remove a stream."""
        if self._lock:
            with self._lock:
                stream = self._streams.pop(task_id, None)
        else:
            stream = self._streams.pop(task_id, None)
        
        if stream:
            if not stream._completed:
                stream.complete()
            logger.debug(f"Closed stream for task {task_id}")
            return True
        return False
    
    def get_active_streams(self) -> List[str]:
        """Get list of active task IDs."""
        if self._lock:
            with self._lock:
                return [tid for tid, s in self._streams.items() if not s._completed]
        return [tid for tid, s in self._streams.items() if not s._completed]
    
    def cleanup_inactive(self, max_age_seconds: float = 3600) -> int:
        """Remove streams that are completed or too old."""
        current_time = time.time()
        removed = 0
        
        if self._lock:
            with self._lock:
                to_remove = []
                for task_id, stream in self._streams.items():
                    if stream._completed:
                        to_remove.append(task_id)
                    elif stream._start_time and (current_time - stream._start_time) > max_age_seconds:
                        to_remove.append(task_id)
                
                for task_id in to_remove:
                    del self._streams[task_id]
                    removed += 1
        else:
            to_remove = []
            for task_id, stream in self._streams.items():
                if stream._completed:
                    to_remove.append(task_id)
                elif stream._start_time and (current_time - stream._start_time) > max_age_seconds:
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                del self._streams[task_id]
                removed += 1
        
        if removed > 0:
            logger.debug(f"Cleaned up {removed} inactive streams")
        return removed


# Import threading at module level for StreamingManager
import threading

# Global instance
streaming_manager = StreamingManager()
