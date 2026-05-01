#!/usr/bin/env python
# Verification script for JARVIS bug fixes


def test_tool_patterns():
    """Test that tool pattern detection works for indexing commands"""
    from jarvis import _likely_needs_tools

    result = _likely_needs_tools("index software shortcuts")
    print("[PASS] Tool pattern detection: 'index software shortcuts' -> {}".format(result))
    assert result == True, "Should detect indexing command as needing tools"
    return True


def test_intent_classification():
    """Test that intent classification works with fallback"""
    from intent_classifier import classify_intents

    # Test a simple command
    result = classify_intents("open notepad")
    print("[PASS] Intent classification: 'open notepad' -> {}".format(result))
    # Should return at least one intent with confidence > 0
    assert len(result) > 0, "Should classify at least one intent"
    assert result[0]["confidence"] > 0, "Intent should have positive confidence"
    return True


def test_tool_reliability():
    """Test that tool reliability updates work"""
    from jarvis import _update_tool_reliability

    try:
        _update_tool_reliability("test_tool", True, "Test successful")
        print("[PASS] Tool reliability update: Success")
        return True
    except Exception as e:
        print("[FAIL] Tool reliability update failed: {}".format(e))
        return False


def test_security_blocking():
    """Test that critical processes are blocked"""
    from control_plane import GLOBAL_BLOCKED

    # Check for System Idle Process protection
    system_idle_blocked = any("System Idle Process" in pattern for pattern in GLOBAL_BLOCKED)
    print("[PASS] Security blocking: System Idle Process blocked -> {}".format(system_idle_blocked))
    assert system_idle_blocked, "Should block System Idle Process"
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("JARVIS BUG FIXES VERIFICATION")
    print("=" * 50)

    tests = [
        test_tool_patterns,
        test_intent_classification,
        test_tool_reliability,
        test_security_blocking,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print("[FAIL] {} failed: {}".format(test.__name__, e))

    print("=" * 50)
    print("RESULTS: {}/{} tests passed".format(passed, total))
    if passed == total:
        print("ALL FIXES VERIFIED SUCCESSFULLY!")
    else:
        print("Some tests failed - review needed")
    print("=" * 50)
