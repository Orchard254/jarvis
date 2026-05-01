# user_profile.py â€” User preferences, shortcuts, and profile management

import json
import os
from datetime import datetime
from pathlib import Path

from logger import get_logger

log = get_logger("user_profile")

PROFILE_FILE = Path(__file__).parent / "user_profile.json"
CONVERSATION_HISTORY_FILE = Path(__file__).parent / "conversation_history.json"


DEFAULT_PROFILE = {
    "user": {
        "name": "User",
        "created_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
    },
    "preferences": {
        "response_length": "brief",  # brief, normal, detailed
        "tts_speed": 1.0,
        "confirm_dangerous": True,
        "favorite_apps": ["Chrome", "VS Code", "Notepad"],
        "timezone": "UTC",
    },
    "shortcuts": {
        "work_mode": ["open_app:VS Code", "open_app:Chrome", "set_timer:25"],
        "break_time": ["open_app:Spotify", "set_volume:60"],
        "focus_mode": ["mute", "set_volume:0", "open_app:VS Code"],
        "relax": ["close_app:Spotify", "volume_down:20", "open_app:Spotify"],
    },
    "routines": {
        "morning": {
            "time": "09:00",
            "enabled": False,
            "actions": ["get_time", "get_date", "battery_status"],
        }
    },
    "learning": {
        "frequently_used_commands": {},
        "preferred_responses": {},
        "interaction_count": 0,
        "conversation_topics": [],
        "last_topics": [],
        "success_patterns": {},
        "failed_patterns": {},
        "user_corrections": [],
        "preferred_response_style": "balanced",
        "active_hours": [],
        "task_completion_times": {},
    },
}


def load_profile() -> dict:
    """Load user profile from JSON file."""
    try:
        if PROFILE_FILE.exists():
            with open(PROFILE_FILE, "r") as f:
                profile = json.load(f)
                log.debug(f"Loaded profile for user: {profile['user'].get('name', 'Unknown')}")

                # Ensure all required learning fields exist (for backwards compatibility)
                if "learning" not in profile:
                    profile["learning"] = {}

                required_learning_fields = {
                    "frequently_used_commands": {},
                    "preferred_responses": {},
                    "interaction_count": 0,
                    "conversation_topics": [],
                    "last_topics": [],
                    "success_patterns": {},
                    "failed_patterns": {},
                    "user_corrections": [],
                    "preferred_response_style": "balanced",
                    "active_hours": [],
                    "task_completion_times": {},
                }

                for field, default_value in required_learning_fields.items():
                    if field not in profile["learning"]:
                        profile["learning"][field] = default_value

                return profile
    except Exception as e:
        log.error(f"Error loading profile: {e}")

    # Create default profile if it doesn't exist
    log.info("Creating new default profile")
    save_profile(DEFAULT_PROFILE)
    return DEFAULT_PROFILE


def save_profile(profile: dict) -> bool:
    """Save user profile to JSON file."""
    try:
        profile["user"]["last_updated"] = datetime.now().isoformat()
        with open(PROFILE_FILE, "w") as f:
            json.dump(profile, f, indent=2)
        log.debug("Profile saved successfully")
        return True
    except Exception as e:
        log.error(f"Error saving profile: {e}")
        return False


def get_user_name() -> str:
    """Get user's name from profile."""
    profile = load_profile()
    return profile["user"].get("name", "User")


def set_user_name(name: str) -> bool:
    """Set user's name in profile."""
    profile = load_profile()
    profile["user"]["name"] = name
    return save_profile(profile)


def get_preference(key: str, default=None):
    """Get a user preference."""
    profile = load_profile()
    return profile["preferences"].get(key, default)


def set_preference(key: str, value) -> bool:
    """Set a user preference."""
    profile = load_profile()
    profile["preferences"][key] = value
    return save_profile(profile)


def add_shortcut(name: str, actions: list) -> bool:
    """Add or update a shortcut/macro.

    Example:
        add_shortcut("work_mode", ["open_app:VS Code", "set_timer:25"])
    """
    profile = load_profile()
    profile["shortcuts"][name] = actions
    log.info(f"Added shortcut: {name}")
    return save_profile(profile)


def get_shortcut(name: str):
    """Get a shortcut by name."""
    profile = load_profile()
    return profile["shortcuts"].get(name)


def list_shortcuts() -> list:
    """List all available shortcuts."""
    profile = load_profile()
    return list(profile["shortcuts"].keys())


def add_routine(name: str, time: str, actions: list, enabled: bool = True) -> bool:
    """Add a daily routine.

    Example:
        add_routine("morning", "09:00", ["get_time", "battery_status"], enabled=True)
    """
    profile = load_profile()
    profile["routines"][name] = {"time": time, "enabled": enabled, "actions": actions}
    log.info(f"Added routine: {name} at {time}")
    return save_profile(profile)


def get_routine(name: str):
    """Get a routine by name."""
    profile = load_profile()
    return profile["routines"].get(name)


def list_routines() -> list:
    """List all available routines."""
    profile = load_profile()
    return list(profile["routines"].keys())


def record_interaction(command: str, success: bool = True, task_context: str = "") -> bool:
    """Record an interaction for learning.

    This helps Nemotron learn which commands are most frequently used,
    and which approaches succeed or fail in different contexts.
    """
    profile = load_profile()

    # Track command frequency
    if command not in profile["learning"]["frequently_used_commands"]:
        profile["learning"]["frequently_used_commands"][command] = 0

    profile["learning"]["frequently_used_commands"][command] += 1
    profile["learning"]["interaction_count"] += 1

    # Track success/failure patterns for learning
    if task_context:
        if success:
            # Track successful patterns
            if task_context not in profile["learning"]["success_patterns"]:
                profile["learning"]["success_patterns"][task_context] = {}
            if command not in profile["learning"]["success_patterns"][task_context]:
                profile["learning"]["success_patterns"][task_context][command] = 0
            profile["learning"]["success_patterns"][task_context][command] += 1
        else:
            # Track failed patterns
            if task_context not in profile["learning"]["failed_patterns"]:
                profile["learning"]["failed_patterns"][task_context] = {}
            if command not in profile["learning"]["failed_patterns"][task_context]:
                profile["learning"]["failed_patterns"][task_context][command] = 0
            profile["learning"]["failed_patterns"][task_context][command] += 1

    return save_profile(profile)


def record_user_correction(original_attempt: str, correction: str, task_context: str = "") -> bool:
    """Record when a user corrects the assistant's action for learning."""
    profile = load_profile()

    correction_entry = {
        "original": original_attempt,
        "correction": correction,
        "context": task_context,
        "timestamp": datetime.now().isoformat(),
    }

    profile["learning"]["user_corrections"].append(correction_entry)
    # Keep only last 50 corrections to prevent unbounded growth
    if len(profile["learning"]["user_corrections"]) > 50:
        profile["learning"]["user_corrections"] = profile["learning"]["user_corrections"][-50:]

    return save_profile(profile)


def get_success_patterns(task_context: str = None) -> dict:
    """Get patterns of what works successfully for a given task context."""
    profile = load_profile()
    if task_context:
        return profile["learning"]["success_patterns"].get(task_context, {})
    return profile["learning"]["success_patterns"]


def get_failed_patterns(task_context: str = None) -> dict:
    """Get patterns of what has failed for a given task context."""
    profile = load_profile()
    if task_context:
        return profile["learning"]["failed_patterns"].get(task_context, {})
    return profile["learning"]["failed_patterns"]


def get_recommended_approach(task_context: str) -> str:
    """Get the most successful approach for a given task context based on learning."""
    success_patterns = get_success_patterns(task_context)
    failed_patterns = get_failed_patterns(task_context)

    if not success_patterns:
        return None

    # Find the command with highest success rate
    best_command = None
    best_score = -1

    for command, success_count in success_patterns.items():
        failure_count = failed_patterns.get(command, 0)
        total_attempts = success_count + failure_count
        if total_attempts > 0:
            success_rate = success_count / total_attempts
            # Weight by total attempts to favor more tried approaches
            score = success_rate * min(total_attempts / 10, 1)  # Cap weight at 10 attempts
            if score > best_score:
                best_score = score
                best_command = command

    return best_command


def update_response_style(preference: str) -> bool:
    """Update the user's preferred response style."""
    profile = load_profile()
    if preference in ["brief", "balanced", "detailed"]:
        profile["learning"]["preferred_response_style"] = preference
        return save_profile(profile)
    return False


def get_preferred_response_style() -> str:
    """Get the user's preferred response style."""
    profile = load_profile()
    return profile["learning"].get("preferred_response_style", "balanced")


def record_active_hour(hour: int) -> bool:
    """Record when the user is active for learning active hours."""
    profile = load_profile()
    # Ensure active_hours key exists in learning section
    if "active_hours" not in profile["learning"]:
        profile["learning"]["active_hours"] = []

    if 0 <= hour <= 23:
        if hour not in profile["learning"]["active_hours"]:
            profile["learning"]["active_hours"].append(hour)
        # Keep sorted and unique
        profile["learning"]["active_hours"] = sorted(list(set(profile["learning"]["active_hours"])))
        return save_profile(profile)
    return False


def get_active_hours() -> list:
    """Get hours when the user is typically active."""
    profile = load_profile()
    return profile["learning"].get("active_hours", [])


def get_profile_summary() -> str:
    """Get a human-readable summary of user profile."""
    profile = load_profile()

    prefs = ", ".join([f"{k}={v}" for k, v in profile["preferences"].items()]) or "None"
    shortcuts = ", ".join(profile["shortcuts"].keys()) or "None"
    routines = ", ".join(profile["routines"].keys()) or "None"

    most_used = (
        max(profile["learning"]["frequently_used_commands"].items(), key=lambda x: x[1])
        if profile["learning"]["frequently_used_commands"]
        else "None"
    )

    summary = f"""
User Profile Summary:
- Name: {profile['user'].get('name', 'Not set')}
- Preferences: {prefs}
- Shortcuts: {shortcuts}
- Routines: {routines}
- Total Interactions: {profile['learning']['interaction_count']}
- Most Used: {most_used}
""".strip()

    return summary


def save_conversation(role: str, content: str, timestamp: str = None) -> bool:
    """Save a conversation message for history."""
    if timestamp is None:
        timestamp = datetime.now().isoformat()

    try:
        history = []
        if CONVERSATION_HISTORY_FILE.exists():
            with open(CONVERSATION_HISTORY_FILE, "r") as f:
                history = json.load(f)

        history.append({"role": role, "content": content, "timestamp": timestamp})

        # When history grows too large, condense oldest messages into a summary entry
        if len(history) > 500:
            keep_from = len(history) - 400
            dropped = history[:keep_from]
            user_snippets = [m["content"][:60] for m in dropped if m["role"] == "user"]
            summary_text = "Earlier conversation covered: " + "; ".join(user_snippets[:20])
            summary_entry = {
                "role": "system",
                "content": summary_text,
                "timestamp": dropped[-1]["timestamp"],
            }
            history = [summary_entry] + history[keep_from:]

        with open(CONVERSATION_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)

        return True
    except Exception as e:
        log.error(f"Error saving conversation: {e}")
        return False


def get_conversation_history(limit: int = 50) -> list:
    """Get recent conversation history."""
    try:
        if CONVERSATION_HISTORY_FILE.exists():
            with open(CONVERSATION_HISTORY_FILE, "r") as f:
                history = json.load(f)
                return history[-limit:]
    except Exception as e:
        log.error(f"Error reading conversation history: {e}")

    return []


def get_conversation_summary(days: int = 1) -> str:
    """Get a summary of recent conversations."""
    history = get_conversation_history(limit=200)

    # Filter by date
    from datetime import datetime, timedelta

    cutoff_date = datetime.now() - timedelta(days=days)

    relevant = [msg for msg in history if datetime.fromisoformat(msg["timestamp"]) > cutoff_date]
    if not relevant:
        return "No recent conversations."

    user_messages = [message for message in relevant if message["role"] == "user"]
    summary = (
        f"Recent topics: {', '.join([message['content'][:50] for message in user_messages[:5]])}"
    )
    return summary


def add_topic(topic: str) -> bool:
    """Track a conversation topic for context."""
    profile = load_profile()
    topics = profile["learning"].get("conversation_topics", [])
    topic = topic.lower().strip()[:50]  # Normalize
    if topic and topic not in topics:
        topics.append(topic)
        profile["learning"]["conversation_topics"] = topics[-20:]  # Keep last 20
        profile["learning"]["last_topics"] = topics[-5:]  # Recent 5
        return save_profile(profile)
    return False


def get_recent_topics() -> list:
    """Get recent topics for context."""
    profile = load_profile()
    return profile["learning"].get("last_topics", [])


def get_command_suggestions() -> list:
    """Get intelligent command suggestions based on usage patterns."""
    profile = load_profile()
    commands = profile["learning"]["frequently_used_commands"]

    if not commands:
        return []

    # Sort by frequency and return top 5
    sorted_commands = sorted(commands.items(), key=lambda x: x[1], reverse=True)
    return [cmd for cmd, count in sorted_commands[:5]]


def get_context_aware_suggestions(time_of_day: str = None) -> list:
    """Get context-aware suggestions based on time, usage patterns, and learning."""
    if not time_of_day:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 22:
            time_of_day = "evening"
        else:
            time_of_day = "night"

    # Get time-based suggestions
    suggestions = {
        "morning": ["get_date", "battery_status", "weather"],
        "afternoon": ["system_info", "list_files"],
        "evening": ["close_app:Chrome", "set_timer:30"],
        "night": ["shutdown", "set_timer:480"],
    }

    # Combine with frequently used commands
    frequent = get_command_suggestions()
    time_based = suggestions.get(time_of_day, [])

    # Get learned patterns for this time of day
    learned_suggestions = get_learned_time_patterns(time_of_day)

    # Combine all suggestions with priority: learned > frequent > time-based
    seen = set()
    result = []

    # Add learned suggestions first (highest priority)
    for cmd in learned_suggestions:
        if cmd not in seen:
            seen.add(cmd)
            result.append(cmd)

    # Add frequently used commands
    for cmd in frequent:
        if cmd not in seen:
            seen.add(cmd)
            result.append(cmd)

    # Add time-based suggestions
    for cmd in time_based:
        if cmd not in seen:
            seen.add(cmd)
            result.append(cmd)

    return result[:10]


def get_learned_time_patterns(time_of_day: str) -> list:
    """Get learned suggestions based on what the user typically does at certain times."""
    profile = load_profile()

    # Look for patterns in user_corrections or interaction history
    # For now, we'll return empty as this would require more complex analysis
    # In a full implementation, this would analyze when user typically performs actions
    learned_patterns = profile["learning"].get("time_patterns", {})
    return learned_patterns.get(time_of_day, [])


def record_time_pattern(time_of_day: str, action: str) -> bool:
    """Record that the user performed an action at a certain time of day for learning."""
    profile = load_profile()

    if "time_patterns" not in profile["learning"]:
        profile["learning"]["time_patterns"] = {
            "morning": [],
            "afternoon": [],
            "evening": [],
            "night": [],
        }

    if action not in profile["learning"]["time_patterns"][time_of_day]:
        profile["learning"]["time_patterns"][time_of_day].append(action)

    # Keep only top 5 most frequent actions per time period to prevent bloat
    # In a full implementation, we'd track frequency and sort by it
    if len(profile["learning"]["time_patterns"][time_of_day]) > 5:
        profile["learning"]["time_patterns"][time_of_day] = profile["learning"]["time_patterns"][
            time_of_day
        ][:5]

    return save_profile(profile)


def get_proactive_suggestions() -> list:
    """Get proactive suggestions based on learned patterns and current context."""
    profile = load_profile()
    suggestions = []

    # Get current time of day
    hour = datetime.now().hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    # Get context-aware suggestions
    context_suggestions = get_context_aware_suggestions(time_of_day)
    suggestions.extend(context_suggestions[:3])  # Top 3

    # Check for any routines that should be triggered
    routine_suggestions = get_due_routines()
    suggestions.extend(routine_suggestions[:2])  # Top 2 routines

    # Check for any learned patterns that suggest proactive actions
    learned_suggestions = get_learned_proactive_patterns()
    suggestions.extend(learned_suggestions[:2])  # Top 2 learned

    # Deduplicate while preserving order
    seen = set()
    result = []
    for item in suggestions:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result[:5]  # Return top 5 suggestions


def get_due_routines() -> list:
    """Check if any routines should be triggered based on current time."""
    profile = load_profile()
    now = datetime.now()
    current_time = now.strftime("%H:%M")

    due_routines = []

    for routine_name, routine_data in profile.get("routines", {}).items():
        if routine_data.get("enabled", False):
            routine_time = routine_data.get("time", "")
            if routine_time == current_time:
                due_routines.append(f"run_routine:{routine_name}")

    return due_routines


def get_learned_proactive_patterns() -> list:
    """Get learned patterns that suggest proactive actions."""
    profile = load_profile()

    # This would analyze user_corrections, interaction patterns, etc.
    # to suggest actions the user might want but hasn't asked for yet
    # For now, return empty as this requires more sophisticated learning
    return []
