"""
Audit Log - Immutable action logging for security and debugging.
Records all tool executions, decisions, and outcomes.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class AuditLog:
    """
    Immutable audit log for all JARVIS actions.
    Logs are append-only and timestamped for security.
    """
    
    def __init__(self, log_dir: str = None):
        """
        Initialize the audit log.
        
        Args:
            log_dir: Directory to store audit logs. Defaults to jarvis/logs/audit
        """
        if log_dir is None:
            # Default to jarvis installation directory
            base_dir = Path(__file__).parent.parent
            log_dir = base_dir / 'logs' / 'audit'
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Current log file (rotated daily)
        self.current_file = self._get_log_file()
        self.buffer = []
        self.buffer_size = 10  # Flush after this many entries
    
    def _get_log_file(self) -> Path:
        """Get the log file path for today."""
        date_str = datetime.now().strftime('%Y-%m-%d')
        return self.log_dir / f'audit_{date_str}.log'
    
    def _rotate_if_needed(self) -> None:
        """Rotate log file if date has changed."""
        expected_file = self._get_log_file()
        if expected_file != self.current_file:
            self.flush()
            self.current_file = expected_file
    
    def log(self, event_type: str, data: Dict[str, Any], 
            session_id: str = None, user_id: str = None) -> None:
        """
        Log an event.
        
        Args:
            event_type: Type of event (tool_call, decision, error, etc.)
            data: Event data dictionary
            session_id: Optional session identifier
            user_id: Optional user identifier
        """
        self._rotate_if_needed()
        
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'session_id': session_id,
            'user_id': user_id,
            'data': data
        }
        
        self.buffer.append(entry)
        
        if len(self.buffer) >= self.buffer_size:
            self.flush()
    
    def log_tool_call(self, tool_name: str, params: Dict[str, Any],
                      result: Dict[str, Any], duration_ms: float,
                      session_id: str = None) -> None:
        """
        Log a tool execution.
        
        Args:
            tool_name: Name of the tool executed
            params: Tool parameters
            result: Tool result
            duration_ms: Execution duration in milliseconds
            session_id: Session identifier
        """
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
        }, session_id=session_id)
    
    def log_decision(self, decision_type: str, reasoning: str,
                     alternatives: List[str] = None, session_id: str = None) -> None:
        """
        Log a decision made by the LLM.
        
        Args:
            decision_type: Type of decision (tool_selection, plan_choice, etc.)
            reasoning: LLM's reasoning for the decision
            alternatives: Alternative options considered
            session_id: Session identifier
        """
        self.log('decision', {
            'decision_type': decision_type,
            'reasoning': reasoning,
            'alternatives': alternatives or []
        }, session_id=session_id)
    
    def log_error(self, error_type: str, message: str, 
                  traceback: str = None, context: Dict[str, Any] = None,
                  session_id: str = None) -> None:
        """
        Log an error.
        
        Args:
            error_type: Type of error
            message: Error message
            traceback: Optional stack trace
            context: Additional context
            session_id: Session identifier
        """
        self.log('error', {
            'error_type': error_type,
            'message': message,
            'traceback': traceback,
            'context': context or {}
        }, session_id=session_id)
    
    def log_validation(self, tool_name: str, params: Dict[str, Any],
                       passed: bool, checks: Dict[str, bool],
                       session_id: str = None) -> None:
        """
        Log a validation check.
        
        Args:
            tool_name: Tool being validated
            params: Tool parameters
            passed: Whether validation passed
            checks: Individual check results
            session_id: Session identifier
        """
        self.log('validation', {
            'tool': tool_name,
            'params': params,
            'passed': passed,
            'checks': checks
        }, session_id=session_id)
    
    def log_plan(self, plan: List[Dict[str, Any]], goal: str,
                 session_id: str = None) -> None:
        """
        Log a task plan.
        
        Args:
            plan: List of planned steps
            goal: Overall goal
            session_id: Session identifier
        """
        self.log('plan', {
            'goal': goal,
            'steps': plan
        }, session_id=session_id)
    
    def log_reflection(self, outcome: str, lessons: List[str],
                       session_id: str = None) -> None:
        """
        Log a reflection on completed work.
        
        Args:
            outcome: Final outcome
            lessons: Lessons learned
            session_id: Session identifier
        """
        self.log('reflection', {
            'outcome': outcome,
            'lessons': lessons
        }, session_id=session_id)
    
    def flush(self) -> None:
        """Flush buffered entries to disk."""
        if not self.buffer:
            return
        
        try:
            with open(self.current_file, 'a', encoding='utf-8') as f:
                for entry in self.buffer:
                    # Write as JSONL (one JSON per line)
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            self.buffer = []
        except Exception as e:
            # Never fail silently, but don't crash the system
            print(f"Audit log flush failed: {e}")
    
    def query(self, event_type: str = None, session_id: str = None,
              start_time: datetime = None, end_time: datetime = None,
              limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query audit log entries.
        
        Args:
            event_type: Filter by event type
            session_id: Filter by session ID
            start_time: Filter entries after this time
            end_time: Filter entries before this time
            limit: Maximum entries to return
            
        Returns:
            List of matching log entries
        """
        results = []
        
        # Get all log files in date range
        log_files = sorted(self.log_dir.glob('audit_*.log'))
        
        for log_file in log_files:
            if len(results) >= limit:
                break
            
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
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
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue
        
        return results
    
    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a summary of a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Summary dictionary with stats
        """
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
    
    def export_session(self, session_id: str, output_path: str = None) -> str:
        """
        Export a session's audit log to a file.
        
        Args:
            session_id: Session identifier
            output_path: Output file path (default: session_<id>.json)
            
        Returns:
            Path to exported file
        """
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


# Singleton instance
_audit_instance = None

def get_audit_log() -> AuditLog:
    """Get the singleton AuditLog instance."""
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = AuditLog()
    return _audit_instance
