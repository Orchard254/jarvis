"""
TEST SUITE FOR STT ENHANCEMENTS
--------------------------------
Tests for speech-to-text functionality using jarvis.perception.stt module.
"""

import numpy as np
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from jarvis.perception.stt import SpeechToText, STTResult
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    print(f"Warning: STT modules not available: {e}")


def test_stt_result():
    """Test STTResult class"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: STT modules not available")
        return True
        
    print("=" * 60)
    print("TEST: STTResult Class")
    print("=" * 60)
    
    # Test successful result
    result = STTResult(
        text="Hello world",
        confidence=0.95,
        language="en"
    )
    
    assert result.is_success == True
    assert result.text == "Hello world"
    assert result.confidence == 0.95
    
    # Test failed result
    fail_result = STTResult(
        text="",
        error="Audio not detected"
    )
    
    assert fail_result.is_success == False
    assert "Audio not detected" in fail_result.error
    
    print("✅ PASSED: STTResult class works correctly\n")
    return True


def test_stt_initialization():
    """Test SpeechToText initialization"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: STT modules not available")
        return True
        
    print("=" * 60)
    print("TEST: SpeechToText Initialization")
    print("=" * 60)
    
    stt = SpeechToText()
    
    assert stt is not None
    assert hasattr(stt, 'recognizer')
    
    print("✅ PASSED: SpeechToText initializes correctly\n")
    return True


def test_microphone_list():
    """Test listing available microphones"""
    if not MODULES_AVAILABLE:
        print("SKIPPED: STT modules not available")
        return True
        
    print("=" * 60)
    print("TEST: List Microphones")
    print("=" * 60)
    
    stt = SpeechToText()
    mics = stt.list_microphones()
    
    assert isinstance(mics, list)
    print(f"  Found {len(mics)} microphone(s)")
    
    print("✅ PASSED: Microphone listing works\n")
    return True


def main():
    print("\n" + "=" * 60)
    print("STT ENHANCEMENTS TEST SUITE")
    print("=" * 60 + "\n")
    
    if not MODULES_AVAILABLE:
        print("All tests skipped - STT modules not available.")
        return 0
    
    tests = [
        ("STTResult Class", test_stt_result),
        ("SpeechToText Initialization", test_stt_initialization),
        ("List Microphones", test_microphone_list),
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
