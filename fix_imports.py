import os
import re

# Files and their import replacements
replacements = {
    # config imports
    (r'^from config\.config import', 'from jarvis.config.config import'),
    (r'^from config\.prompts\.', 'from jarvis.config.prompts.'),
    
    # memory imports  
    (r'^from memory\.working import', 'from jarvis.memory.working import'),
    (r'^from memory\.episodic import', 'from jarvis.memory.episodic import'),
    (r'^from memory\.semantic import', 'from jarvis.memory.semantic import'),
    (r'^from memory\.manager import', 'from jarvis.memory.manager import'),
    (r'^from memory import', 'from jarvis.memory import'),
    
    # perception imports
    (r'^from perception\.intent_classifier import', 'from jarvis.perception.intent_classifier import'),
    (r'^from perception\.vision import', 'from jarvis.perception.vision import'),
    (r'^from perception\.speech_to_text import', 'from jarvis.perception.speech_to_text import'),
    (r'^from perception\.wake_word import', 'from jarvis.perception.wake_word import'),
    
    # safety imports
    (r'^from safety\.audit_log import', 'from jarvis.safety.audit_log import'),
    (r'^from safety\.input_filter import', 'from jarvis.safety.input_filter import'),
    (r'^from safety\.plan_validator import', 'from jarvis.safety.plan_validator import'),
    (r'^from safety\.tool_guard import', 'from jarvis.safety.tool_guard import'),
    
    # skills imports
    (r'^from skills\.base import', 'from jarvis.skills.base import'),
    (r'^from skills\.registry import', 'from jarvis.skills.registry import'),
    
    # execution imports
    (r'^from execution\.rollback import', 'from jarvis.execution.rollback import'),
    (r'^from execution\.tool_runner import', 'from jarvis.execution.tool_runner import'),
    (r'^from execution\.skill_runner import', 'from jarvis.execution.skill_runner import'),
    (r'^from execution\.control_plane import', 'from jarvis.execution.control_plane import'),
    
    # reasoning imports - already fixed
    
    # tools imports
    (r'^from tools\.registry import', 'from jarvis.tools.registry import'),
    (r'^from tools\.executor import', 'from jarvis.tools.executor import'),
    
    # models imports - already fixed
}

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

# Find all Python files in jarvis directory
for root, dirs, files in os.walk('jarvis'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            if fix_file(filepath):
                print(f"Fixed: {filepath}")

print("Done!")
