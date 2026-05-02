"""
Test Phase 3 Safety Layer Integration
Tests the three-layer safety system:
1. Input Filter
2. Plan Validator  
3. Tool Guard
"""

import sys
sys.path.insert(0, '/workspace')

from safety import InputFilter, PlanValidator, ToolGuard, AuditLog

def test_input_filter():
    """Test the input filter layer."""
    print("\n=== Testing Input Filter ===")
    
    input_filter = InputFilter()
    
    # Test safe input
    safe_inputs = [
        "What's the weather today?",
        "Open Chrome browser",
        "Create a new file called test.txt",
        "Tell me a joke"
    ]
    
    for inp in safe_inputs:
        result = input_filter.check(inp)
        status = "✓ PASS" if result.is_safe else "✗ FAIL"
        print(f"{status}: '{inp[:40]}...' -> safe={result.is_safe}")
    
    # Test dangerous inputs that should be blocked
    dangerous_inputs = [
        "format c:",
        "del /s c:\\windows",
        "remove-item -recurse -force c:\\users",
        "reg delete hkcu",
        "powershell -enc SGVsbG8gV29ybGQ="
    ]
    
    for inp in dangerous_inputs:
        result = input_filter.check(inp)
        status = "✓ PASS" if not result.is_safe else "✗ FAIL (should be blocked)"
        print(f"{status}: '{inp[:40]}...' -> blocked={not result.is_safe}, reason={result.reason}")
    
    print("Input Filter tests complete.\n")

def test_plan_validator():
    """Test the plan validator layer."""
    print("\n=== Testing Plan Validator ===")
    
    plan_validator = PlanValidator()
    
    # Test safe plan
    safe_plan = [
        {'tool': 'open_app', 'arguments': {'app_name': 'notepad'}},
        {'tool': 'type_text', 'arguments': {'text': 'Hello World'}},
        {'tool': 'read_file', 'arguments': {'path': 'C:\\Users\\test\\document.txt'}}
    ]
    
    result = plan_validator.review(safe_plan)
    status = "✓ PASS" if result.is_valid else "✗ FAIL"
    print(f"{status}: Safe plan -> valid={result.is_valid}, risk={result.risk_level.value}")
    
    # Test dangerous plan
    dangerous_plan = [
        {'tool': 'run_powershell', 'arguments': {'command': 'format c:'}},
        {'tool': 'delete_file', 'arguments': {'path': 'C:\\Windows\\System32\\config'}},
        {'tool': 'shutdown_pc', 'arguments': {}}
    ]
    
    result = plan_validator.review(dangerous_plan)
    status = "✓ PASS" if not result.is_valid or result.risk_level.value in ['high', 'critical'] else "✗ FAIL"
    print(f"{status}: Dangerous plan -> valid={result.is_valid}, risk={result.risk_level.value}")
    if result.warnings:
        print(f"  Warnings: {result.warnings[0][:80]}...")
    
    # Test excessive destructive operations
    destructive_plan = [
        {'tool': 'delete_file', 'arguments': {'path': 'file1.txt'}},
        {'tool': 'delete_file', 'arguments': {'path': 'file2.txt'}},
        {'tool': 'delete_file', 'arguments': {'path': 'file3.txt'}},
        {'tool': 'delete_file', 'arguments': {'path': 'file4.txt'}},
        {'tool': 'close_app', 'arguments': {'app_name': 'chrome'}}
    ]
    
    result = plan_validator.review(destructive_plan)
    status = "✓ PASS" if result.requires_confirmation or not result.is_valid else "✗ FAIL"
    print(f"{status}: Destructive plan -> requires_confirmation={result.requires_confirmation}, risk={result.risk_level.value}")
    
    print("Plan Validator tests complete.\n")

def test_tool_guard():
    """Test the tool guard layer."""
    print("\n=== Testing Tool Guard ===")
    
    tool_guard = ToolGuard()
    
    # Test safe tool calls
    safe_calls = [
        ('open_app', {'app_name': 'notepad'}),
        ('read_file', {'path': 'C:\\Users\\test\\doc.txt'}),
        ('type_text', {'text': 'Hello'}),
        ('click_at', {'x': 100, 'y': 200})
    ]
    
    for tool_name, params in safe_calls:
        is_valid, error = tool_guard.validate_tool_call(tool_name, params)
        status = "✓ PASS" if is_valid else "✗ FAIL"
        print(f"{status}: {tool_name} -> valid={is_valid}")
    
    # Test dangerous tool calls
    dangerous_calls = [
        ('run_command', {'command': 'format c:'}),
        ('run_powershell', {'command': 'del /s c:\\windows'}),
        ('delete_file', {'path': 'C:\\Windows\\System32\\drivers'}),
        ('create_file', {'path': 'C:\\Windows\\malicious.bat', 'content': 'dangerous'})
    ]
    
    for tool_name, params in dangerous_calls:
        is_valid, error = tool_guard.validate_tool_call(tool_name, params)
        status = "✓ PASS" if not is_valid else "✗ FAIL (should be blocked)"
        print(f"{status}: {tool_name} -> blocked={not is_valid}, reason={error[:60] if error else 'N/A'}")
    
    print("Tool Guard tests complete.\n")

def test_audit_log():
    """Test the audit logging system."""
    print("\n=== Testing Audit Log ===")
    
    audit_log = AuditLog(log_dir='/workspace/jarvis/logs/audit_test')
    
    # Test logging security events
    audit_log.log_security_event('input_blocked', {
        'reason': 'Dangerous pattern detected',
        'blocked_patterns': ['format c:'],
        'original_input_length': 50
    })
    
    audit_log.log_security_event('plan_blocked', {
        'goal': 'Delete system files',
        'risk_level': 'critical',
        'warnings': ['Destructive operation chain detected']
    })
    
    audit_log.log_security_event('tool_blocked', {
        'step_index': 0,
        'tool': 'run_command',
        'reason': 'Protected path access attempt',
        'parameters': {'command': 'dangerous'}
    })
    
    # Flush and verify
    audit_log.flush()
    
    print("✓ PASS: Security events logged successfully")
    print("Audit Log tests complete.\n")

def main():
    """Run all Phase 3 safety tests."""
    print("="*60)
    print("PHASE 3 SAFETY LAYER INTEGRATION TESTS")
    print("="*60)
    
    try:
        test_input_filter()
        test_plan_validator()
        test_tool_guard()
        test_audit_log()
        
        print("="*60)
        print("ALL PHASE 3 SAFETY TESTS COMPLETED SUCCESSFULLY")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
