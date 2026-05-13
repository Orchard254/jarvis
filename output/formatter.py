
"""
Format responses for TTS output.
Strips markdown, shortens long responses, adds natural pauses.
"""
import re

def format_for_tts(text: str, max_chars: int = 1500) -> str:
    """Prepare text for natural-sounding TTS output."""
    if not text:
        return ""
    # Strip markdown/code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*(.*?)\*", r"\1", text)      # italic
    # Convert numbered/bullet lists to natural sentences
    text = re.sub(r"(?:^|\n)\s*\d+[.)]\s+", ". ", text)
    text = re.sub(r"(?:^|\n)\s*[-*]\s+", ". ", text)
    # Convert ISO dates to natural speech (2026-05-12 → May 12th 2026)
    def _date_to_natural(m):
        parts = m.group(0).split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            months = ["", "January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
            y, mo, d = parts
            try:
                return f"{months[int(mo)]} {int(d)}, {y}"
            except (ValueError, IndexError):
                return m.group(0)
        return m.group(0)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", _date_to_natural, text)
    # Truncate at last sentence boundary before limit
    if len(text) > max_chars:
        truncated = text[:max_chars]
        last_boundary = max(truncated.rfind(". "), truncated.rfind("! "),
                            truncated.rfind("? "), truncated.rfind("\n"))
        if last_boundary > max_chars // 2:
            text = truncated[:last_boundary + 1] + " [truncated]"
        else:
            text = truncated[:max_chars - 20] + " [truncated]"
    # Add natural pauses for readability
    text = text.replace(". ", ".  ").replace(", ", ",  ")
    return text.strip()

