# JARVIS Test Suite

This directory contains all test files for the JARVIS project.

## Test Files

### Integration Tests
- `test_capabilities_integration.py` - Tests for capability registry and tool integration
- `test_pipeline.py` - End-to-end pipeline testing

### Unit Tests
- `test_arg_normalization.py` - Argument normalization unit tests
- `test_tool_execution_pipeline.py` - Tool execution pipeline tests

### Examples
- `example_tool_execution.py` - Example tool execution scenarios

## Running Tests

```bash
# Run all tests
python -m pytest jarvis/tests/

# Run specific test
python -m pytest jarvis/tests/test_capabilities_integration.py

# Run with coverage
python -m pytest jarvis/tests/ --cov=jarvis
```

## Requirements
- pytest
- pytest-cov (optional, for coverage)
- All dependencies from `requirements.txt`
