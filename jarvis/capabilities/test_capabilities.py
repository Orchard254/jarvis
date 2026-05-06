#!/usr/bin/env python3
"""
Verification Script for JARVIS Core Capabilities
Tests System Control and Vision modules to ensure proper functionality.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(title):
    print(f"\n{'='*60}")
    print(f" TESTING: {title}")
    print(f"{'='*60}\n")

def print_result(test_name, success, message=""):
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"[{status}] {test_name}")
    if message:
        print(f"       -> {message}")

def test_system_control():
    """Test System Control capabilities"""
    print_header("SYSTEM CONTROL CAPABILITIES")
    
    try:
        from jarvis.capabilities.system_control import (
            run_terminal_command,
            run_python_code,
            system_info,
            process_manager,
            window_manager
        )
        print_result("Imports", True)
    except ImportError as e:
        print_result("Imports", False, str(e))
        return

    # 1. Test Terminal Command
    try:
        result = run_terminal_command.execute("echo 'JARVIS Test Successful'")
        if result['success'] and 'JARVIS Test Successful' in result['output']:
            print_result("run_terminal_command", True)
        else:
            print_result("run_terminal_command", False, result.get('error', 'Unknown error'))
    except Exception as e:
        print_result("run_terminal_command", False, str(e))

    # 2. Test Python Code Execution
    try:
        code = "print(2 + 2)"
        result = run_python_code.execute(code)
        if result['success'] and '4' in result['output']:
            print_result("run_python_code", True)
        else:
            print_result("run_python_code", False, result.get('error', 'Unknown error'))
    except Exception as e:
        print_result("run_python_code", False, str(e))

    # 3. Test System Info
    try:
        result = system_info.execute(info_type="all")
        if result['success'] and 'cpu_percent' in result['output']:
            print_result("system_info", True, f"CPU: {result['output']['cpu_percent']}%")
        else:
            print_result("system_info", False, result.get('error', 'Unknown error'))
    except Exception as e:
        print_result("system_info", False, str(e))

    # 4. Test Process Manager (List processes)
    try:
        result = process_manager.execute(action="list", limit=5)
        if result['success'] and isinstance(result['output'], list):
            print_result("process_manager", True, f"Found {len(result['output'])} processes (showing 5)")
        else:
            print_result("process_manager", False, result.get('error', 'Unknown error'))
    except Exception as e:
        print_result("process_manager", False, str(e))

    # 5. Test Window Manager (Get active window - safe operation)
    try:
        result = window_manager.execute(action="get_active_title")
        # This might fail in headless environments, which is expected
        if result['success']:
            print_result("window_manager", True, f"Active: {result['output']}")
        else:
            print_result("window_manager", False, "Headless environment or no windows")
    except Exception as e:
        print_result("window_manager", False, str(e))

def test_vision():
    """Test Vision capabilities"""
    print_header("VISION CAPABILITIES")
    
    try:
        from jarvis.capabilities.vision import (
            screen_capture,
            ocr_extract_text
            # vision_analyzer excluded from auto-test as it requires model loading
        )
        print_result("Imports", True)
    except ImportError as e:
        print_result("Imports", False, str(e))
        return

    # 1. Test Screen Capture
    try:
        result = screen_capture.execute(region=None)  # Full screen
        if result['success'] and result['output'].startswith('data:image/png;base64,'):
            size_kb = len(result['output']) // 1024
            print_result("screen_capture", True, f"Captured {size_kb}KB image")
        elif result['success']:
            print_result("screen_capture", True, "Captured image (format check skipped)")
        else:
            print_result("screen_capture", False, result.get('error', 'Unknown error'))
    except Exception as e:
        print_result("screen_capture", False, str(e))

    # 2. Test OCR (Create a simple test image first)
    try:
        from PIL import Image, ImageDraw, ImageFont
        import base64
        import io

        # Create a test image with text
        img = Image.new('RGB', (200, 50), color='white')
        d = ImageDraw.Draw(img)
        d.text((10, 15), "JARVIS OCR TEST", fill='black')
        
        # Save to buffer
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        # Run OCR
        result = ocr_extract_text.execute(image_source=buffer)
        if result['success'] and 'JARVIS' in result['output'].upper():
            print_result("ocr_extract_text", True, f"Detected: '{result['output'].strip()}'")
        else:
            # OCR might fail if tesseract is not installed, warn but don't fail hard
            msg = result.get('error', 'Text not detected')
            if 'tesseract' in msg.lower():
                print_result("ocr_extract_text", False, "Tesseract not installed (Optional)")
            else:
                print_result("ocr_extract_text", False, msg)
    except Exception as e:
        print_result("ocr_extract_text", False, str(e))

def test_registry():
    """Test the unified registry"""
    print_header("CAPABILITY REGISTRY")
    
    try:
        from jarvis.capabilities.registry import CapabilityRegistry
        registry = CapabilityRegistry()
        
        # Check count
        count = len(registry.list_capabilities())
        if count >= 9:  # We have at least 9 implemented so far (6 sys + 3 vision)
            print_result("Registry Initialization", True, f"{count} capabilities loaded")
        else:
            print_result("Registry Initialization", False, f"Only {count} capabilities found")
            
        # Test dispatch
        result = registry.execute("system_info", info_type="cpu")
        if result['success']:
            print_result("Registry Dispatch", True, "Successfully routed to system_info")
        else:
            print_result("Registry Dispatch", False, result.get('error'))
            
    except Exception as e:
        print_result("Registry Test", False, str(e))

if __name__ == "__main__":
    print("\n🚀 JARVIS CAPABILITY VERIFICATION SUITE\n")
    
    test_system_control()
    test_vision()
    test_registry()
    
    print("\n" + "="*60)
    print(" VERIFICATION COMPLETE")
    print("="*60)
    print("\nNote: Some tests may fail in headless CI environments.")
    print("Ensure 'tesseract-ocr' is installed for OCR tests.")
    print("Run 'pip install -r jarvis/capabilities/requirements.txt' if imports fail.\n")
