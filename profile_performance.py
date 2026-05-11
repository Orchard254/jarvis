#!/usr/bin/env python3
"""
Performance Profiling Script for JARVIS System
Identifies bottlenecks in tool execution and LLM response
"""

import cProfile
import pstats
import io
import time
import sys
from pathlib import Path

# Add workspace to path
sys.path.insert(0, '/workspace')

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
    """Profile cache lookup operations - REMOVED: intent learner no longer exists"""
    print("\n=== Cache Operations Profiling Removed ===")
    print("Intent learning/cache system has been removed.")
    print("All tool selection is now handled directly by the main LLM.")
    return "Cache operations profiling removed"

def run_comprehensive_profile():
    """Run all profiling tests and generate report"""
    print("=" * 80)
    print("JARVIS PERFORMANCE PROFILING REPORT")
    print("=" * 80)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = {}
    
    # Router/classifier profiling removed - intent router no longer exists
    
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
    
    if 'cosine' in classifier_output.lower() or 'dot' in classifier_output.lower():
        bottlenecks.append("• Embedding similarity calculations are expensive - consider approximate nearest neighbor search")
    
    if 'classify' in classifier_output.lower() and 'cumulative' in classifier_output.lower():
        bottlenecks.append("• Classification loop runs through all tools - early exit on high confidence already implemented ✓")
    
    # Cache/router bottlenecks removed - intent system no longer exists
    
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
