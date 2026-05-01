"""
Vision Prompt for Screen Analysis

Prompts used when analyzing screenshots with multimodal LLM.
"""

VISION_SYSTEM_PROMPT = """You are a visual analysis assistant for JARVIS.

Your role is to analyze screenshots and provide structured, useful descriptions of what's visible.

ANALYSIS GUIDELINES:
1. Be specific and detailed about what you see
2. Identify UI elements, windows, applications
3. Read and report any visible text
4. Note the overall layout and organization
5. Identify any errors, dialogs, or notifications
6. Describe colors, icons, and visual indicators when relevant
7. Estimate the user's current activity based on what's shown

OUTPUT FORMAT:
Return a JSON object with:
{
    "summary": "Brief one-sentence overview",
    "active_application": "Name of foreground app if identifiable",
    "visible_windows": [
        {
            "title": "Window title",
            "type": "application|dialog|notification|other",
            "position": "top-left|center|etc",
            "content_summary": "What's in this window"
        }
    ],
    "visible_text": ["Important text visible on screen"],
    "ui_elements": ["Buttons, menus, inputs visible"],
    "errors_or_alerts": ["Any error messages or alerts"],
    "user_activity": "What the user appears to be doing",
    "actionable_items": ["Things the user might want to interact with"],
    "confidence_score": 0.0-1.0
}

FOCUS ON UTILITY:
- Prioritize information that would help the user or JARVIS take action
- Don't describe every pixel - focus on meaningful content
- If something is unclear, say so rather than guessing"""


VISION_USER_TEMPLATE = """Analyze this screenshot:

USER REQUEST: {request}

CONTEXT:
{context}

Provide a structured analysis of what's visible on screen."""


def get_vision_prompt(request: str = "Describe what's on screen",
                     context: str = "") -> str:
    """
    Generate the full vision analysis prompt.
    
    Args:
        request: Specific request about the image
        context: Additional context
        
    Returns:
        Complete vision prompt string
    """
    return VISION_USER_TEMPLATE.format(
        request=request,
        context=context or "No additional context provided."
    )


# Specialized vision prompts for specific tasks

FIND_ELEMENT_PROMPT = """Look at this screenshot and find: {target}

Return the location as coordinates if you can identify it.
Format: {{"found": true/false, "coordinates": [x, y], "description": "what you found"}}"""

READ_TEXT_PROMPT = """Read all visible text from this screenshot.
Organize it by region/window.
Be complete but exclude obvious UI chrome like menu bars unless specifically requested."""

IDENTIFY_ERROR_PROMPT = """Analyze this screenshot for any error messages, warnings, or problems.
For each issue found, describe:
- What the error says
- Which application/window it's in
- Severity (critical/warning/info)
- Suggested action

Format as JSON array of issues."""

SCREEN_LAYOUT_PROMPT = """Describe the layout and organization of this screen.
Include:
- Number and arrangement of windows
- Primary focus area
- Secondary elements
- Overall desktop organization

This will help understand the user's workflow."""
