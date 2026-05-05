"""
JARVIS Vision Test Script
Tests vision capabilities using gemma3:27b (native vision model)
while keeping main system on gpt-oss:120b (reasoning only)

Usage: python test_vision.py
"""

import sys
import os
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from jarvis.models.ollama_client import OllamaClient
from jarvis.tools.screen.capture import ScreenshotTool

def capture_and_encode_screenshot(filename="vision_test.png"):
    """Capture screenshot and return base64 encoded string"""
    print("📸 Capturing screenshot...")
    
    try:
        # Take screenshot using PIL directly (more reliable)
        from PIL import ImageGrab
        import tempfile
        
        # Capture screen
        screenshot = ImageGrab.grab()
        
        # Save to temp file then read
        temp_path = Path(tempfile.gettempdir()) / filename
        screenshot.save(temp_path)
        
        # Read and encode image
        with open(temp_path, "rb") as f:
            image_data = f.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
            print(f"✅ Screenshot captured and encoded ({len(base64_image)} chars)")
            
            # Also save to current directory for reference
            local_path = Path(filename)
            screenshot.save(local_path)
            print(f"💾 Saved copy to: {local_path.absolute()}")
            
            return base64_image
            
    except Exception as e:
        print(f"❌ Error capturing screenshot: {e}")
        print("\n💡 Troubleshooting:")
        print("   - Install Pillow: pip install Pillow")
        print("   - On Windows, also install: pip install pywin32")
        return None

def test_vision_with_gemma(base64_image, prompt):
    """Test vision capabilities using gemma3:27b"""
    print(f"\n🤖 Sending to gemma3:27b for analysis...")
    print(f"   Prompt: {prompt}")
    
    try:
        # Create client with gemma3:27b for vision
        client = OllamaClient(model="gemma3:27b")
        
        # Call vision endpoint
        response = client.chat_with_image(
            image_base64=base64_image,
            prompt=prompt
        )
        
        if response:
            print("\n💬 Gemma Response:")
            print("=" * 60)
            print(response)
            print("=" * 60)
            return True
        else:
            print("❌ No response from model")
            return False
            
    except Exception as e:
        print(f"❌ Vision test failed: {e}")
        return False

def test_specific_tasks(base64_image):
    """Run specific vision tests"""
    tests = [
        ("Describe what you see in detail", "General Description"),
        ("Find all buttons on the screen and describe their positions", "Button Detection"),
        ("What application windows are currently open?", "Window Detection"),
        ("Read any visible text on the screen", "OCR Text Reading"),
        ("Are there any error messages or notifications?", "Error Detection"),
        ("What is the current time shown on the screen?", "Time Recognition"),
    ]
    
    results = []
    
    for prompt, test_name in tests:
        print(f"\n{'='*60}")
        print(f"🧪 TEST: {test_name}")
        print(f"{'='*60}")
        
        success = test_vision_with_gemma(base64_image, prompt)
        results.append((test_name, success))
        
        # Brief pause between tests
        import time
        time.sleep(1)
    
    return results

def main():
    print("=" * 60)
    print("🔍 JARVIS VISION TEST SUITE")
    print("   Model: gemma3:27b (Vision)")
    print("   Purpose: Test screen analysis capabilities")
    print("=" * 60)
    
    # Step 1: Capture screenshot
    base64_image = capture_and_encode_screenshot()
    
    if not base64_image:
        print("\n❌ Cannot proceed without screenshot")
        return
    
    # Step 2: Run general test
    print(f"\n{'='*60}")
    print("🧪 TEST 1: General Screen Analysis")
    print(f"{'='*60}")
    test_vision_with_gemma(base64_image, "Describe everything you see on this screen in detail.")
    
    # Step 3: Run specific tests
    print("\n" + "=" * 60)
    choice = input("\nRun specific vision tests? (y/n): ").strip().lower()
    
    if choice == 'y':
        results = test_specific_tasks(base64_image)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} - {test_name}")
        
        passed = sum(1 for _, s in results if s)
        total = len(results)
        print(f"\nTotal: {passed}/{total} tests passed")
    
    # Step 4: Interactive mode
    print("\n" + "=" * 60)
    print("💬 INTERACTIVE MODE")
    print("=" * 60)
    print("Type your own questions about the screen (or 'quit' to exit)")
    
    while True:
        user_prompt = input("\nYour question: ").strip()
        
        if user_prompt.lower() in ['quit', 'exit', 'q']:
            break
        
        if user_prompt:
            test_vision_with_gemma(base64_image, user_prompt)
    
    print("\n✅ Vision test completed!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
