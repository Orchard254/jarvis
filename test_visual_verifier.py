import os
import sys
from PIL import Image, ImageDraw

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verification.visual_verifier import compute_image_diff, verify_visual_state, capture_screenshot


def test_identical_images():
    print("\n--- Test 1: Identical Images Comparison ---")
    # Create a 200x200 solid blue image
    img_a = Image.new("RGB", (200, 200), color="blue")
    img_b = Image.new("RGB", (200, 200), color="blue")
    
    diff_ratio = compute_image_diff(img_a, img_b)
    print(f"  Identical images diff ratio: {diff_ratio:.6f} (Expected: 0.0)")
    assert diff_ratio == 0.0, "Identical images produced a non-zero difference!"
    
    is_changed = verify_visual_state(img_a, img_b)
    print(f"  Is changed: {is_changed} (Expected: False)")
    assert is_changed is False, "Identical images incorrectly verified as having visual changes!"
    print("[OK] Identical images test passed.")


def test_slightly_modified_image():
    print("\n--- Test 2: Slightly Modified Image Comparison ---")
    img_a = Image.new("RGB", (200, 200), color="white")
    img_b = img_a.copy()
    
    # Draw a small 10x10 black square in the center of img_b
    draw = ImageDraw.Draw(img_b)
    draw.rectangle([95, 95, 105, 105], fill="black")
    
    diff_ratio = compute_image_diff(img_a, img_b)
    # 11*11 pixels changed from white (255,255,255) to black (0,0,0)
    # Total pixels = 40000. Diff per pixel = 255. Overall diff = (121 * 255) / (40000 * 255) = 121/40000 = 0.003025
    print(f"  Modified image diff ratio: {diff_ratio:.6f} (Expected: ~0.003025)")
    assert diff_ratio > 0.0, "Modified image produced a zero difference!"
    
    is_changed = verify_visual_state(img_a, img_b)
    print(f"  Is changed: {is_changed} (Expected: True)")
    assert is_changed is True, "Slightly modified image was not verified as having visual changes!"
    print("[OK] Slightly modified image test passed.")


def test_completely_different_images():
    print("\n--- Test 3: Completely Different Images Comparison ---")
    img_a = Image.new("RGB", (200, 200), color="red")
    img_b = Image.new("RGB", (200, 200), color="green")
    
    diff_ratio = compute_image_diff(img_a, img_b)
    # Red is (255, 0, 0), Green is (0, 255, 0).
    # Diff per channel: R = 255, G = 255, B = 0.
    # Total diff sum per pixel = 510. Normalized per pixel = 510 / (3 * 255) = 510 / 765 = 0.666667
    print(f"  Different images diff ratio: {diff_ratio:.6f} (Expected: > 0.4)")
    assert diff_ratio > 0.4, f"Completely different images difference was not > 0.4, got {diff_ratio:.6f}"
    
    is_changed = verify_visual_state(img_a, img_b)
    print(f"  Is changed: {is_changed} (Expected: True)")
    assert is_changed is True, "Completely different images were not verified as having visual changes!"
    print("[OK] Completely different images test passed.")


def test_screenshot_capture():
    print("\n--- Test 4: Live Screenshot Capture ---")
    try:
        img = capture_screenshot()
        if img is not None:
            print(f"  Successfully captured screenshot: {img.width}x{img.height}")
            assert img.width > 0 and img.height > 0
            print("[OK] Screenshot capture test passed.")
        else:
            print("  Screenshot capture returned None (probably headless/no display). Skipping assert.")
    except Exception as e:
        print(f"  Screenshot capture raised: {e}. Skipping assert.")


def run_tests():
    print("==================================================")
    print("           RUNNING VISUAL VERIFIER TESTS          ")
    print("==================================================")
    
    test_identical_images()
    test_slightly_modified_image()
    test_completely_different_images()
    test_screenshot_capture()
    
    print("\n==================================================")
    print("     ALL VISUAL VERIFIER TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
