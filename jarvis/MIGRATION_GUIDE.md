# JARVIS Migration Guide

## Overview

This guide explains how to migrate from the old monolithic architecture to the new modular architecture while keeping the system running throughout the transition.

## Architecture Comparison

### Old Architecture (Monolithic)
```
jarvis.py              # Main loop doing too much
brain.py               # LLM calls
pc_control.py          # 3,144 lines - all tools in one file
control_plane.py       # Tool validation
intent_classifier.py   # Intent classification (misused for tool filtering)
tools.py               # Tool schemas
function_definitions.py # Tool docs
scoring_gate.py        # Safety scoring
ambient.py             # Background monitoring
tts.py                 # TTS output
stt.py                 # Speech recognition
wake_word.py           # Wake word detection
user_profile.py        # User preferences
jarvis_prompt.py       # System prompt
todo_manager.py        # Todo tracking
logger.py              # Logging
config.py              # Configuration
health_check.py        # Health monitoring
```

### New Architecture (Modular)
```
jarvis/
├── core/              # Core orchestration, brain, memory, context
├── perception/        # STT, wake word, vision, intent classification
├── reasoning/         # Planning, criticism, reflection, strategy
├── execution/         # Control plane, skill runner, tool runner, rollback
├── tools/             # Modular tool implementations by category
├── skills/            # High-level skill definitions
├── memory/            # Working, episodic, semantic, procedural memory
├── safety/            # Input filter, plan validator, tool guard, audit
├── output/            # TTS, notifications, formatting
├── monitoring/        # Ambient monitoring, reliability, health
├── models/            # Ollama client, routing, token management
├── profile/           # User profile, learning, routines
└── config/            # Configuration, prompts, schemas
```

## Migration Phases

### Phase 1: Foundation (COMPLETED ✓)

The following components have been implemented and are ready for use:

#### Models Layer
- `models/ollama_client.py` - LLM client with cloud/local fallback
- `models/router.py` - Task routing to appropriate model configs

#### Tools Layer (All Implemented)
- `tools/base.py` - BaseTool abstract class
- `tools/registry.py` - Central tool registry
- `tools/executor.py` - Tool execution dispatcher
- All tool categories implemented:
  - `tools/system/` - power.py, info.py, process.py, display.py
  - `tools/apps/` - launcher.py, window.py
  - `tools/audio/` - volume.py
  - `tools/files/` - operations.py, search.py
  - `tools/network/` - connectivity.py
  - `tools/screen/` - capture.py
  - `tools/input/` - keyboard.py, clipboard.py
  - `tools/web/` - browser.py
  - `tools/time/` - clock.py
  - `tools/settings/` - windows.py
  - `tools/tasks/` - background.py
  - `tools/scripts/` - runner.py
  - `tools/data/` - notes.py, todo.py, calculate.py

#### Safety Layer
- `safety/tool_guard.py` - Replaces control_plane.py
- `safety/audit_log.py` - Immutable action logging

#### Memory Layer
- `memory/working.py` - Conversation window
- `memory/episodic.py` - Session history
- `memory/semantic.py` - Fact storage with TF-IDF search
- `memory/manager.py` - Memory coordinator

#### Perception Layer
- `perception/intent_classifier.py` - Chat vs agent routing ONLY
- `perception/vision.py` - Screen analysis with multimodal LLM

#### Reasoning Layer
- `reasoning/planner.py` - Task decomposition
- `reasoning/critic.py` - Plan review
- `reasoning/reflector.py` - Outcome analysis
- `reasoning/strategy_selector.py` - Reasoning depth selection

#### Skills Layer
- `skills/base.py` - BaseSkill abstract class
- `skills/registry.py` - Skill loader
- `skills/builtin/` - morning_briefing.py, focus_mode.py, system_optimizer.py

#### Core Layer (COMPLETED)
- `core/memory.py` - Memory integration
- `core/context.py` - Context assembly
- `core/brain.py` - LLM inference coordinator
- `core/orchestrator.py` - Main loop (replaces jarvis.py)

#### Configuration Layer
- `config/config.py` - Configuration management
- `config/prompts/` - All prompt templates
  - jarvis_prompt.py, planning_prompt.py, critic_prompt.py
  - reflection_prompt.py, scripting_prompt.py, vision_prompt.py
- `config/schemas/tool_schemas.py` - Centralized tool schemas

#### Entry Point
- `jarvis/jarvis.py` - Thin entry point starting orchestrator

### Phase 2: Integration Steps

#### Step 1: Backup Current System
```bash
# Create backup of working prototype
cp -r jarvis_old/ jarvis_backup_$(date +%Y%m%d_%H%M%S)/
```

#### Step 2: Install New Dependencies
```bash
# The new architecture uses these existing dependencies:
pip install psutil mss Pillow pyyaml

# No new external dependencies beyond what's already in requirements.txt
```

#### Step 3: Test Individual Components

Test the tool registry:
```python
from jarvis.tools.registry import ToolRegistry
from jarvis.config.config import get_config

config = get_config()
registry = ToolRegistry(config)
registry.load_all_tools()

print(f"Loaded {len(registry.tools)} tools:")
for name in registry.tools.keys():
    print(f"  - {name}")
```

Test the brain:
```python
from jarvis.core.brain import Brain
from jarvis.tools.registry import ToolRegistry

config = get_config()
registry = ToolRegistry(config)
registry.load_all_tools()

brain = Brain(config, registry)
response = brain.chat(
    messages=[{'role': 'user', 'content': 'Hello!'}],
    system_prompt="You are JARVIS, a helpful AI assistant."
)
print(response['content'])
```

Test the orchestrator:
```python
from jarvis.core.orchestrator import Orchestrator
from jarvis.config.config import get_config

config = get_config()
orchestrator = Orchestrator(config)

# Process a test command
result = orchestrator.process_command("What time is it?")
print(result)
```

#### Step 4: Parallel Run Strategy

Run old and new systems side-by-side during transition:

1. **Week 1**: Run new system in "shadow mode"
   - New system receives same inputs but doesn't execute
   - Compare outputs between old and new
   - Log discrepancies for review

2. **Week 2**: Enable limited execution
   - Allow new system to execute safe tools only (get_time, get_date, calculate)
   - Continue comparing outputs
   - Gradually enable more tool categories

3. **Week 3**: Full execution with fallback
   - New system handles all requests
   - Old system on standby for immediate fallback
   - Monitor error rates and user satisfaction

4. **Week 4**: Complete cutover
   - Disable old system
   - Keep old code available for reference
   - Begin removing deprecated code

### Phase 3: Code Mapping

Use this table to find where functionality moved:

| Old File | New Location(s) | Notes |
|----------|-----------------|-------|
| jarvis.py | core/orchestrator.py, jarvis.py | Split into orchestrator + thin entry point |
| brain.py | core/brain.py, models/ollama_client.py | Separated coordination from client |
| pc_control.py | tools/* (20+ files) | Split by category |
| control_plane.py | safety/tool_guard.py | Enhanced with better validation |
| intent_classifier.py | perception/intent_classifier.py | Now ONLY routes chat vs agent |
| tools.py | config/schemas/tool_schemas.py | Schemas centralized |
| function_definitions.py | config/schemas/tool_schemas.py | Merged with schemas |
| scoring_gate.py | safety/tool_guard.py | Integrated into guard |
| ambient.py | monitoring/ambient.py | Same functionality |
| tts.py | output/tts.py | Same functionality |
| stt.py | perception/stt.py | To be implemented |
| wake_word.py | perception/wake_word.py | To be implemented |
| user_profile.py | profile/user_profile.py | Enhanced with learning |
| jarvis_prompt.py | config/prompts/jarvis_prompt.py | More flexible |
| todo_manager.py | tools/data/todo.py | Integrated as tool |
| logger.py | Removed | Using Python stdlib logging |
| config.py | config/config.py | Enhanced with env overrides |
| health_check.py | monitoring/health_check.py | To be implemented |

### Phase 4: Key Improvements

#### 1. Tool Hallucination Prevention
Old: No validation, LLM could invent tool names
New: Registry check before execution, clear error feedback

```python
# In core/brain.py
def validate_tool_name(self, tool_name: str) -> bool:
    return tool_name in self.tool_registry.tools

def _execute_tool_call(self, tool_call: Dict) -> Dict:
    tool_name = tool_call.get('name', '')
    if not self.validate_tool_name(tool_name):
        error_msg = f"Tool '{tool_name}' not found. Available: {self.get_available_tool_names()}"
        return {'success': False, 'error': error_msg}
```

#### 2. Vision Layer (NEW)
Old: Screenshots taken but never analyzed
New: Multimodal LLM analyzes screenshots

```python
from jarvis.perception.vision import VisionAnalyzer

vision = VisionAnalyzer(config, brain)
analysis = vision.analyze_screen(prompt="What application is open?")
print(analysis['summary'])
```

#### 3. Memory System (ENHANCED)
Old: Flat JSON conversation window
New: Four memory types with semantic search

```python
from jarvis.core.memory import CoreMemory

memory = CoreMemory(config)

# Store fact
memory.remember_fact("User prefers dark mode", category="preferences")

# Recall relevant memories
memories = memory.recall_memories("display settings", limit=5)

# Get full context
context = memory.retrieve_context(query="current task")
```

#### 4. Intent Classifier (FIXED)
Old: Used to filter tool choices (caused conflicts)
New: Only routes between chat and agent mode

```python
from jarvis.perception.intent_classifier import IntentClassifier

classifier = IntentClassifier(config, brain)
intent = classifier.classify("What's the weather like?")
# Returns: {'mode': 'chat', 'confidence': 0.95}

intent = classifier.classify("Turn off the lights")
# Returns: {'mode': 'agent', 'confidence': 0.92}
```

#### 5. Safety Layers (ENHANCED)
Old: Single scoring gate
New: Multiple independent layers

1. `input_filter` - Validates user input
2. `plan_validator` - Reviews plans before execution
3. `tool_guard` - Validates each tool call
4. `execution_monitor` - Watches execution in real-time
5. `audit_log` - Immutable record of all actions

### Phase 5: Running the New System

#### Basic Usage
```bash
# Start in agent mode (default)
python jarvis/jarvis.py

# Start in chat mode
python jarvis/jarvis.py --mode chat

# Enable voice interaction
python jarvis/jarvis.py --voice

# Debug mode with verbose logging
python jarvis/jarvis.py --debug
```

#### Configuration
Create `config/config.yaml`:
```yaml
model: nemotron-3-nano:30b-cloud
tts_enabled: true
tts_voice: bm_george
tts_speed: 1.15
user_name: YourName

# Safety settings
require_confirmation_for:
  - shutdown_computer
  - restart_computer
  - delete_file

# Memory settings
working_memory_max_messages: 20
memory_retrieval_limit: 5
```

Or use environment variables:
```bash
export JARVIS_MODEL=nemotron-3-nano:30b-cloud
export JARVIS_TTS_ENABLED=true
export JARVIS_USER_NAME=YourName
python jarvis/jarvis.py
```

### Phase 6: Troubleshooting

#### Common Issues

**Issue**: Tools not loading
```
Solution: Check that all tool modules exist and have no import errors
python -c "from jarvis.tools.registry import ToolRegistry; r = ToolRegistry({}); r.load_all_tools()"
```

**Issue**: LLM connection failures
```
Solution: Verify ollama_cloud_url is accessible, fallback_to_local will use localhost:11434
Check: curl https://ollama.com/api/chat
```

**Issue**: Memory not persisting
```
Solution: Ensure data_dir exists and is writable
mkdir -p jarvis_data && chmod 755 jarvis_data
```

**Issue**: TTS not working
```
Solution: Verify Kokoro is installed and voice file exists
Check config: tts_engine, tts_voice, tts_speed
```

### Phase 7: Rollback Plan

If issues arise, revert to old system:

```bash
# Stop new system
# Restore old system
mv jarvis jarvis_new
mv jarvis_old jarvis

# Restart with old system
python jarvis/jarvis.py
```

## Testing Checklist

Before completing migration, verify:

- [ ] All tools execute correctly
- [ ] Tool hallucinations are caught and reported
- [ ] Vision analysis works with screenshots
- [ ] Memory retrieval returns relevant results
- [ ] Intent classifier correctly routes chat vs agent
- [ ] Safety guards block dangerous operations
- [ ] Audit log records all actions
- [ ] TTS output is clear and natural
- [ ] System recovers gracefully from errors
- [ ] Performance is acceptable (< 2s response for simple commands)

## Post-Migration Tasks

After successful migration:

1. Remove duplicate handler functions from old pc_control.py
2. Delete deprecated files (scoring_gate.py, function_definitions.py)
3. Update documentation to reflect new architecture
4. Add integration tests for cross-module interactions
5. Profile performance and optimize bottlenecks
6. Implement remaining TODO items in new code

## Support

For issues or questions during migration:
- Check logs in `logs/jarvis.log`
- Review audit trail in `jarvis_data/audit/`
- Examine memory files in `jarvis_data/memory/`
- Consult architecture diagrams in `docs/`

---

**Migration Status**: Foundation Complete
**Next Step**: Begin Phase 2 integration testing
**Estimated Timeline**: 2-4 weeks for full migration
