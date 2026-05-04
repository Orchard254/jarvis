#!/usr/bin/env python3
"""
Demo script showcasing Tree of Thoughts capabilities in JARVIS.
Run this to see ToT in action with simulated LLM responses.
"""

import asyncio
import sys
sys.path.insert(0, '/workspace')

from jarvis.core.tot_engine import TreeOfThoughtsEngine, ThoughtNode
from jarvis.core.advanced_agent import AdvancedReActAgent

class DemoLLM:
    """Simulated LLM for demonstration purposes."""
    
    def __init__(self):
        self.call_count = 0
        self.scenario = "research"  # Change scenario for different demos
    
    async def generate_async(self, prompt, temperature=0.5):
        self.call_count += 1
        call_id = self.call_count
        
        if "Generate" in prompt and "distinct possible next steps" in prompt:
            # Branching phase
            return '''[
                {"thought": "Search academic databases for recent papers", "action_type": "search"},
                {"thought": "Interview domain experts via email", "action_type": "tool_use"},
                {"thought": "Analyze existing industry reports", "action_type": "search"},
                {"thought": "Create a survey for data collection", "action_type": "tool_use"}
            ]'''
        
        elif "Evaluate this step" in prompt:
            # Evaluation phase - simulate varying scores
            scores = [0.85, 0.72, 0.68, 0.91]
            score_idx = (call_id - 1) % len(scores)
            return str(scores[score_idx])
        
        elif "Think step by step" in prompt:
            # ReAct mode response
            return '''Thought: I need to gather information first
Action: web_search
Action Input: {"query": "latest AI research trends"}
Observation: Found 15 relevant papers from arXiv...
Final Answer: Research complete with 15 papers analyzed.'''
        
        else:
            return "Default response"


class DemoToolExecutor:
    """Simulated tool executor for demonstration."""
    
    async def execute(self, tool_name, args):
        await asyncio.sleep(0.1)  # Simulate execution time
        return {
            "success": True,
            "result": f"Executed {tool_name} with args: {args}",
            "data": f"Sample data from {tool_name}"
        }


async def demo_tot_engine():
    """Demonstrate the Tree of Thoughts Engine."""
    print("\n" + "="*70)
    print("🌳 TREE OF THOUGHTS ENGINE DEMO")
    print("="*70)
    
    llm = DemoLLM()
    engine = TreeOfThoughtsEngine(
        llm_interface=llm,
        max_depth=3,
        beam_width=2,
        max_branches=4
    )
    
    problem = "Research and analyze the latest trends in AI safety"
    print(f"\n📋 Problem: {problem}")
    print("\n🔄 Starting ToT solving process...\n")
    
    solution = await engine.solve(problem, {})
    
    print("\n" + "-"*70)
    print("✅ SOLUTION FOUND:")
    print("-"*70)
    print(solution)
    print("-"*70)
    print(f"\n📊 Statistics:")
    print(f"   Total nodes created: {len(engine.nodes)}")
    print(f"   Solution path length: {len(engine.solution_path)}")
    print(f"   LLM calls made: {llm.call_count}")
    

async def demo_advanced_agent():
    """Demonstrate the Advanced Agent with auto ToT/ReAct selection."""
    print("\n" + "="*70)
    print("🤖 ADVANCED AGENT DEMO (Auto ToT/ReAct)")
    print("="*70)
    
    llm = DemoLLM()
    tools = DemoToolExecutor()
    agent = AdvancedReActAgent(llm, tools, use_tot=True)
    
    # Test complex task (should trigger ToT)
    complex_task = "Plan a comprehensive research strategy for AI safety"
    print(f"\n📋 Task: {complex_task}")
    print(f"🔍 Complexity check: {'COMPLEX' if agent._is_complex_task(complex_task) else 'SIMPLE'}")
    
    result = await agent.process_task(complex_task, {})
    
    print(f"\n📊 Result:")
    print(f"   Method used: {result['method'].upper()}")
    print(f"   Success: {result['success']}")
    if 'solution_path' in result:
        print(f"   Solution path available: Yes")
    
    # Test simple task (should use standard ReAct)
    simple_task = "Open a file"
    print(f"\n\n📋 Task: {simple_task}")
    print(f"🔍 Complexity check: {'COMPLEX' if agent._is_complex_task(simple_task) else 'SIMPLE'}")
    
    result = await agent.process_task(simple_task, {})
    
    print(f"\n📊 Result:")
    print(f"   Method used: {result['method'].upper()}")
    print(f"   Success: {result['success']}")


async def demo_visualization():
    """Visualize the thought tree structure."""
    print("\n" + "="*70)
    print("🎯 THOUGHT TREE VISUALIZATION")
    print("="*70)
    
    llm = DemoLLM()
    engine = TreeOfThoughtsEngine(llm, max_depth=2, beam_width=2, max_branches=3)
    
    root_id = engine.initialize_tree("How to improve AI alignment?")
    
    # Manually create a small tree for visualization
    from jarvis.core.tot_engine import ThoughtNode
    
    child1 = ThoughtNode(id="c1", content="Research current methods", parent_id=root_id, value_score=0.8)
    child2 = ThoughtNode(id="c2", content="Consult experts", parent_id=root_id, value_score=0.75)
    child3 = ThoughtNode(id="c3", content="Run experiments", parent_id=root_id, value_score=0.85)
    
    engine.nodes["c1"] = child1
    engine.nodes["c2"] = child2
    engine.nodes["c3"] = child3
    engine.nodes[root_id].children = ["c1", "c2", "c3"]
    
    grandchild = ThoughtNode(id="gc1", content="Literature review", parent_id="c1", value_score=0.9)
    engine.nodes["gc1"] = grandchild
    engine.nodes["c1"].children = ["gc1"]
    
    print("\nTree Structure:")
    print("\n```")
    print("Root: How to improve AI alignment?")
    print("├── c1 (0.80): Research current methods")
    print("│   └── gc1 (0.90): Literature review ★")
    print("├── c2 (0.75): Consult experts")
    print("└── c3 (0.85): Run experiments")
    print("```")
    print("\n★ = Highest scored path")


async def main():
    """Run all demos."""
    print("\n" + "🚀"*35)
    print(" "*15 + "JARVIS ToT DEMO SUITE" + " "*15)
    print("🚀"*35)
    
    try:
        await demo_tot_engine()
        await demo_advanced_agent()
        await demo_visualization()
        
        print("\n" + "="*70)
        print("✅ ALL DEMOS COMPLETED SUCCESSFULLY")
        print("="*70)
        print("\n💡 Next Steps:")
        print("   1. Integrate with real LLM backend")
        print("   2. Connect to actual tool executor")
        print("   3. Adjust beam_width and max_depth for your use case")
        print("   4. Add custom evaluation criteria")
        print("\n📚 See docs/TOT_GUIDE.md for detailed documentation")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
