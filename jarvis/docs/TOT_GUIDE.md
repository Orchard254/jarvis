# Tree of Thoughts (ToT) Implementation Guide

## Overview
The Tree of Thoughts (ToT) system enables JARVIS to solve complex problems through multi-path reasoning, self-evaluation, and strategic backtracking.

## Architecture

### Core Components

1. **ThoughtNode** (`tot_engine.py`)
   - Represents a single reasoning step
   - Tracks parent-child relationships
   - Stores evaluation scores (0.0-1.0)
   - Maintains execution results

2. **TreeOfThoughtsEngine** (`tot_engine.py`)
   - Manages the entire thought tree
   - Implements Beam Search algorithm
   - Generates multiple branches per node
   - Evaluates and prunes low-value paths

3. **AdvancedReActAgent** (`advanced_agent.py`)
   - Integrates ToT with standard ReAct
   - Auto-detects complex tasks
   - Falls back to simple ReAct for easy tasks
   - Executes solution paths from ToT

## How It Works

```
┌─────────────────────────────────────────┐
│  Complex Task Input                     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Task Complexity Check                  │
│  (keywords: plan, strategy, research)   │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴───────┐
       │               │
    Complex        Simple
       │               │
       ▼               ▼
┌─────────────┐  ┌─────────────┐
│   ToT Mode  │  │ ReAct Mode  │
│             │  │             │
│ 1. Branch   │  │ Direct      │
│ 2. Evaluate │  │ execution   │
│ 3. Search   │  │             │
│ 4. Execute  │  │             │
└──────┬──────┘  └──────┬──────┘
       │                │
       └────────┬───────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  Solution + Execution Results           │
└─────────────────────────────────────────┘
```

## Usage Examples

### Basic ToT Engine Usage

```python
from jarvis.core.tot_engine import TreeOfThoughtsEngine
from jarvis.core.llm import LLMInterface

# Initialize
llm = LLMInterface()
engine = TreeOfThoughtsEngine(
    llm_interface=llm,
    max_depth=5,        # Maximum reasoning depth
    beam_width=3,       # Keep top 3 paths at each level
    max_branches=4      # Generate 4 options per node
)

# Solve complex problem
solution = await engine.solve(
    problem="Plan a multi-step research project on AI safety",
    tools_context={"available_tools": [...]}
)

print(solution)
```

### Advanced Agent (Auto ToT/ReAct)

```python
from jarvis.core.advanced_agent import AdvancedReActAgent
from jarvis.core.tool_executor import ToolExecutor

# Initialize
agent = AdvancedReActAgent(
    llm_interface=llm,
    tool_executor=tools,
    use_tot=True  # Enable ToT for complex tasks
)

# Automatically uses ToT for complex tasks
result = await agent.process_task(
    task="Research and compare 5 different AI models, then create a summary report",
    context={"user_preferences": {...}}
)

print(f"Method used: {result['method']}")  # 'tot' or 'react'
print(f"Solution path: {result.get('solution_path', 'N/A')}")
```

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_depth` | 5 | Maximum depth of thought tree |
| `beam_width` | 3 | Number of top paths to keep per level |
| `max_branches` | 4 | Maximum children per node |
| `use_tot` | True | Enable/disable ToT entirely |

## When ToT is Triggered

The agent automatically uses ToT for tasks containing:
- "plan" / "planning"
- "strategy" / "strategic"
- "optimize" / "optimization"
- "compare" / "comparison"
- "analyze" / "analysis"
- "multi-step"
- "complex"
- "research"
- "investigate"

## Performance Considerations

### Beam Search Trade-offs
- **Larger beam_width**: Better solutions, more LLM calls
- **Smaller beam_width**: Faster, may miss optimal paths
- **Recommended**: 3-5 for most tasks

### Depth Limits
- **Shallow (2-3)**: Quick decisions, simple problems
- **Medium (4-6)**: Balanced approach (default)
- **Deep (7+)**: Complex planning, expensive

## Testing

Run the test suite:
```bash
cd /workspace/jarvis
python -m pytest tests/test_tot.py -v
```

Tests cover:
- ThoughtNode creation and serialization
- Tree initialization and branching
- Node evaluation scoring
- Path reconstruction
- Complex task detection
- Action parsing
- End-to-end solving flow

## Extending ToT

### Custom Evaluation Criteria

Modify `evaluate_node()` in `tot_engine.py`:

```python
async def evaluate_node(self, node_id: str, context: str) -> float:
    prompt = f"""
    Evaluate based on:
    1. Cost efficiency (weight: 0.3)
    2. Time required (weight: 0.3)
    3. Success probability (weight: 0.4)
    ...
    """
```

### Alternative Search Strategies

Current: Beam Search  
Future additions:
- DFS with backtracking
- Monte Carlo Tree Search (MCTS)
- A* with heuristic functions

## Debugging

Enable verbose logging:
```python
import logging
logging.getLogger('jarvis.core.tot_engine').setLevel(logging.DEBUG)
```

Key metrics to monitor:
- Number of nodes generated
- Average evaluation scores
- Pruned branches count
- Final solution path length

## Next Steps

1. **Vision Integration**: Add visual UI understanding to thoughts
2. **Parallel Execution**: Run independent branches concurrently
3. **Learning**: Store successful patterns for future reuse
4. **Human Feedback**: Incorporate user corrections into evaluation