"""
Visual Verification module.
Provides screenshot capturing, average pixel difference analysis, and visual change verification.
"""

import logging
from PIL import Image, ImageChops, ImageStat

logger = logging.getLogger(__name__)


def capture_screenshot() -> Image.Image:
    """
    Capture a screenshot of the primary screen using PyAutoGUI.
    """
    try:
        import pyautogui
        return pyautogui.screenshot()
    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}")
        return None


def compute_image_diff(img_a: Image.Image, img_b: Image.Image) -> float:
    """
    Compares two PIL Images of identical size.
    Computes the average pixel-by-pixel difference (L1 norm).
    Returns a change ratio between 0.0 (identical) and 1.0 (completely different).
    """
    if not img_a or not img_b:
        return 0.0
    if img_a.size != img_b.size:
        return 1.0

    try:
        # Convert both images to RGB to ensure identical channel counts
        img_a_rgb = img_a.convert("RGB")
        img_b_rgb = img_b.convert("RGB")
        
        diff = ImageChops.difference(img_a_rgb, img_b_rgb)
        stat = ImageStat.Stat(diff)
        
        # stat.mean returns a list of average difference for each channel (R, G, B)
        # Normalizing by dividing by 255.0 to get a ratio between 0.0 and 1.0
        mean_diff = sum(stat.mean) / (len(stat.mean) * 255.0)
        return mean_diff
    except Exception as e:
        logger.error(f"Failed to compute image diff: {e}")
        return 0.0


def verify_visual_state(pre_img: Image.Image, post_img: Image.Image, action_type: str = None) -> bool:
    """
    Verifies that the visual state of the screen changed between pre-action and post-action screenshots.
    If the difference ratio is below the threshold, it means a 'dead click' or no action took place.
    """
    if not pre_img or not post_img:
        logger.warning("Visual verification skipped: pre_img or post_img is missing.")
        return True

    ratio = compute_image_diff(pre_img, post_img)
    # A standard cursor blink or minor screen noise can be up to 0.0001. 
    # A genuine click/keyboard visual update is usually > 0.0005.
    threshold = 0.0005

    logger.info(f"Visual verifier computed diff ratio: {ratio:.6f} against threshold: {threshold:.6f}")
    if ratio < threshold:
        return False
    return True
