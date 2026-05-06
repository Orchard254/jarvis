# Tree of Thoughts (ToT) Testing Guide

## Overview
This guide provides comprehensive testing strategies for JARVIS's Tree of Thoughts implementation, covering unit tests, integration tests, demo scripts, and manual testing approaches.

## ✅ Quick Start - Run All Tests

```bash
# Activate virtual environment
cd /workspace
source venv/bin/activate

# Run ToT unit tests
python -m pytest jarvis/tests/test_tot.py -v

# Run the interactive demo
python jarvis/examples/tot_demo.py
```

## 📋 Test Components

### 1. Unit Tests (`jarvis/tests/test_tot.py`)

The unit test suite covers all core ToT components:

#### ThoughtNode Tests
- `test_create_node`: Verifies node creation with default values
- `test_node_to_dict`: Tests serialization to dictionary format

#### TreeOfThoughtsEngine Tests
- `test_initialize_tree`: Creates root node from problem statement
- `test_generate_branches`: Generates multiple solution paths from LLM
- `test_evaluate_node`: Scores nodes based on promise/relevance
- `test_reconstruct_path`: Traces path from leaf to root

#### AdvancedReActAgent Tests
- `test_complex_task_detection`: Identifies tasks requiring ToT vs ReAct
- `test_parse_action`: Extracts tool calls from LLM responses
- `test_parse_action_none`: Handles final answer scenarios

#### Integration Flow Test
- `test_tot_solve_flow`: End-to-end solving with mock LLM

**Expected Output:**
```
============================== 10 passed in 0.48s ==============================
```

### 2. Demo Script (`jarvis/examples/tot_demo.py`)

The demo showcases three key scenarios:

#### A. Tree of Thoughts Engine Demo
Demonstrates the complete ToT solving process:
- Problem: "Research and analyze the latest trends in AI safety"
- Shows branching, evaluation, and beam search
- Displays solution path with scores

#### B. Advanced Agent Demo
Shows automatic ToT/ReAct selection:
- **Complex task**: "Plan a comprehensive research strategy for AI safety" → Uses ToT
- **Simple task**: "Open a file" → Uses standard ReAct

#### C. Visualization Demo
Displays tree structure with scores:
```
Root: How to improve AI alignment?
├── c1 (0.80): Research current methods
│   └── gc1 (0.90): Literature review ★
├── c2 (0.75): Consult experts
└── c3 (0.85): Run experiments
```

**Expected Output:**
```
✅ ALL DEMOS COMPLETED SUCCESSFULLY
```

### 3. Manual Testing Scenarios

#### Scenario 1: Complex Multi-Step Planning
```python
from jarvis.core.tot_engine import TreeOfThoughtsEngine
from jarvis.core.llm import LLMInterface

llm = LLMInterface()
engine = TreeOfThoughtsEngine(
    llm_interface=llm,
    max_depth=5,
    beam_width=3,
    max_branches=4
)

solution = await engine.solve(
    problem="Plan a 3-month AI research project with budget constraints",
    tools_context={"available_tools": [...]}
)
print(solution)
```

#### Scenario 2: Comparative Analysis
```python
problem = "Compare 5 different cloud providers for ML workloads considering cost, performance, and ease of use"
solution = await engine.solve(problem, {})
```

#### Scenario 3: Strategic Decision Making
```python
problem = "Decide whether to build or buy a customer support chatbot system"
solution = await engine.solve(problem, {})
```

### 4. Integration Tests

Test ToT integration with other JARVIS components:

```bash
# Run full integration suite
python -m pytest tests/integration/test_jarvis_integration.py -v

# Test with real tools (requires API keys)
python test_tools.py
```

## 🔧 Configuration Testing

### Adjust Beam Width
Test different beam widths to see impact on solution quality:

```python
# Narrow beam (faster, may miss optimal)
engine = TreeOfThoughtsEngine(llm, beam_width=1)

# Wide beam (slower, better solutions)
engine = TreeOfThoughtsEngine(llm, beam_width=5)
```

### Adjust Depth
Test reasoning depth limits:

```python
# Shallow (quick decisions)
engine = TreeOfThoughtsEngine(llm, max_depth=2)

# Deep (complex planning)
engine = TreeOfThoughtsEngine(llm, max_depth=7)
```

### Adjust Branching Factor
Control how many options are generated per node:

```python
# Fewer branches
engine = TreeOfThoughtsEngine(llm, max_branches=2)

# More branches
engine = TreeOfThoughtsEngine(llm, max_branches=6)
```

## 📊 Performance Metrics to Monitor

When testing, track these metrics:

1. **LLM Calls**: Number of API requests made
   - Lower = faster/cheaper
   - Higher = more thorough exploration

2. **Nodes Generated**: Total thought nodes created
   - Indicates search space size

3. **Solution Path Length**: Steps in final solution
   - Shorter = more direct
   - Longer = more comprehensive

4. **Average Node Score**: Quality of explored paths
   - Higher = better evaluation

5. **Pruned Branches**: Paths discarded early
   - Shows effectiveness of evaluation

Example monitoring:
```python
solution = await engine.solve(problem, {})
print(f"LLM calls: {llm.call_count}")
print(f"Nodes created: {len(engine.nodes)}")
print(f"Path length: {len(engine.solution_path)}")
```

## 🐛 Debugging Tips

### Enable Verbose Logging
```python
import logging
logging.getLogger('jarvis.core.tot_engine').setLevel(logging.DEBUG)
```

### Inspect Tree Structure
```python
for node_id, node in engine.nodes.items():
    print(f"{node_id}: {node.content} (score: {node.value_score})")
    print(f"  Children: {node.children}")
```

### Trace Execution Path
```python
print("Solution Path:")
for i, node_id in enumerate(engine.solution_path):
    node = engine.nodes[node_id]
    print(f"  Step {i}: {node.content}")
```

## 🧪 Custom Test Cases

### Test Case Template
```python
import asyncio
from jarvis.core.tot_engine import TreeOfThoughtsEngine

class MockLLM:
    async def generate_async(self, prompt, temperature=0.5):
        # Return custom responses for your test
        return "[{\"thought\": \"Test step\", \"action_type\": \"logic\"}]"

async def test_custom_scenario():
    llm = MockLLM()
    engine = TreeOfThoughtsEngine(llm, max_depth=3, beam_width=2)
    
    problem = "Your custom problem here"
    result = await engine.solve(problem, {})
    
    assert result is not None, "Should find a solution"
    print(f"✓ Test passed: {result}")

asyncio.run(test_custom_scenario())
```

### Example Custom Tests

#### Test 1: Resource Optimization
```python
problem = """
Optimize server resource allocation for:
- 10 web servers
- 5 database servers
- Budget: $10,000/month
- Goal: Maximize uptime while minimizing cost
"""
```

#### Test 2: Risk Assessment
```python
problem = """
Assess risks of deploying AI system in healthcare:
- Patient data privacy
- Diagnostic accuracy
- Regulatory compliance
- Liability concerns
"""
```

#### Test 3: Product Strategy
```python
problem = """
Develop go-to-market strategy for new SaaS product:
- Target audience: Small businesses
- Price point: $99/month
- Competition: 3 established players
- Timeline: 6 months to launch
"""
```

## 🔄 Continuous Testing

### Add to CI/CD Pipeline
```yaml
# .github/workflows/test_tot.yml
name: ToT Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.12
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run ToT tests
        run: pytest jarvis/tests/test_tot.py -v
      - name: Run demo
        run: python jarvis/examples/tot_demo.py
```

## 📈 Benchmarking

Compare ToT vs standard ReAct:

```python
import time

# Measure ReAct
start = time.time()
react_result = await react_agent.process_task(complex_problem, {})
react_time = time.time() - start

# Measure ToT
start = time.time()
tot_result = await tot_engine.solve(complex_problem, {})
tot_time = time.time() - start

print(f"ReAct: {react_time:.2f}s, Success: {react_result['success']}")
print(f"ToT: {tot_time:.2f}s, Success: {tot_solution is not None}")
```

## 🎯 Success Criteria

Your ToT implementation is working correctly if:

✅ All 10 unit tests pass  
✅ Demo script completes without errors  
✅ Complex tasks trigger ToT mode  
✅ Simple tasks use ReAct mode  
✅ Solution paths have scores > 0.5  
✅ Beam search prunes low-value branches  
✅ Path reconstruction works correctly  

## 📚 Additional Resources

- **Architecture Guide**: `jarvis/docs/TOT_GUIDE.md`
- **Source Code**: `jarvis/core/tot_engine.py`
- **Advanced Agent**: `jarvis/core/advanced_agent.py`
- **Unit Tests**: `jarvis/tests/test_tot.py`

## 🆘 Troubleshooting

### Issue: Tests fail with import errors
**Solution**: Install missing dependencies
```bash
pip install pytest pytest-asyncio requests python-dotenv aiofiles psutil
```

### Issue: Demo hangs or times out
**Solution**: Check LLM connectivity or use mock LLM

### Issue: Low solution scores
**Solution**: Adjust evaluation criteria or increase beam_width

### Issue: Too many LLM calls
**Solution**: Reduce max_depth, beam_width, or max_branches

---

**Last Updated**: 2025
**Version**: JARVIS ToT v1.0
