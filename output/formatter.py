
"""
Format responses for TTS output.
Strips markdown, shortens long responses, adds natural pauses.
"""
import re

def format_for_tts(text: str, max_chars: int = 500) -> str:
    """Prepare text for natural-sounding TTS output."""
    if not text:
        return ""
    # Strip markdown/code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)      # italic
    # Truncate if too long
    if len(text) > max_chars:
        text = text[:max_chars-20] + " [truncated]"
    # Add natural pauses for readability
    text = text.replace(". ", ".  ").replace(", ", ",  ")
    return text.strip()

