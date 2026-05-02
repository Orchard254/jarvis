# JARVIS Documentation

This directory contains comprehensive documentation for the JARVIS voice-controlled automation framework.

## Quick Start

See the main [README.md](../README.md) in the root directory for installation and usage instructions.

## Documentation Index

### Completion Reports
- **[PHASE3_COMPLETE.md](PHASE3_COMPLETE.md)** - Safety layer integration (input filtering, plan validation, execution monitoring)
- **[DYNAMIC_SCRIPTING_COMPLETE.md](DYNAMIC_SCRIPTING_COMPLETE.md)** - Dynamic Python script generation and execution
- **[DYNAMIC_INTEGRATION_COMPLETE.md](DYNAMIC_INTEGRATION_COMPLETE.md)** - Full dynamic command integration
- **[STT_WHISPER_COMPLETE.md](STT_WHISPER_COMPLETE.md)** - Whisper ASR integration for noise-robust speech recognition

### Enhancement Guides
- **[STT_ENHANCEMENTS.md](STT_ENHANCEMENTS.md)** - Speech-to-text improvements and configuration
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Migration path for upgrading JARVIS versions

### Project Information
- **[CLEANUP_SUMMARY.md](CLEANUP_SUMMARY.md)** - Project cleanup operations and backup information

## Architecture Overview

```
JARVIS/
├── jarvis/              # Core framework
│   ├── core/           # Orchestrator, registry, safety
│   ├── tools/          # Tool implementations
│   ├── memory/         # Short-term and long-term memory
│   └── utils/          # STT, TTS, audio utilities
├── tests/              # Test suite
│   ├── unit/           # Unit tests
│   └── integration/    # Integration tests
└── docs/               # This directory
```

## Testing

Run all tests:
```bash
pytest tests/
```

Run unit tests only:
```bash
pytest tests/unit/
```

Run integration tests only:
```bash
pytest tests/integration/
```
