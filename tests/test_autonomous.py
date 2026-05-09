
"""Phase 7 tests — Autonomous operation: queue, approval, scheduler, logging."""
import pytest, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous import task_queue, approval_gate, scheduler, activity_log

def test_task_queue_crud():
    task_queue.init_db()
    tid = task_queue.create_task("test command", confidence_required=0.9)
    assert tid is not None
    
    pending = task_queue.get_pending_tasks()
    assert any(t["task_id"] == tid for t in pending)
    
    task_queue.update_task(tid, "running")
    task = task_queue.get_task(tid)
    assert task["status"] == "running"
    
    task_queue.update_task(tid, "complete", result={"response": "done"})
    task = task_queue.get_task(tid)
    assert task["status"] == "complete"
    assert task["result"]["response"] == "done"

def test_approval_gate_flow():
    gate = approval_gate.ApprovalGate(timeout_seconds=60)
    tid = "test-approval-123"
    
    # Request approval
    result = gate.request_approval(tid, "test cmd", "do X then Y", 0.88)
    assert result is False  # Should return False, caller polls for response
    
    # Check response parsing
    assert gate.check_response(tid, "yes") is True
    assert gate.check_response(tid, "no") is None  # Already resolved
    
    # Test rejection
    tid2 = "test-approval-456"
    gate.request_approval(tid2, "test", "plan", 0.9)
    assert gate.check_response(tid2, "cancel") is False

def test_scheduler_cron_parsing():
    sched = scheduler.Scheduler(lambda cmd: "mock")
    now = time.time()
    
    # "every 5 minutes"
    ts = sched._parse_cron("every 5 minutes")
    assert ts is not None and ts > now and ts <= now + 300
    
    # "every day at 09:00"
    ts = sched._parse_cron("every day at 09:00")
    assert ts is not None
    
    # Invalid expression
    assert sched._parse_cron("invalid cron") is None

def test_activity_log_summary():
    task_queue.init_db()
    tid = task_queue.create_task("autonomous test", confidence_required=0.85)
    task_queue.update_task(tid, "running")
    task_queue.update_task(tid, "complete", result={"response": "completed successfully"})
    
    summary = activity_log.generate_summary(task_id=tid)
    assert "autonomous test" in summary
    assert "✅" in summary or "complete" in summary.lower()

def test_pending_approvals_filter():
    task_queue.init_db()
    # Create a high-confidence pending task
    tid = task_queue.create_task("high-conf task", confidence_required=0.95)
    
    pending = activity_log.get_pending_approvals()
    assert any(t["task_id"] == tid for t in pending)
    
    # Low-confidence task should not appear
    tid2 = task_queue.create_task("low-conf task", confidence_required=0.6)
    pending = activity_log.get_pending_approvals()
    assert not any(t["task_id"] == tid2 for t in pending)

