"""
Working Memory - Short-term conversation window manager.
Manages the current conversation context for the LLM.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque


class WorkingMemory:
    """
    Manages short-term working memory for the current conversation.
    Maintains a sliding window of recent messages.
    """
    
    def __init__(self, max_messages: int = 50, max_tokens_estimate: int = 8000):
        """
        Initialize working memory.
        
        Args:
            max_messages: Maximum number of messages to keep
            max_tokens_estimate: Estimated max tokens (for truncation)
        """
        self.max_messages = max_messages
        self.max_tokens_estimate = max_tokens_estimate
        self.messages = deque(maxlen=max_messages)
        self.system_prompt = None
        self.metadata = {
            'session_start': datetime.now().isoformat(),
            'message_count': 0,
            'last_activity': None
        }
    
    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt (prepended to every LLM call)."""
        self.system_prompt = prompt
    
    def add_message(self, role: str, content: str, 
                    metadata: Dict[str, Any] = None) -> None:
        """
        Add a message to working memory.
        
        Args:
            role: Message role ('user', 'assistant', 'system', 'tool')
            content: Message content
            metadata: Optional metadata (timestamps, tool names, etc.)
        """
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        if metadata:
            message['metadata'] = metadata
        
        self.messages.append(message)
        self.metadata['message_count'] += 1
        self.metadata['last_activity'] = datetime.now().isoformat()
    
    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.add_message('user', content)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self.add_message('assistant', content)
    
    def add_tool_result(self, tool_name: str, result: Dict[str, Any]) -> None:
        """
        Add a tool execution result.
        
        Args:
            tool_name: Name of the executed tool
            result: Tool result dictionary
        """
        content = json.dumps({
            'tool': tool_name,
            'result': result
        }, ensure_ascii=False)
        
        self.add_message('tool', content, {'tool_name': tool_name})
    
    def get_messages(self, include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get all messages for the LLM.
        
        Args:
            include_system: Whether to include system prompt
            
        Returns:
            List of message dictionaries
        """
        messages = []
        
        # Add system prompt first
        if include_system and self.system_prompt:
            messages.append({
                'role': 'system',
                'content': self.system_prompt
            })
        
        # Add conversation messages
        messages.extend(list(self.messages))
        
        return messages
    
    def get_recent_messages(self, count: int) -> List[Dict[str, str]]:
        """Get the N most recent messages."""
        return list(self.messages)[-count:]
    
    def get_context_summary(self) -> str:
        """Generate a text summary of the current context."""
        lines = [
            f"Working Memory Summary",
            f"======================",
            f"Session started: {self.metadata['session_start']}",
            f"Total messages: {self.metadata['message_count']}",
            f"Messages in window: {len(self.messages)}",
            f"",
            f"Recent conversation:",
        ]
        
        for msg in list(self.messages)[-10:]:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:100]
            if len(msg.get('content', '')) > 100:
                content += '...'
            lines.append(f"  [{role}]: {content}")
        
        return '\n'.join(lines)
    
    def truncate_to_token_limit(self, estimated_tokens_per_char: float = 0.25) -> None:
        """
        Truncate messages to stay within token limit.
        Removes oldest messages first.
        
        Args:
            estimated_tokens_per_char: Rough estimate of tokens per character
        """
        while len(self.messages) > 0:
            # Estimate total tokens
            total_chars = sum(len(m.get('content', '')) for m in self.messages)
            estimated_tokens = total_chars * estimated_tokens_per_char
            
            if estimated_tokens <= self.max_tokens_estimate:
                break
            
            # Remove oldest message
            self.messages.popleft()
    
    def clear(self) -> None:
        """Clear all messages but keep metadata."""
        self.messages.clear()
        self.metadata['message_count'] = 0
        self.metadata['last_activity'] = datetime.now().isoformat()
    
    def search_messages(self, query: str, case_insensitive: bool = True) -> List[Dict[str, Any]]:
        """
        Search messages for a query string.
        
        Args:
            query: Search query
            case_insensitive: Whether to ignore case
            
        Returns:
            List of matching messages with position info
        """
        results = []
        
        flags = 0 if case_insensitive else 0
        if case_insensitive:
            query = query.lower()
        
        for i, msg in enumerate(self.messages):
            content = msg.get('content', '')
            search_content = content.lower() if case_insensitive else content
            
            if query in search_content:
                results.append({
                    'index': i,
                    'message': msg,
                    'match_position': search_content.find(query)
                })
        
        return results
    
    def export_conversation(self) -> List[Dict[str, Any]]:
        """Export the full conversation as a list."""
        return list(self.messages)
    
    def import_conversation(self, messages: List[Dict[str, Any]]) -> None:
        """Import messages into working memory."""
        self.messages.clear()
        for msg in messages:
            self.messages.append(msg)
        self.metadata['message_count'] = len(messages)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        total_chars = sum(len(m.get('content', '')) for m in self.messages)
        
        return {
            'message_count': len(self.messages),
            'total_characters': total_chars,
            'estimated_tokens': total_chars * 0.25,
            'max_messages': self.max_messages,
            'max_tokens_estimate': self.max_tokens_estimate,
            'utilization': len(self.messages) / self.max_messages if self.max_messages > 0 else 0
        }


# Singleton instance
_working_memory_instance = None

def get_working_memory() -> WorkingMemory:
    """Get the singleton WorkingMemory instance."""
    global _working_memory_instance
    if _working_memory_instance is None:
        _working_memory_instance = WorkingMemory()
    return _working_memory_instance
