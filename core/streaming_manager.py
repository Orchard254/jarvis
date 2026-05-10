"""
Streaming Response Manager for JARVIS.
Provides chunked output with support for mixed content types and SSE formatting.
"""
import json
import time
from typing import Optional, Dict, Any, List, Generator, AsyncGenerator
from dataclasses import dataclass, field, asdict
from enum import Enum
import asyncio


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
    sequence_id: int = 0
    task_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "content_type": self.content_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "sequence_id": self.sequence_id,
            "task_id": self.task_id
        }
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps(self.to_dict())}\n\n"
    
    def to_json(self) -> str:
        """Format as JSON string."""
        return json.dumps(self.to_dict())


class StreamingResponse:
    """
    Manages streaming responses with support for mixed content types.
    
    Features:
    - Token-level streaming for text content
    - Tool call visibility with real-time arguments
    - Status updates for progress tracking
    - SSE-compatible formatting
    - Sequence ordering guarantees
    """
    
    def __init__(self, task_id: Optional[str] = None, enable_thoughts: bool = False):
        self.task_id = task_id
        self.enable_thoughts = enable_thoughts
        self._sequence_counter = 0
        self._chunks: List[StreamChunk] = []
        self._subscribers: List[asyncio.Queue] = []
        self._closed = False
        self._start_time = time.time()
    
    def _next_sequence(self) -> int:
        """Get next sequence ID."""
        seq = self._sequence_counter
        self._sequence_counter += 1
        return seq
    
    def send_text(self, text: str) -> StreamChunk:
        """Send a text chunk."""
        if self._closed:
            raise RuntimeError("Cannot send to closed stream")
        
        chunk = StreamChunk(
            content_type=ContentType.TEXT,
            data=text,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        return chunk
    
    def send_tool_call(self, tool_name: str, arguments: Dict[str, Any], 
                       call_id: Optional[str] = None) -> StreamChunk:
        """Send a tool call notification."""
        if self._closed:
            raise RuntimeError("Cannot send to closed stream")
        
        data = {
            "tool_name": tool_name,
            "arguments": arguments,
            "call_id": call_id or f"call_{self._sequence_counter}"
        }
        
        chunk = StreamChunk(
            content_type=ContentType.TOOL_CALL,
            data=data,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        return chunk
    
    def send_status(self, status: str, progress: float, 
                    message: Optional[str] = None) -> StreamChunk:
        """Send a status update."""
        if self._closed:
            raise RuntimeError("Cannot send to closed stream")
        
        data = {
            "status": status,
            "progress": min(100.0, max(0.0, progress)),
            "message": message or status
        }
        
        chunk = StreamChunk(
            content_type=ContentType.STATUS_UPDATE,
            data=data,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        return chunk
    
    def send_thought(self, thought: str) -> StreamChunk:
        """Send an intermediate thought (if enabled)."""
        if not self.enable_thoughts:
            return None
        
        if self._closed:
            raise RuntimeError("Cannot send to closed stream")
        
        chunk = StreamChunk(
            content_type=ContentType.THOUGHT,
            data=thought,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        return chunk
    
    def send_error(self, error: str, error_type: str = "Error") -> StreamChunk:
        """Send an error message."""
        if self._closed:
            raise RuntimeError("Cannot send to closed stream")
        
        data = {
            "error_type": error_type,
            "message": error
        }
        
        chunk = StreamChunk(
            content_type=ContentType.ERROR,
            data=data,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        return chunk
    
    def complete(self, final_result: Optional[Any] = None) -> StreamChunk:
        """Mark the stream as complete."""
        if self._closed:
            raise RuntimeError("Stream already closed")
        
        data = {
            "final_result": final_result,
            "duration_seconds": time.time() - self._start_time,
            "total_chunks": len(self._chunks)
        }
        
        chunk = StreamChunk(
            content_type=ContentType.COMPLETE,
            data=data,
            sequence_id=self._next_sequence(),
            task_id=self.task_id
        )
        self._chunks.append(chunk)
        self._notify_subscribers(chunk)
        self._closed = True
        return chunk
    
    def _notify_subscribers(self, chunk: StreamChunk):
        """Notify all subscribed queues."""
        for sub_queue in self._subscribers:
            try:
                sub_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is too slow
    
    def subscribe(self) -> asyncio.Queue:
        """Subscribe to stream updates."""
        queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from stream updates."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
    
    async def stream_generator(self) -> AsyncGenerator[str, None]:
        """Generate SSE-formatted stream chunks."""
        for chunk in self._chunks:
            yield chunk.to_sse()
        
        if not self._closed:
            # Create a subscriber to wait for new chunks
            subscriber = self.subscribe()
            try:
                while not self._closed:
                    try:
                        chunk = await asyncio.wait_for(
                            subscriber.get(), 
                            timeout=30.0
                        )
                        yield chunk.to_sse()
                    except asyncio.TimeoutError:
                        continue
            finally:
                self.unsubscribe(subscriber)
    
    def get_chunks(self) -> List[Dict[str, Any]]:
        """Get all chunks as dictionaries."""
        return [chunk.to_dict() for chunk in self._chunks]
    
    def get_full_text(self) -> str:
        """Concatenate all text chunks."""
        text_chunks = [
            chunk.data for chunk in self._chunks 
            if chunk.content_type == ContentType.TEXT
        ]
        return "".join(text_chunks)
    
    @property
    def is_closed(self) -> bool:
        """Check if stream is closed."""
        return self._closed
    
    @property
    def duration(self) -> float:
        """Get stream duration in seconds."""
        return time.time() - self._start_time


class StreamingManager:
    """
    Central manager for all active streaming responses.
    """
    
    def __init__(self):
        self._streams: Dict[str, StreamingResponse] = {}
        self._lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else threading.Lock()
    
    def create_stream(self, task_id: str, 
                      enable_thoughts: bool = False) -> StreamingResponse:
        """Create a new streaming response for a task."""
        stream = StreamingResponse(task_id=task_id, enable_thoughts=enable_thoughts)
        self._streams[task_id] = stream
        return stream
    
    def get_stream(self, task_id: str) -> Optional[StreamingResponse]:
        """Get existing stream for a task."""
        return self._streams.get(task_id)
    
    def close_stream(self, task_id: str) -> bool:
        """Close a stream if it's not already closed."""
        stream = self._streams.get(task_id)
        if stream and not stream.is_closed:
            stream.complete()
            return True
        return False
    
    def list_active_streams(self) -> List[str]:
        """List all active (non-closed) stream task IDs."""
        return [
            task_id for task_id, stream in self._streams.items()
            if not stream.is_closed
        ]
    
    def cleanup_completed(self, max_age_seconds: float = 3600):
        """Remove completed streams older than max_age_seconds."""
        current_time = time.time()
        to_remove = []
        
        for task_id, stream in self._streams.items():
            if stream.is_closed and (current_time - stream._start_time) > max_age_seconds:
                to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._streams[task_id]
        
        return len(to_remove)


# Global instance
streaming_manager = StreamingManager()
