# JARVIS Migration Guide: Legacy to Capability-Based Architecture

## Overview

This guide documents the migration from the legacy tool-based architecture to the new capability-based architecture with integrated GPT-OSS 120B and Gemma 3 27B models.

## Migration Status: ✅ COMPLETE

As of this update, the migration is **100% complete** with the following milestones achieved:

### Phase 1: Core Infrastructure ✅
- [x] Capability Registry implemented with 30+ tools
- [x] Model Adapter Layer created for GPT-OSS 120B and Gemma 3 27B
- [x] Intent Router integrated with Gemma 3 27B for classification
- [x] Task Planner integrated with GPT-OSS 120B for planning

### Phase 2: Integration ✅
- [x] Main entry point (`jarvis.py`) updated to use capability-based architecture
- [x] Legacy code archived to `jarvis_legacy.py`
- [x] All documentation references updated
- [x] Model adapters properly inject into CapabilityRegistry

### Phase 3: Verification ✅
- [x] End-to-end testing completed
- [x] Model inference working through Ollama client
- [x] Fallback mechanisms tested (graceful degradation on model failure)

## Architecture Comparison

### Legacy Architecture (Archived)
```
User Input → Simple Orchestrator → Mock Tool Calls → Results
```

### New Architecture (Production)
```
User Input → Intent Router (Gemma 3 27B) 
           → Task Planner (GPT-OSS 120B) 
           → Capability Registry (30+ Tools) 
           → Results
```

## Key Changes

### 1. Model Integration
- **GPT-OSS 120B**: Used for complex reasoning and task planning
  - Configuration: `gpt-oss:120b` (configurable in `settings.py`)
  - Optimized for: High-temp (0.7), long context (4000 tokens), extended timeout (300s)
  
- **Gemma 3 27B**: Used for intent classification and vision tasks
  - Configuration: `gemma3:27b` (configurable in `settings.py`)
  - Optimized for: Lower temp (0.5), faster response (2000 tokens), shorter timeout (180s)

### 2. Entry Point Changes
**Old Usage:**
```bash
python jarvis_legacy.py --mode chat
```

**New Usage:**
```bash
python jarvis.py --mode chat
python jarvis.py --mode agent
python jarvis.py --test  # Run health checks
```

### 3. File Structure
```
/workspace/
├── jarvis.py                 # Main entry point (NEW architecture)
├── jarvis_legacy.py          # Archived legacy code
├── jarvis/
│   ├── capabilities/
│   │   ├── registry.py       # Central capability registry
│   │   └── orchestration/
│   │       ├── intent_router.py   # Uses Gemma 3 27B
│   │       └── task_planner.py    # Uses GPT-OSS 120B
│   └── models/
│       └── model_adapter.py  # Model adapter layer
└── settings.py               # Model configuration
```

## Model Adapter Layer

The new `ModelAdapter` layer provides:

1. **Unified Interface**: Both models expose `generate()` and `generate_json()` methods
2. **Automatic Fallback**: Graceful degradation to rule-based methods on model failure
3. **Configuration Management**: All model settings centralized in `settings.py`
4. **Factory Pattern**: `ModelAdapterFactory` manages singleton instances

### Example Usage
```python
from jarvis.models.model_adapter import get_reasoning_model, get_vision_model

# Get reasoning model (GPT-OSS 120B)
reasoner = get_reasoning_model()
response = reasoner.generate("Plan a multi-step task...")

# Get vision model (Gemma 3 27B)
classifier = get_vision_model()
intent = classifier.generate_json("Classify this request...", schema=intent_schema)
```

## Configuration

Edit `settings.py` to customize model behavior:

```python
# Model names (must match Ollama model tags)
REASONING_MODEL_NAME = "gpt-oss:120b"
VISION_MODEL_NAME = "gemma3:27b"

# API endpoints
OLLAMA_BASE_URL = "http://localhost:11434"
CLOUD_FALLBACK_URL = "https://api.example.com/v1"

# Timeouts and limits
REASONING_TIMEOUT = 300  # seconds
VISION_TIMEOUT = 180     # seconds
```

## Troubleshooting

### Model Not Loading
1. Verify Ollama is running: `ollama serve`
2. Check models are pulled: `ollama list`
3. Pull missing models: `ollama pull gpt-oss:120b`

### Fallback Activated
If you see "Using fallback classification/planning", check:
- Model server connectivity
- Model availability in Ollama
- Timeout settings in `settings.py`

### Performance Issues
- Reduce token limits in `settings.py`
- Lower temperature for more deterministic output
- Enable caching for repeated queries

## Rollback Procedure

If issues occur, revert to legacy version:

```bash
# Stop current process
# Rename files
mv jarvis.py jarvis_current.py
mv jarvis_legacy.py jarvis.py

# Run legacy version
python jarvis.py --mode chat
```

## Next Steps

1. **Monitor Performance**: Track model response times and accuracy
2. **Fine-tune Prompts**: Optimize system prompts for your use case
3. **Add Capabilities**: Extend the registry with custom tools
4. **Scale Deployment**: Consider containerization for production

## Support

For issues or questions:
- Check logs in `/workspace/logs/`
- Run health check: `python jarvis.py --test`
- Review model adapter tests: `python test_capabilities_integration.py`

---

**Migration Completed**: $(date)
**Architecture Version**: 2.0 (Capability-Based)
**Models Integrated**: GPT-OSS 120B, Gemma 3 27B
