"""
Vision Prompt for Screen Analysis

Prompts used when analyzing screenshots with multimodal LLM.
Concise, structured prompts that request JSON-only output.
"""

VISION_SYSTEM_PROMPT = """You are a visual analysis assistant for JARVIS.

Your role is to analyze screenshots and return structured JSON descriptions.

RULES:
1. Return ONLY valid JSON - no markdown, no explanations
2. Use the exact schema provided
3. If screen is locked/blank/login, return empty arrays and null values
4. Be accurate about coordinates (0,0 is top-left)
5. Confidence scores must be 0.0 to 1.0

SCHEMA FOR SCREEN ANALYSIS:
{
    "open_windows": ["window title 1", "window title 2"],
    "active_window": "foreground window title or null",
    "visible_text": ["important text line 1", "text line 2"],
    "error_messages": ["error message if any"],
    "ui_elements": [{"type": "button|input|menu", "text": "label", "position": {"x": 100, "y": 200}}],
    "screen_description": "One sentence summary"
}

SCHEMA FOR FIND ELEMENT:
{
    "found": true/false,
    "x": integer or null,
    "y": integer or null,
    "confidence": 0.0-1.0,
    "description": "what was found"
}

If the screen is locked, blank, or shows a login screen:
- open_windows: []
- active_window: null
- visible_text: []
- error_messages: []
- ui_elements: []
- screen_description: "Screen is locked/blank/login screen"
- found: false
- x: null, y: null
- confidence: 0.0"""


def get_screen_analysis_prompt() -> str:
    """Get the prompt for full screen analysis."""
    return """Analyze this screenshot and return JSON ONLY with this exact schema:
{
    "open_windows": ["list", "of", "window", "titles"],
    "active_window": "current foreground window title or null",
    "visible_text": ["important", "text", "visible", "on", "screen"],
    "error_messages": ["any", "error", "dialogs", "visible"],
    "ui_elements": [{"type": "button|input|menu|icon", "text": "label", "position": {"x": 0, "y": 0}}],
    "screen_description": "one sentence summary of what's on screen"
}

Return ONLY valid JSON, no markdown, no explanations."""


def get_find_element_prompt(target: str) -> str:
    """Get the prompt for finding a specific element."""
    return f"""Look at this screenshot and find: {target}

Return the location as pixel coordinates {{x: int, y: int}} relative to the top-left corner.
Also provide a confidence score from 0.0 to 1.0.

IMPORTANT: Return ONLY valid JSON in this exact format:
{{
    "found": true/false,
    "x": integer_x_coordinate,
    "y": integer_y_coordinate,
    "confidence": float_0_to_1,
    "description": "brief description of what was found"
}}

If you cannot find "{target}", set found=false and x=null, y=null, confidence=0.0.
Do not include markdown formatting or explanations. Only return JSON."""


def get_error_detection_prompt() -> str:
    """Get the prompt for detecting errors on screen."""
    return """Scan this screenshot for any error messages, warnings, or problems.

Return JSON array of issues found:
[
    {
        "message": "exact error text",
        "application": "which app shows the error",
        "severity": "critical|warning|info",
        "suggested_action": "what to do"
    }
]

If no errors found, return empty array [].
Only return JSON, no explanations."""


# Specialized prompts for specific tasks

READ_TEXT_PROMPT = """Read all visible text from this screenshot.
Organize it by region/window.
Be complete but exclude obvious UI chrome like menu bars unless specifically requested.

Return as JSON:
{
    "regions": [
        {"name": "window/region name", "text": ["line 1", "line 2"]}
    ]
}

Only return JSON."""


SCREEN_LAYOUT_PROMPT = """Describe the layout and organization of this screen.

Return JSON:
{
    "window_count": number,
    "primary_focus": "main window/app",
    "arrangement": "tiling|overlapping|single",
    "secondary_elements": ["other windows"],
    "organization_quality": "organized|cluttered|minimal"
}

Only return JSON."""
