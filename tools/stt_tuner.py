"""
Standalone STT Tuner — test, compare & improve speech recognition accuracy
without loading the full Jarvis system.

Usage:
    python tools/stt_tuner.py test-mic           # List mics + calibrate noise floor
    python tools/stt_tuner.py transcribe         # Record & transcribe (Google or Whisper)
    python tools/stt_tuner.py compare            # Same recording → Google vs Whisper side-by-side
    python tools/stt_tuner.py file <path>        # Transcribe an audio file
    python tools/stt_tuner.py benchmark          # Run predefined test phrases
    python tools/stt_tuner.py interactive        # Loop: record → show result → tweak settings

Pass --help on any subcommand for details.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Ensure parent is on path so we can import settings directly
_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

# ── Minimal settings bootstrap (we don't import the real settings to stay standalone) ──
# We still import the real settings for defaults, but override via CLI flags.

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-5s %(message)s",
)
logger = logging.getLogger("stt_tuner")
logger.setLevel(logging.INFO)

# Lazy imports — only loaded when needed
_sr = None
_whisper_lib = None
_whisper_model = None


def _get_sr():
    global _sr
    if _sr is None:
        import speech_recognition as sr
        _sr = sr
    return _sr


def _get_whisper():
    global _whisper_lib, _whisper_model
    if _whisper_lib is None:
        try:
            import whisper
            _whisper_lib = whisper
        except ImportError:
            return None
    if _whisper_model is None:
        _whisper_model = _whisper_lib.load_model("tiny")
    return _whisper_lib


# ── Config ──────────────────────────────────────────────────────────────────────

@dataclass
class STTConfig:
    engine: str = "google"           # google | whisper
    language: str = "en-US"
    sample_rate: int = 16000
    mic_device: int = -1             # -1 = default
    timeout: float = 5.0
    phrase_limit: int = 15
    dynamic_energy: bool = True
    energy_threshold: Optional[int] = None
    pause_threshold: float = 1.5
    whisper_model: str = "tiny"      # tiny | base | small | medium | large
    preprocess: bool = False
    save_wav: Optional[str] = None
    use_vad: bool = False


# ── Audio preprocessing ─────────────────────────────────────────────────────────

def _denoise_audio(wav_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Apply spectral noise reduction via noisereduce."""
    import io
    import wave
    import numpy as np

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, 'r') as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)

    try:
        import noisereduce as nr
        # noisereduce works on the full signal; it automatically profiles noise
        # Reduced prop_decrease from 0.85 to 0.5 to avoid speech distortion
        reduced = nr.reduce_noise(y=audio, sr=sample_rate, prop_decrease=0.5)
    except Exception:
        # fallback: simple high-pass filter at 80Hz to cut rumble
        from scipy.signal import butter, sosfilt
        sos = butter(4, 80 / (sample_rate / 2), btype='high', output='sos')
        reduced = sosfilt(sos, audio).astype(np.float32)

    # Normalize after processing to avoid clipping
    peak = np.max(np.abs(reduced)) or 1
    reduced = reduced * (0.9 * 32767 / peak)
    out_frames = reduced.astype(np.int16).tobytes()

    out = io.BytesIO()
    with wave.open(out, 'w') as wf:
        wf.setparams(params)
        wf.writeframes(out_frames)
    return out.getvalue()


def _audio_data_from_wav_bytes(raw: bytes):
    """Reconstruct speech_recognition AudioData from WAV bytes."""
    import io
    import wave
    sr = _get_sr()
    buf = io.BytesIO(raw)
    with wave.open(buf, 'r') as wf:
        frames = wf.readframes(wf.getnframes())
    return sr.AudioData(frames, sample_rate=wf.getframerate(), sample_width=wf.getsampwidth())


def _preprocess_audio(audio_data) -> tuple:
    """
    Apply preprocessing to AudioData. Returns (processed_audio_data, error_string).
    Applies: noise reduction → normalise volume.
    """
    try:
        raw = audio_data.get_wav_data()
        raw = _denoise_audio(raw, audio_data.sample_rate)
        processed = _audio_data_from_wav_bytes(raw)
        return processed, None
    except Exception as e:
        return audio_data, str(e)


def _save_wav(audio_data, path: str):
    """Write AudioData to a WAV file for offline inspection."""
    try:
        raw = audio_data.get_wav_data()
        Path(path).write_bytes(raw)
        return True
    except Exception as e:
        print(f"  Warning: could not save WAV — {e}")
        return False


# ── Audio utilities ─────────────────────────────────────────────────────────────

def list_microphones() -> list[dict]:
    """Return all available microphone devices."""
    sr = _get_sr()
    results = []
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        results.append({"index": i, "name": name})
    return results


def _build_recognizer(cfg: STTConfig):
    sr = _get_sr()
    r = sr.Recognizer()
    r.dynamic_energy_threshold = cfg.dynamic_energy
    r.pause_threshold = cfg.pause_threshold
    if cfg.energy_threshold is not None:
        r.energy_threshold = cfg.energy_threshold
        r.dynamic_energy_threshold = False
    return r


def _capture_mic(cfg: STTConfig) -> tuple:
    """
    Capture audio from mic using sounddevice + ring buffer + energy VAD.
    Ring buffer ensures first word is never clipped.
    Energy VAD with generous silence timeout prevents mid-sentence cutoff.
    """
    import numpy as np
    import sounddevice as sd
    from collections import deque

    LOOKBACK_SEC = 0.5
    FRAME_MS = 30
    frame_samples = int(cfg.sample_rate * FRAME_MS / 1000)
    max_silence_frames = int(cfg.pause_threshold * 1000 / FRAME_MS)
    ring_max = int(LOOKBACK_SEC * cfg.sample_rate)

    try:
        stream = sd.RawInputStream(
            samplerate=cfg.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
            device=cfg.mic_device if cfg.mic_device != -1 else None,
        )
    except Exception as e:
        return None, f"Mic error: {e}"

    ring = deque(maxlen=ring_max)
    speech = []
    state = "idle"
    silence_frames = 0
    elapsed = 0.0
    frame_sec = FRAME_MS / 1000
    energy_threshold = cfg.energy_threshold or 200

    print(f"  (energy threshold={energy_threshold}, listen...)", end=" ", flush=True)

    with stream:
        while True:
            data, _ = stream.read(frame_samples)
            buf = bytes(data)
            elapsed += frame_sec

            # Compute RMS energy
            samples = np.frombuffer(buf, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples ** 2))
            is_speech = rms > energy_threshold

            ring.append(samples)

            if elapsed > cfg.timeout and state == "idle":
                print("timeout")
                return None, "timeout"

            if state == "idle":
                if is_speech:
                    state = "speech"
                    speech = list(ring)
                    speech.append(samples)
                    silence_frames = 0
                    print("speaking...", end=" ", flush=True)

            elif state == "speech":
                speech.append(samples)
                if is_speech:
                    silence_frames = 0
                else:
                    silence_frames += 1
                    if silence_frames >= max_silence_frames:
                        break

    if not speech:
        print("no speech")
        return None, "timeout"

    sr = _get_sr()
    merged = np.concatenate(speech).astype(np.int16)
    audio = sr.AudioData(merged.tobytes(), sample_rate=cfg.sample_rate, sample_width=2)
    print()
    return audio, None


def _capture_from_file(path: str, cfg: STTConfig):
    """Load audio from file into an AudioData object."""
    sr = _get_sr()
    try:
        with sr.AudioFile(path) as source:
            r = _build_recognizer(cfg)
            audio = r.record(source)
        return audio, None
    except Exception as e:
        return None, str(e)


# ── Transcription engines ───────────────────────────────────────────────────────

def transcribe_google(audio, language: str) -> tuple[str, float]:
    """Returns (text, confidence). confidence is approximated."""
    sr = _get_sr()
    t0 = time.perf_counter()
    try:
        result = sr.Recognizer().recognize_google(audio, language=language, show_all=True)
        elapsed = time.perf_counter() - t0
        if not result:
            return "", 0.0
        if "alternative" in result:
            alt = result["alternative"][0]
            text = alt.get("transcript", "")
            confidence = alt.get("confidence", 0.0)
            return text.strip(), confidence
        return "", 0.0
    except sr.UnknownValueError:
        return "", 0.0
    except sr.RequestError as e:
        return f"[API error: {e}]", 0.0


def transcribe_whisper(audio, model_name: str = "tiny", language: str = None) -> tuple[str, float]:
    """Returns (text, confidence)."""
    whisper = _get_whisper()
    if whisper is None:
        return "[Whisper not installed]", 0.0

    # Whisper works from file, so write WAV to temp file
    tmp = None
    try:
        wav_bytes = audio.get_wav_data()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name
        t0 = time.perf_counter()
        result = whisper.transcribe(tmp, language=language, fp16=False)
        elapsed = time.perf_counter() - t0
        text = (result.get("text") or "").strip()
        # Whisper doesn't give per-segment confidence by default
        # Use average of segment probabilities if available
        segments = result.get("segments", [])
        if segments:
            avg_conf = sum(s.get("avg_logprob", -1) for s in segments) / len(segments)
            # Convert logprob to pseudo-confidence
            confidence = max(0.0, min(1.0, (avg_conf + 2.5) / 5.0))
        else:
            confidence = 0.0
        return text, confidence
    except Exception as e:
        return f"[Whisper error: {e}]", 0.0
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass


# ── Subcommands ─────────────────────────────────────────────────────────────────

def cmd_list_mics(args):
    """List available microphone devices."""
    mics = list_microphones()
    if not mics:
        print("No microphones found.")
        return
    print(f"\nFound {len(mics)} microphone(s):\n")
    print(f"  {'Index':<6} {'Name'}")
    print(f"  {'-'*5:<6} {'-'*40}")
    for m in mics:
        default = " <- default" if m["index"] == 0 else ""
        print(f"  {m['index']:<6} {m['name']}{default}")
    print("\nUse --mic <index> to select a specific device.")


def cmd_calibrate(args):
    """Measure ambient noise levels."""
    cfg = _config_from_args(args)
    sr = _get_sr()
    mics = list_microphones()
    print(f"\nCalibrating microphone: {cfg.mic_device if cfg.mic_device != -1 else 'default'}")
    if cfg.mic_device != -1:
        info = next((m for m in mics if m["index"] == cfg.mic_device), None)
        if info:
            print(f"  Device: {info['name']}")
    print()

    try:
        kwargs = {"sample_rate": cfg.sample_rate}
        if cfg.mic_device != -1:
            kwargs["device_index"] = cfg.mic_device
        mic = sr.Microphone(**kwargs)
    except Exception as e:
        print(f"  Error opening mic: {e}")
        return

    r = _build_recognizer(cfg)
    with mic as source:
        print("  Measuring ambient noise (2 seconds)...")
        r.adjust_for_ambient_noise(source, duration=2.0)
        print(f"\n  Results:")
        print(f"    Energy threshold:      {r.energy_threshold:.0f}")
        print(f"    Dynamic threshold:     {r.dynamic_energy_threshold}")
        print(f"    Pause threshold:       {r.pause_threshold}s")
        print(f"    Sample rate:           {cfg.sample_rate} Hz")
        print()

        # Additional readings
        thresholds = []
        for i in range(5):
            r.adjust_for_ambient_noise(source, duration=0.3)
            thresholds.append(r.energy_threshold)
        avg = sum(thresholds) / len(thresholds)
        print(f"  Noise floor samples: {[f'{t:.0f}' for t in thresholds]}")
        print(f"  Recommended energy_threshold: {avg * 1.5:.0f} (1.5x noise floor)")
        print(f"  Recommended energy_threshold: {avg * 2.0:.0f} (2.0x noise floor)")
        print()


def cmd_transcribe(args):
    """Record from mic and transcribe."""
    cfg = _config_from_args(args)
    print(f"\n  Engine:    {cfg.engine}")
    print(f"  Language:  {cfg.language}")
    print(f"  Mic:       {cfg.mic_device if cfg.mic_device != -1 else 'default'}")
    print(f"  Timeout:   {cfg.timeout}s")
    print(f"  Phrase:    {cfg.phrase_limit}s max")
    print(f"  Pause:     {cfg.pause_threshold}s silence cutoff")
    if cfg.use_vad:
        print(f"  Capture:    ring buffer + energy VAD (0.5s lookback)")
    if cfg.preprocess:
        print(f"  Preprocess: noise reduction + normalize")
    if cfg.save_wav:
        print(f"  Save WAV:  {cfg.save_wav}")
    print()

    audio, err = _capture_mic(cfg)
    if err:
        print(f"  Capture failed: {err}")
        return

    if cfg.save_wav:
        _save_wav(audio, cfg.save_wav)

    if cfg.preprocess:
        audio, err = _preprocess_audio(audio)
        if err:
            print(f"  Preprocess warning: {err}")

    if cfg.engine == "whisper":
        text, conf = transcribe_whisper(audio, cfg.whisper_model, cfg.language.split("-")[0])
    else:
        text, conf = transcribe_google(audio, cfg.language)

    print(f"\n  Transcription ({cfg.engine}):")
    print(f"    Text:       '{text}'")
    print(f"    Confidence: {conf:.3f}" if conf > 0 else "    Confidence: N/A")
    print()


def cmd_compare(args):
    """Record once, transcribe with both engines side-by-side."""
    cfg = _config_from_args(args)
    print("\n  Recording one utterance for side-by-side comparison...\n")

    # Show preprocessing info
    if cfg.preprocess:
        print("  Preprocessing: noise reduction + normalize will be applied\n")

    audio, err = _capture_mic(cfg)
    if err:
        print(f"  Capture failed: {err}")
        return

    if cfg.save_wav:
        _save_wav(audio, cfg.save_wav)

    if cfg.preprocess:
        audio, err = _preprocess_audio(audio)
        if err:
            print(f"  Preprocess warning: {err}")

    print(f"  {'Engine':<10} {'Text':<50} {'Confidence':<10}")
    print(f"  {'-'*10:<10} {'-'*50:<50} {'-'*10:<10}")

    gtext, gconf = transcribe_google(audio, cfg.language)
    print(f"  {'Google':<10} {gtext[:50]:<50} {gconf:<10.3f}" if gconf > 0 else f"  {'Google':<10} {gtext[:50]:<50} {'N/A':<10}")

    wtext, wconf = transcribe_whisper(audio, cfg.whisper_model)
    print(f"  {'Whisper':<10} {wtext[:50]:<50} {wconf:<10.3f}" if wconf > 0 else f"  {'Whisper':<10} {wtext[:50]:<50} {'N/A':<10}")
    print()

    # Show full texts
    if len(gtext) > 50 or len(wtext) > 50:
        print("  Full texts:")
        print(f"    Google:  {gtext}")
        print(f"    Whisper: {wtext}")
        print()


def cmd_file(args):
    """Transcribe an audio file."""
    path = args.path
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return

    cfg = _config_from_args(args)
    print(f"\n  File:      {path}")
    print(f"  Engine:    {cfg.engine}")
    print(f"  Language:  {cfg.language}")
    print()

    audio, err = _capture_from_file(path, cfg)
    if err:
        print(f"  Error reading file: {err}")
        return

    if cfg.engine == "whisper":
        text, conf = transcribe_whisper(audio, cfg.whisper_model, cfg.language.split("-")[0])
    else:
        text, conf = transcribe_google(audio, cfg.language)

    print(f"  Transcription ({cfg.engine}):")
    print(f"    Text:       '{text}'")
    print(f"    Confidence: {conf:.3f}" if conf > 0 else "    Confidence: N/A")
    print()


def cmd_benchmark(args):
    """Run predefined test phrases through both engines (requires pre-recorded files or live)."""
    cfg = _config_from_args(args)

    phrases = [
        "open chrome browser",
        "what is the weather today",
        "send an email to John",
        "create a new folder called projects",
        "shut down the computer in five minutes",
        "play my music playlist",
        "search for Python tutorial on YouTube",
        "set a timer for ten minutes",
        "what files are on my desktop",
        "turn on Bluetooth",
    ]

    if args.source == "live":
        print(f"\n  Benchmark mode: LIVE ({len(phrases)} phrases)")
        print("  You'll be prompted to speak each phrase.\n")
        results = []
        for i, phrase in enumerate(phrases, 1):
            input(f"  [{i}/{len(phrases)}] Press Enter then say: \"{phrase}\" ")
            audio, err = _capture_mic(cfg)
            if err:
                print(f"    Capture failed: {err}\n")
                continue
            gtext, gconf = transcribe_google(audio, cfg.language)
            wtext, wconf = transcribe_whisper(audio, cfg.whisper_model)
            results.append({
                "expected": phrase,
                "google_text": gtext,
                "google_conf": gconf,
                "whisper_text": wtext,
                "whisper_conf": wconf,
            })
            print(f"    Google:  '{gtext}' (conf={gconf:.3f})")
            print(f"    Whisper: '{wtext}' (conf={wconf:.3f})\n")

        # Summary
        print("=" * 60)
        print("  BENCHMARK SUMMARY")
        print("=" * 60)
        for r in results:
            g_match = _similarity(r["expected"].lower(), r["google_text"].lower())
            w_match = _similarity(r["expected"].lower(), r["whisper_text"].lower())
            print(f"  Expected: {r['expected']}")
            print(f"    Google  ({r['google_conf']:.2f}): {r['google_text']}  [{g_match:.0%} match]")
            print(f"    Whisper ({r['whisper_conf']:.2f}): {r['whisper_text']}  [{w_match:.0%} match]")
            print()

        if results:
            avg_g = sum(r["google_conf"] for r in results) / len(results)
            avg_w = sum(r["whisper_conf"] for r in results) / len(results)
            print(f"  Avg confidence — Google: {avg_g:.3f}, Whisper: {avg_w:.3f}")

        if args.save:
            _save_results(results, args.save)
            print(f"\n  Results saved to {args.save}")

    elif args.source == "dir":
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"Directory not found: {args.dir}")
            return
        wav_files = sorted(dir_path.glob("*.wav")) + sorted(dir_path.glob("*.mp3"))
        if not wav_files:
            print(f"No .wav or .mp3 files found in {args.dir}")
            return
        print(f"\n  Benchmark mode: FILE ({len(wav_files)} files from {args.dir})\n")
        results = []
        for fpath in wav_files:
            audio, err = _capture_from_file(str(fpath), cfg)
            if err:
                print(f"  {fpath.name}: read error — {err}")
                continue
            gtext, gconf = transcribe_google(audio, cfg.language)
            wtext, wconf = transcribe_whisper(audio, cfg.whisper_model)
            expected = fpath.stem.replace("_", " ").replace("-", " ")
            results.append({
                "expected": expected,
                "google_text": gtext,
                "google_conf": gconf,
                "whisper_text": wtext,
                "whisper_conf": wconf,
                "file": fpath.name,
            })
            print(f"  {fpath.name}:")
            print(f"    Google:  '{gtext}' (conf={gconf:.3f})")
            print(f"    Whisper: '{wtext}' (conf={wconf:.3f})")
            print()

        if results:
            avg_g = sum(r["google_conf"] for r in results) / len(results)
            avg_w = sum(r["whisper_conf"] for r in results) / len(results)
            print(f"  Avg confidence — Google: {avg_g:.3f}, Whisper: {avg_w:.3f}")

        if args.save:
            _save_results(results, args.save)


def cmd_interactive(args):
    """Interactive loop — repeatedly record and transcribe with live config tweaks."""
    cfg = _config_from_args(args)
    print("\n  Interactive STT Tuner")
    print("  Commands: !google | !whisper | !lang <code> | !thresh <n> | !mic <n> | !help | !quit")
    print()

    while True:
        try:
            inp = input("  [press Enter to speak, or type a command] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Quit.")
            break

        if not inp:
            audio, err = _capture_mic(cfg)
            if err:
                if err == "timeout":
                    print("  (no speech detected)\n")
                else:
                    print(f"  Error: {err}\n")
                continue
            if cfg.engine == "whisper":
                text, conf = transcribe_whisper(audio, cfg.whisper_model, cfg.language.split("-")[0])
            else:
                text, conf = transcribe_google(audio, cfg.language)
            print(f"  [{cfg.engine}] conf={conf:.3f}: '{text}'\n")
            continue

        parts = inp.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "!quit":
            break
        elif cmd == "!google":
            cfg.engine = "google"
            print(f"  → Engine set to Google STT\n")
        elif cmd == "!whisper":
            cfg.engine = "whisper"
            print(f"  → Engine set to Whisper ({cfg.whisper_model})\n")
        elif cmd == "!lang":
            cfg.language = arg if arg else "en-US"
            print(f"  → Language set to {cfg.language}\n")
        elif cmd == "!thresh":
            try:
                cfg.energy_threshold = int(arg)
                print(f"  → Energy threshold set to {cfg.energy_threshold}\n")
            except ValueError:
                print(f"  Usage: !thresh <number>\n")
        elif cmd == "!mic":
            try:
                cfg.mic_device = int(arg) if arg else -1
                print(f"  → Mic device set to {cfg.mic_device}\n")
            except ValueError:
                print(f"  Usage: !mic <index> | -1 for default\n")
        elif cmd == "!model":
            if arg in ("tiny", "base", "small", "medium", "large"):
                cfg.whisper_model = arg
                global _whisper_model
                _whisper_model = None  # force reload
                print(f"  → Whisper model set to {cfg.whisper_model} (will load on next transcribe)\n")
            else:
                print(f"  Options: tiny, base, small, medium, large\n")
        elif cmd == "!help":
            print("  Commands:")
            print("    !google          — switch to Google STT")
            print("    !whisper          — switch to Whisper local")
            print("    !model <name>     — Whisper model: tiny/base/small/medium/large")
            print("    !lang <code>      — set language (e.g. en-US, fr-FR)")
            print("    !thresh <n>       — set energy threshold (0 = auto)")
            print("    !mic <index>      — select mic device (-1 = default)")
            print("    !help             — this help")
            print("    !quit             — exit")
            print("    [Enter]           — record & transcribe\n")
        else:
            print(f"  Unknown command: {cmd}\n")


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _config_from_args(args) -> STTConfig:
    return STTConfig(
        engine=args.engine or "google",
        language=args.language or "en-US",
        sample_rate=args.sample_rate or 16000,
        mic_device=args.mic if hasattr(args, "mic") else -1,
        timeout=args.timeout or 5.0,
        phrase_limit=args.phrase_limit or 10,
        dynamic_energy=not args.fixed_threshold if hasattr(args, "fixed_threshold") else True,
        energy_threshold=args.threshold if hasattr(args, "threshold") and args.threshold is not None else None,
        pause_threshold=args.pause_threshold if hasattr(args, "pause_threshold") else 1.5,
        preprocess=args.preprocess if hasattr(args, "preprocess") else False,
        save_wav=args.save_wav if hasattr(args, "save_wav") else None,
        use_vad=args.vad if hasattr(args, "vad") else False,
        whisper_model=args.whisper_model or "tiny",
    )


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity."""
    if not a or not b:
        return 0.0
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def _save_results(results: list[dict], path: str):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


# ── CLI entry point ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="STT Tuner — standalone speech recognition testing tool")
    p.add_argument("--engine", choices=["google", "whisper"], default="google", help="STT engine")
    p.add_argument("--language", default="en-US", help="Language code (e.g. en-US, fr-FR)")
    p.add_argument("--sample-rate", type=int, default=16000, help="Audio sample rate")
    p.add_argument("--mic", type=int, default=-1, help="Microphone device index (-1 = default)")
    p.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for speech")
    p.add_argument("--phrase-limit", type=int, default=10, help="Max seconds per phrase")
    p.add_argument("--whisper-model", choices=["tiny", "base", "small", "medium", "large"], default="tiny")
    p.add_argument("--threshold", type=int, default=None, help="Fixed energy threshold (0 = auto)")
    p.add_argument("--pause-threshold", type=float, default=1.5, help="Seconds of silence to end phrase (default 1.5)")
    p.add_argument("--vad", action="store_true", help="Use ring-buffer capture with lookback (no first-word clipping)")
    p.add_argument("--preprocess", action="store_true", help="Noise reduction + volume normalize before transcription")
    p.add_argument("--save-wav", default=None, help="Save raw recording to .wav file for offline inspection")
    p.add_argument("--fixed-threshold", action="store_true", help="Disable dynamic energy threshold")
    p.add_argument("--verbose", action="store_true", help="Show debug logs")

    sub = p.add_subparsers(dest="command", title="commands")

    # list-mics
    sub.add_parser("list-mics", help="List available microphone devices")

    # calibrate
    sub.add_parser("calibrate", help="Measure ambient noise")

    # transcribe
    sub.add_parser("transcribe", help="Record and transcribe")

    # compare
    sub.add_parser("compare", help="Compare Google vs Whisper")

    # file
    fp = sub.add_parser("file", help="Transcribe audio file")
    fp.add_argument("path", help="Path to audio file (.wav / .mp3)")

    # benchmark
    bp = sub.add_parser("benchmark", help="Run accuracy benchmark")
    bp.add_argument("--source", choices=["live", "dir"], default="live", help="Benchmark source")
    bp.add_argument("--dir", default=".", help="Directory with .wav files named by expected phrase")
    bp.add_argument("--save", default=None, help="Save results JSON to this path")

    # interactive
    sub.add_parser("interactive", help="Interactive tuning session")

    return p


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    command_map = {
        "list-mics": cmd_list_mics,
        "calibrate": cmd_calibrate,
        "transcribe": cmd_transcribe,
        "compare": cmd_compare,
        "file": cmd_file,
        "benchmark": cmd_benchmark,
        "interactive": cmd_interactive,
    }

    cmd = args.command
    if cmd is None:
        parser.print_help()
        return

    handler = command_map.get(cmd)
    if handler:
        handler(args)


if __name__ == "__main__":
    main()
