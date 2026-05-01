# Deep investigation of intent classifier issues
import json

import requests

import config
from logger import get_logger

log = get_logger("intent_test")

INTENT_SYSTEM_PROMPT = """You are a deterministic intent classification engine.

SUPPORTED INTENTS:
- screenshot: capture screen
- time: get system time
- open: open application
- close: close application
- volume: adjust system volume
- brightness: adjust screen brightness
- search: web search
- shutdown: shut down system
- lock: lock system

RULES:
1. Interpret FINAL intention (apply corrections: "actually", "wait", "no", "instead", "don't", "forget")
2. Extract ALL valid intents in final meaning
3. Assign confidence: clear=0.90-1.0, implicit=0.60-0.89, weak=0.30-0.59, rejected<=0.20
4. NEVER output only one intent unless only one truly present
5. NEVER drop secondary valid intents

OUTPUT FORMAT (JSON array only):
[{"intent": "<name>", "confidence": <float>}]

NO explanations. NO markdown. JSON only."""

test_cases = [
    "open notepad and write hello world",
    "open calculator and calculate 25 * 8",
    "open chrome and search AI tools",
    "mute volume",
    "increase volume",
    "take a screenshot and open it",
    "open notepad then close it",
]

print("=" * 80)
print("INTENT CLASSIFIER DEEP INVESTIGATION")
print("=" * 80)

for test_text in test_cases:
    print(f"\n{'=' * 80}")
    print(f"TEST: {test_text}")
    print(f"{'=' * 80}")

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": test_text},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 500,
        },
    }

    headers = {
        "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        print("\n[1] Sending request to Ollama Cloud...")
        resp = requests.post(
            config.OLLAMA_CLOUD_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )
        print(f"[2] Response status: {resp.status_code}")

        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()

        print(f"\n[3] RAW LLM OUTPUT ({len(content)} chars):")
        print(f"    {repr(content[:200])}")
        if len(content) > 200:
            print(f"    ... ({len(content) - 200} more chars)")

        print("\n[4] Attempting to parse JSON...")

        # Try different parsing strategies
        strategies = [
            ("Direct parse", lambda c: json.loads(c)),
            (
                "Strip markdown",
                lambda c: json.loads(c.split("```")[-1].split("```")[0] if "```" in c else c),
            ),
            ("Extract array", lambda c: json.loads(c[c.find("[") : c.rfind("]") + 1])),
        ]

        for strategy_name, strategy_func in strategies:
            try:
                result = strategy_func(content)
                print(f"    ✓ {strategy_name}: SUCCESS")
                print(f"      Parsed: {result}")
            except Exception as e:
                print(f"    ✗ {strategy_name}: FAILED - {e}")

        # Check for common issues
        print("\n[5] Content analysis:")
        print(f"    - Starts with '[': {content.startswith('[')}")
        print(f"    - Contains '[': {'[' in content}")
        print(f"    - Contains ']': {']' in content}")
        print(f"    - Contains '```': {'```' in content}")
        print(f"    - Contains 'intent': {'intent' in content.lower()}")
        print(f"    - Contains 'confidence': {'confidence' in content.lower()}")
        last_char = content[-1] if len(content) > 0 else ""
        print(f"    - Has trailing text: {last_char not in ']}'}")

        # Check for truncated output
        if content and not content.endswith("]"):
            print(f"    ⚠ WARNING: Output appears truncated (doesn't end with ']')")

        # Check for incomplete JSON
        if content.count("[") > content.count("]"):
            print(f"    ⚠ WARNING: Unbalanced brackets (more '[' than ']')")

        if content.count("{") > content.count("}"):
            print(f"    ⚠ WARNING: Unbalanced braces (more '{{' than '}}')")

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("INVESTIGATION COMPLETE")
print("=" * 80)
