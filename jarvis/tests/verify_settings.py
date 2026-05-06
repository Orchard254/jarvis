#!/usr/bin/env python3
"""
JARVIS Settings Verification Tool

Run this script to verify your .env configuration before starting JARVIS.

Usage:
    python verify_settings.py
"""

import sys
from pathlib import Path

print("\n" + "═" * 54)
print("  JARVIS SETTINGS VERIFICATION")
print("═" * 54 + "\n")

# Check .env exists
env_path = Path(".env")
if env_path.exists():
    print("✓ .env file found")
else:
    print("✗ .env file NOT found")
    print("  Run: cp .env.example .env")
    print("  Then fill in your values\n")
    sys.exit(1)

# Load and check all settings
try:
    import settings
    print("✓ settings.py loaded successfully\n")
except Exception as e:
    print(f"✗ settings.py failed to load: {e}\n")
    sys.exit(1)

# Check each setting
checks = [
    # (setting_name, value, is_critical, description)
    ("OLLAMA_API_KEY", settings.OLLAMA_API_KEY, 
     True, "Required for cloud LLM"),
    
    ("OLLAMA_CLOUD_URL", settings.OLLAMA_CLOUD_URL,
     True, "Cloud endpoint"),
    
    ("OLLAMA_LOCAL_URL", settings.OLLAMA_LOCAL_URL,
     False, "Local fallback endpoint"),
    
    ("OLLAMA_MODEL", settings.OLLAMA_MODEL,
     True, "LLM model name"),
    
    ("OLLAMA_MODE", settings.OLLAMA_MODE,
     True, "cloud/local/auto"),
    
    ("TTS_ENGINE", settings.TTS_ENGINE,
     True, "kokoro or piper"),
    
    ("KOKORO_VOICE", settings.KOKORO_VOICE,
     False, "TTS voice name"),
    
    ("WAKE_WORD", settings.WAKE_WORD,
     False, "Wake word model"),
    
    ("CONTINUOUS_MODE", settings.CONTINUOUS_MODE,
     False, "Always listening mode"),
    
    ("WEATHER_API_KEY", settings.WEATHER_API_KEY,
     False, "Optional - weather tool"),
    
    ("NEWS_API_KEY", settings.NEWS_API_KEY,
     False, "Optional - news skill"),
]

critical_failures = []
warnings = []

for name, value, critical, desc in checks:
    if value:
        display = str(value)
        # Mask sensitive values
        if "KEY" in name or "TOKEN" in name or "SECRET" in name:
            display = value[:4] + "****" + value[-4:] \
                      if len(value) > 8 else "****"
        print(f"  ✓ {name:<30} {display}")
    else:
        if critical:
            print(f"  ✗ {name:<30} NOT SET ← CRITICAL")
            critical_failures.append(f"{name}: {desc}")
        else:
            print(f"  ⚠ {name:<30} not set (optional)")
            warnings.append(f"{name}: {desc}")

# Test Ollama connectivity
print("\n─ Testing Connections ─────────────────────────")
try:
    import requests
    
    try:
        r = requests.get(
            settings.OLLAMA_CLOUD_URL.replace("/api/chat", ""),
            timeout=3
        )
        print("  ✓ Cloud Ollama reachable")
    except Exception:
        print("  ✗ Cloud Ollama unreachable")
        if settings.OLLAMA_MODE == "cloud":
            critical_failures.append("Cloud Ollama unreachable")
    
    try:
        r = requests.get(settings.OLLAMA_LOCAL_URL.replace("/api/chat", ""), timeout=2)
        print("  ✓ Local Ollama reachable")
    except Exception:
        print("  ⚠ Local Ollama not running (optional fallback)")
except ImportError:
    print("  ⚠ requests library not available for connectivity test")

# Final result
print("\n" + "═" * 54)
if critical_failures:
    print("  RESULT: ✗ CRITICAL ISSUES FOUND")
    print("\n  Fix these before starting JARVIS:")
    for f in critical_failures:
        print(f"    • {f}")
    print()
    sys.exit(1)
elif warnings:
    print("  RESULT: ⚠ READY WITH WARNINGS")
    print("\n  Optional settings not configured:")
    for w in warnings:
        print(f"    • {w}")
    print("\n  JARVIS will start but some features")
    print("  may be unavailable.")
else:
    print("  RESULT: ✓ ALL SETTINGS VERIFIED")
    print("  JARVIS is ready to start.")
print("═" * 54 + "\n")
