import os
import sys
import numpy as np

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from perception.dsp import high_pass_filter, noise_gate, reduce_noise


def test_high_pass_filter():
    print("\n--- Test 1: High-Pass Filter Frequency Attenuation ---")
    sample_rate = 16000
    duration = 1.0  # 1 second
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # 1. Generate 30 Hz sub-bass room rumble/hum (should be filtered out)
    rumble_freq = 30.0
    rumble = np.sin(2 * np.pi * rumble_freq * t) * 10000.0
    
    # 2. Generate 400 Hz human vocal frequency tone (should be preserved)
    vocal_freq = 400.0
    vocal = np.sin(2 * np.pi * vocal_freq * t) * 10000.0
    
    # Combined composite signal
    composite = (rumble + vocal).astype(np.int16)
    
    # Run filter at 80 Hz cutoff
    filtered = high_pass_filter(composite, sample_rate, cutoff=80.0)
    
    # Convert to float for analysis
    filtered_float = filtered.astype(np.float32)
    
    # Compute FFT to verify frequency attenuation
    fft_composite = np.abs(np.fft.rfft(composite))
    fft_filtered = np.abs(np.fft.rfft(filtered))
    freqs = np.fft.rfftfreq(len(composite), 1.0 / sample_rate)
    
    # Find bin indices for 30 Hz and 400 Hz
    bin_30 = np.argmin(np.abs(freqs - 30.0))
    bin_400 = np.argmin(np.abs(freqs - 400.0))
    
    # Measure power ratios
    rumble_attenuation = fft_filtered[bin_30] / (fft_composite[bin_30] + 1e-10)
    vocal_preservation = fft_filtered[bin_400] / (fft_composite[bin_400] + 1e-10)
    
    print(f"  Rumble (30Hz) remaining amplitude ratio: {rumble_attenuation:.4f} (Expected < 0.25)")
    print(f"  Vocal (400Hz) remaining amplitude ratio: {vocal_preservation:.4f} (Expected > 0.85)")
    
    assert rumble_attenuation < 0.25, f"High-pass failed to filter out 30Hz hum (ratio: {rumble_attenuation})"
    assert vocal_preservation > 0.85, f"High-pass accidentally muted 400Hz vocal frequency (ratio: {vocal_preservation})"
    print("[OK] High-Pass filter successfully cleaned room rumble and hum!")


def test_noise_gate():
    print("\n--- Test 2: Dynamic Soft Noise Gate Enforcement ---")
    sample_rate = 16000
    
    # Generate 1.0s speech burst, and 1.0s silence containing static room hiss
    t_half = np.linspace(0, 1.0, sample_rate, False)
    
    # Speaks a loud 400Hz vocal tone
    speech_signal = np.sin(2 * np.pi * 400.0 * t_half) * 10000.0
    
    # Silent background contains faint white noise hum (amplitude 200)
    np.random.seed(42)
    noise_signal = np.random.normal(0, 200.0, sample_rate)
    
    # Combined audio: Speech first, then background noise hiss
    combined = np.concatenate((speech_signal, noise_signal)).astype(np.int16)
    
    # Apply soft gate with 0.02 (2%) attenuation for gated silent frames
    gated = noise_gate(combined, sample_rate, threshold_ratio=1.6, attenuation=0.02)
    
    # Analyze RMS of gated speech section vs gated noise section
    speech_gated = gated[:sample_rate].astype(np.float32)
    noise_gated = gated[sample_rate:].astype(np.float32)
    
    rms_speech_orig = np.sqrt(np.mean(speech_signal**2))
    rms_speech_gated = np.sqrt(np.mean(speech_gated**2))
    
    rms_noise_orig = np.sqrt(np.mean(noise_signal**2))
    rms_noise_gated = np.sqrt(np.mean(noise_gated**2))
    
    noise_suppression = rms_noise_gated / (rms_noise_orig + 1e-10)
    speech_preservation = rms_speech_gated / (rms_speech_orig + 1e-10)
    
    print(f"  Speech section energy preservation ratio: {speech_preservation:.4f} (Expected > 0.85)")
    print(f"  Noise section energy remaining ratio:     {noise_suppression:.4f} (Expected < 0.15)")
    
    assert speech_preservation > 0.85, f"Noise gate ruined vocal speech burst (ratio: {speech_preservation})"
    assert noise_suppression < 0.15, f"Noise gate failed to silence background hiss (ratio: {noise_suppression})"
    print("[OK] Soft Dynamic Noise Gate successfully silenced silent gaps!")


def test_wrapper_processing():
    print("\n--- Test 3: Wrapper Processing Interface ---")
    sample_rate = 16000
    # Create 0.5s of random raw bytes (16-bit PCM, mono)
    raw_samples = np.random.randint(-10000, 10000, sample_rate // 2, dtype=np.int16)
    raw_bytes = raw_samples.tobytes()
    
    cleaned_bytes = reduce_noise(raw_bytes, sample_rate=sample_rate, sample_width=2)
    
    # Assert length and format remains exactly preserved
    assert len(cleaned_bytes) == len(raw_bytes), "Wrapper modified raw PCM audio buffer size"
    print("[OK] Wrapper completed execution successfully!")


def run_tests():
    print("==================================================")
    print("               RUNNING DSP TESTS                  ")
    print("==================================================")
    
    test_high_pass_filter()
    test_noise_gate()
    test_wrapper_processing()
    
    print("\n==================================================")
    print("         ALL DSP TESTS PASSED SUCCESSFULY!        ")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
