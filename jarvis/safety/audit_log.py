"""
safety/audit_log.py — Immutable action logging for security and debugging.
Records all tool executions, decisions, and outcomes.

Requirements:
- Write to a rotating log file called audit.log
- Log every tool execution with: timestamp, tool name, params, result success/fail, user text
- Never raise exceptions — audit failures must not block execution
- Be thread-safe for concurrent tool execution
"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging


class AuditLog:
    """
    Thread-safe, append-only audit log for all JARVIS actions.
    Uses rotating file handler to manage log size.
    Never raises exceptions - failures are silently logged.
    """
    
    _lock = threading.Lock()
    
    def __init__(self, log_dir: str = None, max_bytes: int = 10*1024*1024, backup_count: int = 5):
        """
        Initialize the audit log with rotating file handler.
        
        Args:
            log_dir: Directory to store audit logs. Defaults to jarvis/logs/audit
            max_bytes: Maximum size of log file before rotation (default: 10MB)
            backup_count: Number of backup files to keep (default: 5)
        """
        try:
            if log_dir is None:
                base_dir = Path(__file__).parent.parent
                log_dir = base_dir / 'logs' / 'audit'
            
            self.log_dir = Path(log_dir)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
            # Set up rotating file handler for audit.log
            self.log_file = self.log_dir / 'audit.log'
            
            # Create a dedicated logger for audit
            self._logger = logging.getLogger(f'audit_{id(self)}')
            self._logger.setLevel(logging.INFO)
            self._logger.handlers = []  # Clear existing handlers
            
            # RotatingFileHandler handles rotation automatically
            handler = RotatingFileHandler(
                self.log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            handler.setFormatter(logging.Formatter('%(message)s'))
            self._logger.addHandler(handler)
            
            # Prevent propagation to root logger
            self._logger.propagate = False
            
        except Exception as e:
            # Never fail during init - just print error
            print(f"AuditLog initialization failed: {e}")
            self._logger = None
    
    def _safe_log(self, entry: Dict[str, Any]) -> None:
        """
        Safely write an entry to the log file.
        Never raises exceptions - errors are silently ignored.
        Thread-safe using lock.
        """
        if self._logger is None:
            return
        
        try:
            with self._lock:
                # Write as JSON line
                self._logger.info(json.dumps(entry, ensure_ascii=False))
        except Exception:
            # Never raise - audit failures must not block execution
            pass
    
    def log(self, event_type: str, data: Dict[str, Any], 
            session_id: str = None, user_text: str = None) -> None:
        """
        Log an event. Thread-safe, never raises.
        
        Args:
            event_type: Type of event (tool_call, decision, error, etc.)
            data: Event data dictionary
            session_id: Optional session identifier
            user_text: Original user text that triggered this action
        """
        try:
            entry = {
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,
                'session_id': session_id,
                'user_text': user_text,
                'data': data
            }
            self._safe_log(entry)
        except Exception:
            # Never raise
            pass
    
    def log_tool_call(self, tool_name: str, params: Dict[str, Any],
                      result: Dict[str, Any], duration_ms: float,
                      session_id: str = None, user_text: str = None) -> None:
        """
        Log a tool execution with all required fields.
        Thread-safe, never raises.
        
        Args:
            tool_name: Name of the tool executed
            params: Tool parameters
            result: Tool result dict
            duration_ms: Execution duration in milliseconds
            session_id: Session identifier
            user_text: User text that triggered this tool call
        """
        try:
            self.log('tool_call', {
                'tool': tool_name,
                'params': params,
                'result': {
                    'success': result.get('success'),
                    'output': result.get('output'),
                    'error': result.get('error'),
                    'exit_code': result.get('exit_code'),
                    'verified': result.get('verified'),
                    'verify_msg': result.get('verify_msg')
                },
                'duration_ms': duration_ms
            }, session_id=session_id, user_text=user_text)
        except Exception:
            # Never raise
            pass
    
    def log_action(self, action_type: str, details: Dict[str, Any],
                   session_id: str = None, user_text: str = None) -> None:
        """Log a general action. Thread-safe, never raises."""
        try:
            self.log(action_type, details, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_security_event(self, event_type: str, details: Dict[str, Any],
                           session_id: str = None, user_text: str = None) -> None:
        """Log a security-related event. Thread-safe, never raises."""
        try:
            self.log(f'security_{event_type}', details, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_decision(self, decision_type: str, reasoning: str,
                     alternatives: List[str] = None, session_id: str = None,
                     user_text: str = None) -> None:
        """Log a decision made by the LLM. Thread-safe, never raises."""
        try:
            self.log('decision', {
                'decision_type': decision_type,
                'reasoning': reasoning,
                'alternatives': alternatives or []
            }, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_error(self, error_type: str, message: str, 
                  traceback: str = None, context: Dict[str, Any] = None,
                  session_id: str = None, user_text: str = None) -> None:
        """Log an error. Thread-safe, never raises."""
        try:
            self.log('error', {
                'error_type': error_type,
                'message': message,
                'traceback': traceback,
                'context': context or {}
            }, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_validation(self, tool_name: str, params: Dict[str, Any],
                       passed: bool, checks: Dict[str, bool],
                       session_id: str = None, user_text: str = None) -> None:
        """Log a validation check. Thread-safe, never raises."""
        try:
            self.log('validation', {
                'tool': tool_name,
                'params': params,
                'passed': passed,
                'checks': checks
            }, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_plan(self, plan: List[Dict[str, Any]], goal: str,
                 session_id: str = None, user_text: str = None) -> None:
        """Log a task plan. Thread-safe, never raises."""
        try:
            self.log('plan', {
                'goal': goal,
                'steps': plan
            }, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def log_reflection(self, outcome: str, lessons: List[str],
                       session_id: str = None, user_text: str = None) -> None:
        """Log a reflection on completed work. Thread-safe, never raises."""
        try:
            self.log('reflection', {
                'outcome': outcome,
                'lessons': lessons
            }, session_id=session_id, user_text=user_text)
        except Exception:
            pass
    
    def flush(self) -> None:
        """Flush any buffered entries. RotatingFileHandler handles this automatically."""
        try:
            if self._logger:
                for handler in self._logger.handlers:
                    handler.flush()
        except Exception:
            pass
    
    def query(self, event_type: str = None, session_id: str = None,
              start_time: datetime = None, end_time: datetime = None,
              limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query audit log entries. Thread-safe, returns empty list on error.
        """
        try:
            results = []
            
            with self._lock:
                if not self.log_file.exists():
                    return []
                
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if len(results) >= limit:
                            break
                        
                        try:
                            entry = json.loads(line.strip())
                            
                            # Apply filters
                            if event_type and entry.get('event_type') != event_type:
                                continue
                            if session_id and entry.get('session_id') != session_id:
                                continue
                            
                            entry_time = datetime.fromisoformat(entry['timestamp'])
                            if start_time and entry_time < start_time:
                                continue
                            if end_time and entry_time > end_time:
                                continue
                            
                            results.append(entry)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
                
                return results
        except Exception:
            # Never raise - return empty list
            return []
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get a summary of a session. Returns empty summary on error."""
        try:
            entries = self.query(session_id=session_id, limit=10000)
            
            summary = {
                'session_id': session_id,
                'total_events': len(entries),
                'tool_calls': 0,
                'errors': 0,
                'decisions': 0,
                'validations': 0,
                'tools_used': {},
                'start_time': None,
                'end_time': None
            }
            
            for entry in entries:
                event_type = entry.get('event_type')
                
                if event_type == 'tool_call':
                    summary['tool_calls'] += 1
                    tool = entry.get('data', {}).get('tool', 'unknown')
                    summary['tools_used'][tool] = summary['tools_used'].get(tool, 0) + 1
                elif event_type == 'error':
                    summary['errors'] += 1
                elif event_type == 'decision':
                    summary['decisions'] += 1
                elif event_type == 'validation':
                    summary['validations'] += 1
                
                timestamp = entry.get('timestamp')
                if timestamp:
                    if not summary['start_time']:
                        summary['start_time'] = timestamp
                    summary['end_time'] = timestamp
            
            return summary
        except Exception:
            # Return empty summary on error
            return {'session_id': session_id, 'error': 'Failed to generate summary'}
    
    def export_session(self, session_id: str, output_path: str = None) -> Optional[str]:
        """Export a session's audit log to a file. Returns None on error."""
        try:
            entries = self.query(session_id=session_id, limit=100000)
            
            if output_path is None:
                output_path = f'session_{session_id}.json'
            
            export_data = {
                'session_id': session_id,
                'exported_at': datetime.now().isoformat(),
                'events': entries,
                'summary': self.get_session_summary(session_id)
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return output_path
        except Exception:
            return None


# Singleton instance
_audit_instance = None

def get_audit_log() -> AuditLog:
    """Get the singleton AuditLog instance."""
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = AuditLog()
    return _audit_instance
