#!/usr/bin/env python3
"""
KOKORO TTS VOICE SELECTOR

Quick way to test different voices without loading the full JARVIS system.
Just run: python test_tts_voices.py
"""

import os
import sys
import warnings

# Suppress PyTorch warnings
warnings.filterwarnings("ignore")

# Add venv to path
venv_path = os.path.join(os.path.dirname(__file__), "venv", "Lib", "site-packages")
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

import numpy as np
import sounddevice as sd
from kokoro import KPipeline

# Voice list - American English voices
VOICES = [
    ("af_heart", "Female - warm, conversational"),
    ("af_bella", "Female - clear, pleasant"),
    ("af_nicole", "Female - neutral, professional"),
    ("af_sarah", "Female - soft, friendly"),
    ("af_sky", "Female - bright, energetic"),
    ("am_adam", "Male - deep, authoritative"),
    ("am_michael", "Male - casual, friendly"),
    ("bf_emma", "Female British - proper"),
    ("bf_isabella", "Female British - warm"),
    ("bm_george", "Male British - formal"),
    ("bm_lewis", "Male British - young"),
]

TEST_PHRASES = [
    "Hello! I am SYNTH. Your personal AI assistant.",
    "The current time is 3:45 PM.",
    "Battery is at 85 percent and charging.",
    "Volume is set to 50 percent.",
    "What can I help you with today?",
]


def play_audio(audio_data, sample_rate=24000):
    """Play audio through speakers."""
    audio = np.concatenate(audio_data)
    audio = audio.astype(np.float32)

    # Normalize
    max_val = np.abs(audio).max()
    if max_val > 0:
        audio = audio / max_val

    sd.play(audio, samplerate=sample_rate)
    sd.wait()


def main():
    print("\n" + "=" * 54)
    print("  KOKORO TTS VOICE SELECTOR")
    print("=" * 54)
    print(f"\nVoices available: {len(VOICES)}")
    print("-" * 54)
    for i, (name, desc) in enumerate(VOICES):
        print(f"  {i+1:2}. {name:<15} - {desc}")
    print("-" * 54)
    print("\nCommands:")
    print("  <number>  - Select voice and play test phrase")
    print("  p/n       - Previous/next voice")
    print("  t         - Play all test phrases")
    print("  q         - Quit")
    print("=" * 54 + "\n")

    # Initialize pipeline once
    print("Loading Kokoro pipeline...")
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    current = 0

    while True:
        try:
            cmd = input(f"[{VOICES[current][0]}]> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "q":
            break

        if cmd == "p":
            current = (current - 1) % len(VOICES)
            print(f"  Switched to: {VOICES[current][0]}")
            continue

        if cmd == "n":
            current = (current + 1) % len(VOICES)
            print(f"  Switched to: {VOICES[current][0]}")
            continue

        if cmd == "t":
            # Play all phrases with current voice
            voice_name = VOICES[current][0]
            print(f"  Playing {len(TEST_PHRASES)} phrases with {voice_name}...")
            for phrase in TEST_PHRASES:
                print(f"    '{phrase[:40]}...'")
                audio_data = []
                for _, _, audio in pipeline(phrase, voice=voice_name, speed=1.15):
                    audio_data.append(audio)
                if audio_data:
                    play_audio(audio_data)
            continue

        # Try to parse as number
        try:
            n = int(cmd)
            if 1 <= n <= len(VOICES):
                current = n - 1
            else:
                print(f"  Use 1-{len(VOICES)}")
                continue
        except ValueError:
            print(f"  Unknown: '{cmd}'. Use p/n/t/q or number")
            continue

        # Play selected voice
        voice_name = VOICES[current][0]
        print(f"  Playing with {voice_name}...")

        audio_data = []
        for _, _, audio in pipeline(TEST_PHRASES[0], voice=voice_name, speed=1.15):
            audio_data.append(audio)

        if audio_data:
            play_audio(audio_data)
        else:
            print("  No audio generated!")

    print("\nDone. Run 'python jarvis.py' to start JARVIS.")


if __name__ == "__main__":
    main()
