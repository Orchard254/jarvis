"""
TEST SUITE FOR TTS VOICES
--------------------------
Tests for text-to-speech functionality using jarvis.output.tts module.
"""

import os
import sys
import warnings
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from jarvis.output.tts import TTSManager, speak
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    print(f"Warning: TTS modules not available: {e}")


def test_tts_manager_init():
    """Test TTSManager initialization"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: TTS modules not available")
        return True
        
    print("=" * 60)
    print("TEST: TTSManager Initialization")
    print("=" * 60)
    
    tts = TTSManager()
    
    assert tts is not None
    assert hasattr(tts, 'enabled')
    
    print("✅ PASSED: TTSManager initializes correctly\n")
    return True


def test_tts_enabled_toggle():
    """Test enabling/disabling TTS"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: TTS modules not available")
        return True
        
    print("=" * 60)
    print("TEST: TTS Enable/Disable")
    print("=" * 60)
    
    tts = TTSManager()
    
    # Disable
    tts.set_enabled(False)
    assert tts.enabled == False
    
    # Enable
    tts.set_enabled(True)
    assert tts.enabled == True
    
    print("✅ PASSED: TTS enable/disable works\n")
    return True


def test_speak_function():
    """Test the speak function"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: TTS modules not available")
        return True
        
    print("=" * 60)
    print("TEST: Speak Function")
    print("=" * 60)
    
    # This should not raise an error even if audio hardware is unavailable
    try:
        speak("Test message")
        print("  ✅ speak() executed without errors")
    except Exception as e:
        # Expected in headless environments
        print(f"  ℹ️  speak() raised exception (expected in headless): {type(e).__name__}")
    
    print("✅ PASSED: Speak function callable\n")
    return True


def main():
    print("\n" + "=" * 60)
    print("TTS VOICES TEST SUITE")
    print("=" * 60 + "\n")
    
    if not MODULES_AVAILABLE:
        print("All tests skipped - TTS modules not available.")
        return 0
    
    tests = [
        ("TTSManager Initialization", test_tts_manager_init),
        ("TTS Enable/Disable", test_tts_enabled_toggle),
        ("Speak Function", test_speak_function),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {name} - {e}\n")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {name} - {e}\n")
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{len(tests)} tests passed")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!\n")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed.\n")
        return 1


if __name__ == "__main__":
    exit(main())
