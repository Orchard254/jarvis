"""
Digital Signal Processing (DSP) Speech Noise Reduction engine.
Applies mathematical high-pass filtering and soft dynamic noise gating to clean speech inputs.
"""

import logging
import math
import numpy as np

logger = logging.getLogger(__name__)

# Check if scipy is available for C-compiled butterworth filtering
try:
    from scipy.signal import butter, lfilter
    _has_scipy = True
except ImportError:
    _has_scipy = False


def _numpy_hpf_first_order(x: np.ndarray, sample_rate: int, cutoff: float) -> np.ndarray:
    """Apply a single-pass first-order IIR high-pass filter."""
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    
    y = np.zeros_like(x)
    last_y = 0.0
    last_x = x[0] if len(x) > 0 else 0.0
    
    for i in range(len(x)):
        cur_x = x[i]
        last_y = alpha * (last_y + cur_x - last_x)
        y[i] = last_y
        last_x = cur_x
    return y


def high_pass_filter(data: np.ndarray, sample_rate: int = 16000, cutoff: float = 80.0) -> np.ndarray:
    """
    Apply a second-order high-pass filter to eliminate sub-bass rumble (<80Hz)
    like AC noise, traffic rumble, hum, or microphone DC bias.
    Uses compiled scipy 2nd-order Butterworth filter if available, falling back
    to chaining two 1st-order IIR filters in series for a steep 12dB/octave roll-off.
    """
    if len(data) == 0:
        return data

    if _has_scipy:
        try:
            nyq = 0.5 * sample_rate
            normal_cutoff = cutoff / nyq
            b, a = butter(2, normal_cutoff, btype="high", analog=False)
            filtered = lfilter(b, a, data.astype(np.float32))
            return np.clip(filtered, -32768, 32767).astype(np.int16)
        except Exception as e:
            logger.debug(f"Scipy high-pass failed, falling back to numpy: {e}")

    # Pure NumPy recursive fallback: chain two 1st-order filters in series
    # to achieve a 2nd-order slope response.
    x = data.astype(np.float32)
    y1 = _numpy_hpf_first_order(x, sample_rate, cutoff)
    y2 = _numpy_hpf_first_order(y1, sample_rate, cutoff)

    return np.clip(y2, -32768, 32767).astype(np.int16)


def noise_gate(
    data: np.ndarray,
    sample_rate: int = 16000,
    threshold_ratio: float = 1.6,
    attenuation: float = 0.02,
) -> np.ndarray:
    """
    A Soft Dynamic Noise Gate that analyzes the signal energy in 20ms frames,
    automatically profiles the ambient noise floor using the quietest sections,
    and applies a smoothly-interpolated gain envelope to silence background hiss.
    """
    if len(data) == 0:
        return data

    # 20ms frames, 10ms overlap
    frame_len = int(sample_rate * 0.02)
    step = frame_len // 2

    if len(data) < frame_len:
        return data

    # 1. Profile energy in short frames
    rms_list = []
    frames_indices = []

    for i in range(0, len(data) - frame_len, step):
        frame = data[i : i + frame_len].astype(np.float32)
        rms = np.sqrt(np.mean(frame**2) + 1e-10)
        rms_list.append(rms)
        frames_indices.append(i + step)

    if not rms_list:
        return data

    # 2. Self-calibrate background noise floor from the bottom 15% quietest frames
    sorted_rms = sorted(rms_list)
    num_quiet_frames = max(1, int(len(sorted_rms) * 0.15))
    noise_floor = np.mean(sorted_rms[:num_quiet_frames])

    # 3. Calculate dynamic gains per frame using a dual-threshold soft knee
    threshold_low = noise_floor * 1.15
    threshold_high = noise_floor * threshold_ratio
    frame_gains = []

    for rms in rms_list:
        if rms < threshold_low:
            gain = attenuation
        elif rms < threshold_high:
            # Soft gating inside the transition knee: smooth quadratic interpolation
            ratio = (rms - threshold_low) / (threshold_high - threshold_low + 1e-10)
            gain = attenuation + (1.0 - attenuation) * (ratio**2)
        else:
            gain = 1.0
        frame_gains.append(gain)

    # 4. Interpolate frame gains to full sample resolution
    x_coords = np.array(frames_indices)
    y_gains = np.array(frame_gains)

    # Map gains to each sample in the array
    gain_envelope = np.interp(
        np.arange(len(data)), x_coords, y_gains, left=attenuation, right=attenuation
    )

    # 5. Smooth the gain envelope with a 15ms moving average to eliminate click transients
    smoothing_len = int(sample_rate * 0.015)
    if smoothing_len > 1:
        gain_envelope = np.convolve(
            gain_envelope, np.ones(smoothing_len) / smoothing_len, mode="same"
        )

    # 6. Apply gain envelope
    gated_data = data.astype(np.float32) * gain_envelope
    return np.clip(gated_data, -32768, 32767).astype(np.int16)


def reduce_noise(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    sample_width: int = 2,
) -> bytes:
    """
    High-level DSP wrapper to clean up PCM audio bytes.
    Accepts 16-bit mono PCM bytes, filters out rumble and hiss, and returns cleaned PCM bytes.
    """
    if sample_width != 2:
        # We only process 16-bit PCM (standard for STT); pass others through unchanged
        logger.debug(f"DSP: skipped noise reduction — unsupported sample width {sample_width}")
        return audio_bytes

    try:
        # Convert raw PCM bytes to NumPy array (int16 mono)
        data = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # Phase A: Eliminate sub-bass hum and microphone DC offset (<80Hz)
        hpf_data = high_pass_filter(data, sample_rate, cutoff=80.0)
        
        # Phase B: Apply soft noise gate to silence room hiss and fan noise between words
        cleaned_data = noise_gate(hpf_data, sample_rate, threshold_ratio=1.6, attenuation=0.02)
        
        logger.info(f"DSP: successfully processed {len(data)} samples of speech audio")
        return cleaned_data.tobytes()

    except Exception as exc:
        logger.error(f"DSP: failed to process speech audio — {exc}", exc_info=True)
        return audio_bytes
