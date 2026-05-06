# Model Adapter Layer Implementation

## Summary

Successfully implemented the Model Adapter Layer to connect actual GPT-OSS 120B and Gemma 3 27B model instances, replacing placeholder calls in the orchestration tools.

## Files Created/Modified

### New Files

1. **`jarvis/models/model_adapter.py`** - Core adapter layer implementation
   - `ModelResponse` - Standardized response dataclass
   - `BaseModelAdapter` - Abstract base class for all adapters
   - `GPTOSSAdapter` - Adapter for GPT-OSS 120B (reasoning/planning)
   - `Gemma3Adapter` - Adapter for Gemma 3 27B (classification/vision)
   - `ModelAdapterFactory` - Singleton factory for managing adapters
   - Helper functions: `get_model_adapter()`, `get_reasoning_model()`, `get_vision_model()`

### Modified Files

1. **`jarvis/models/__init__.py`** - Updated exports
   - Added all new adapter classes and functions to `__all__`

2. **`jarvis/capabilities/orchestration/intent_router.py`**
   - Replaced `_classify_with_model()` placeholder with actual Gemma 3 27B integration
   - Added `_parse_model_response_dict()` for dictionary responses
   - Intent classification now uses Gemma 3 27B via the adapter layer

3. **`jarvis/capabilities/orchestration/task_planner.py`**
   - Replaced `_plan_with_model()` placeholder with actual GPT-OSS 120B integration
   - Added `_parse_model_plan_dict()` for dictionary responses
   - Task planning now uses GPT-OSS 120B via the adapter layer

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   CapabilityRegistry                         │
│  ┌─────────────────┐        ┌─────────────────┐             │
│  │  IntentRouter   │        │   TaskPlanner   │             │
│  │                 │        │                 │             │
│  │ Uses Gemma 3    │        │ Uses GPT-OSS    │             │
│  │ 27B Adapter     │        │ 120B Adapter    │             │
│  └────────┬────────┘        └────────┬────────┘             │
│           │                          │                       │
└───────────┼──────────────────────────┼───────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  ModelAdapterFactory                        │
│  ┌──────────────────────┐   ┌──────────────────────┐       │
│  │   Gemma3Adapter      │   │   GPTOSSAdapter      │       │
│  │   (gemma3:27b)       │   │   (gpt-oss:120b)     │       │
│  │                      │   │                      │       │
│  │ - classify()         │   │ - generate()         │       │
│  │ - generate_json()    │   │ - generate_json()    │       │
│  └──────────┬───────────┘   └──────────┬───────────┘       │
└─────────────┼───────────────────────────┼───────────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    OllamaClient                             │
│         (Unified API with cloud/local fallback)             │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Unified Interface
Both adapters implement the same `BaseModelAdapter` interface:
- `generate(prompt, **kwargs)` - Generate text response
- `generate_json(prompt, **kwargs)` - Generate structured JSON response

### 2. Model-Specific Optimizations

**GPT-OSS 120B (Reasoning)**
- Higher temperature (0.7) for creative reasoning
- Larger max_tokens (4000) for complex plans
- Longer timeout (300s) for deep thinking
- Used for: Task planning, complex reasoning, code generation

**Gemma 3 27B (Classification)**
- Lower temperature (0.5) for consistent classification
- Smaller max_tokens (2000) for quick responses
- Shorter timeout (180s) for fast inference
- Used for: Intent classification, vision tasks, quick queries

### 3. Automatic Fallback
All model calls include try/except blocks that gracefully fall back to:
- Rule-based classification (intent router)
- Heuristic planning (task planner)

### 4. Configuration Integration
Adapters automatically load settings from `settings.py`:
- `LLM_MODEL` → GPT-OSS model name
- `OLLAMA_VISION_MODEL` → Gemma 3 model name
- `OLLAMA_CLOUD_URL`, `OLLAMA_LOCAL_URL`, `OLLAMA_API_KEY`

## Usage Examples

### Direct Adapter Access
```python
from jarvis.models import get_reasoning_model, get_vision_model

# Get reasoning model (GPT-OSS 120B)
reasoning = get_reasoning_model()
response = reasoning.generate("Explain quantum computing")
print(response.content)

# Get vision model (Gemma 3 27B)
vision = get_vision_model()
result = vision.classify("open chrome", ["launch_app", "close_app", "search"])
print(f"Intent: {result[0]}, Confidence: {result[1]}")
```

### Via Orchestration Components
```python
from jarvis.capabilities.orchestration import get_intent_router, get_task_planner

# Intent router automatically uses Gemma 3
router = get_intent_router()
result = router.classify("search for python tutorials")
print(f"Intent: {result.intent}")

# Task planner automatically uses GPT-OSS 120B
planner = get_task_planner(available_capabilities=['web_search'])
plan = planner.plan("find weather and save to file")
for step in plan.steps:
    print(f"{step.step_id}: {step.description} ({step.capability})")
```

### Via Capability Registry
```python
from jarvis.capabilities.registry import CapabilityRegistry

registry = CapabilityRegistry()
registry.initialize()  # Automatically configures models

# Execute through registry
result = registry.execute('intent_router', user_input='what is the time')
result = registry.execute('task_planner', goal='organize my files')
```

## Testing Results

```
✓ Model adapters instantiate correctly
✓ GPT-OSS 120B adapter configured with correct model name
✓ Gemma 3 27B adapter configured with correct model name
✓ Intent router integrates with Gemma 3 adapter
✓ Task planner integrates with GPT-OSS adapter
✓ Capability registry initializes with model adapters
✓ All imports resolve without errors
```

## Next Steps

1. **Main Entry Point Update**: The `jarvis.py` entry point already works with the updated orchestrator which will use the capability registry with real models.

2. **Archive Old Tools**: Any legacy mock/placeholder tool implementations can be archived now that real model calls are active.

3. **Performance Monitoring**: Add logging/metrics to track:
   - Model response times
   - Fallback frequency
   - Token usage

4. **Model Configuration**: Fine-tune temperature/max_tokens based on production usage patterns.

## Dependencies

The adapter layer uses existing infrastructure:
- `jarvis.models.ollama_client.OllamaClient` - HTTP client with retry logic
- `jarvis.models.router.ModelRouter` - Task routing configuration
- `settings.py` - Configuration values (model names, URLs, API keys)

No new external dependencies required.
