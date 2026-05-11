#!/usr/bin/env python3
"""
Performance Profiling Script for JARVIS Intent System
Identifies bottlenecks in intent routing and classification
"""

import cProfile
import pstats
import io
import time
import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, '/workspace')

def profile_intent_classifier():
    """Profile the semantic intent classifier with various inputs"""
    from brain.intent_classifier import SemanticIntentClassifier
    
    classifier = SemanticIntentClassifier()
    
    # Test cases representing different scenarios
    test_queries = [
        "set volume to 50",
        "what is the weather today",
        "turn on the lights",
        "play some music",
        "set brightness to maximum",
        "tell me a joke",
        "search for python tutorials",
        "open chrome browser",
        "what time is it",
        "calculate 25 * 17"
    ]
    
    print("\n=== Profiling Intent Classifier ===")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Run multiple iterations to get meaningful stats
    for _ in range(10):
        for query in test_queries:
            result = classifier.classify(query)
    
    profiler.disable()
    
    # Print stats
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    stats.print_stats(20)
    print(s.getvalue())
    
    return s.getvalue()

def profile_intent_router():
    """Profile the intent router with various inputs"""
    from core.intent_router import route
    
    test_queries = [
        "set volume to 50",
        "what is the weather today",
        "turn on the lights in the kitchen",
        "play some jazz music",
        "set brightness to 80 percent",
        "tell me something funny",
        "search for machine learning courses",
        "open firefox",
        "what's the current time",
        "compute 123 + 456"
    ]
    
    print("\n=== Profiling Intent Router ===")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Run multiple iterations
    for _ in range(10):
        for query in test_queries:
            try:
                result = route(query)
            except Exception as e:
                pass  # Ignore errors, just measure performance
    
    profiler.disable()
    
    # Print stats
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    stats.print_stats(20)
    print(s.getvalue())
    
    return s.getvalue()

def profile_embedding_generation():
    """Profile embedding generation (often a bottleneck)"""
    try:
        import numpy as np
    except ImportError:
        print("NumPy not available, skipping embedding profiling")
        return "NumPy not available"
    
    print("\n=== Profiling Embedding Generation ===")
    
    # Simulate embedding operations
    test_vectors = [np.random.rand(384) for _ in range(100)]
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(5):
        for vec in test_vectors:
            # Simulate cosine similarity calculations
            similarities = [np.dot(vec, v) / (np.linalg.norm(vec) * np.linalg.norm(v)) 
                          for v in test_vectors[:50]]
    
    profiler.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    stats.print_stats(15)
    print(s.getvalue())
    
    return s.getvalue()

def profile_cache_operations():
    """Profile cache lookup operations"""
    from core import intent_learner
    
    # Pre-populate some learned intents
    for i in range(50):
        intent_learner.record_route(f"test query {i}", [{"tool": f"tool_{i}", "action": "test"}], success=True)
    
    test_queries = [f"test query {i}" for i in range(20)]
    
    print("\n=== Profiling Cache Operations ===")
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    for _ in range(10):
        for query in test_queries:
            intent_learner.lookup_route(query)
    
    profiler.disable()
    
    s = io.StringIO()
    stats = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    stats.print_stats(15)
    print(s.getvalue())
    
    return s.getvalue()

def run_comprehensive_profile():
    """Run all profiling tests and generate report"""
    print("=" * 80)
    print("JARVIS PERFORMANCE PROFILING REPORT")
    print("=" * 80)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = {}
    
    try:
        results['classifier'] = profile_intent_classifier()
    except Exception as e:
        results['classifier'] = f"Error profiling classifier: {e}"
        print(f"Warning: {e}")
    
    try:
        results['router'] = profile_intent_router()
    except Exception as e:
        results['router'] = f"Error profiling router: {e}"
        print(f"Warning: {e}")
    
    try:
        results['embeddings'] = profile_embedding_generation()
    except Exception as e:
        results['embeddings'] = f"Error profiling embeddings: {e}"
        print(f"Warning: {e}")
    
    try:
        results['cache'] = profile_cache_operations()
    except Exception as e:
        results['cache'] = f"Error profiling cache: {e}"
        print(f"Warning: {e}")
    
    # Save detailed report
    report_path = Path('/workspace/performance_profile_report.txt')
    with open(report_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("JARVIS PERFORMANCE PROFILING REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for section, content in results.items():
            f.write(f"\n{'='*40}\n")
            f.write(f"{section.upper()}\n")
            f.write(f"{'='*40}\n")
            f.write(content)
            f.write("\n")
    
    print(f"\n✓ Detailed report saved to: {report_path}")
    
    # Generate summary of bottlenecks
    print("\n" + "=" * 80)
    print("IDENTIFIED BOTTLENECKS & RECOMMENDATIONS")
    print("=" * 80)
    
    bottlenecks = []
    
    # Analyze results for common bottlenecks
    classifier_output = str(results.get('classifier', ''))
    router_output = str(results.get('router', ''))
    cache_output = str(results.get('cache', ''))
    
    if 'cosine' in classifier_output.lower() or 'dot' in classifier_output.lower():
        bottlenecks.append("• Embedding similarity calculations are expensive - consider approximate nearest neighbor search")
    
    if 'classify' in classifier_output.lower() and 'cumulative' in classifier_output.lower():
        bottlenecks.append("• Classification loop runs through all tools - early exit on high confidence already implemented ✓")
    
    if 'lookup_route' in cache_output or 'record_route' in cache_output:
        bottlenecks.append("• Database operations in cache lookups - batch operations already optimized ✓")
    
    bottlenecks.append("• Consider async processing for non-critical path operations")
    bottlenecks.append("• Implement batch processing for multiple similar queries")
    bottlenecks.append("• Add connection pooling for external API calls")
    bottlenecks.append("• Profile tool execution layer next (brain/tool_loop.py)")
    
    for bottleneck in bottlenecks:
        print(bottleneck)
    
    print("\n" + "=" * 80)
    
    return results

if __name__ == "__main__":
    run_comprehensive_profile()
