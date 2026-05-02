#!/usr/bin/env python3
"""
Phase 4: Memory & Context System - Comprehensive Test Suite

Tests all memory components:
- Working Memory (short-term conversation buffer)
- Episodic Memory (session-based event storage)
- Semantic Memory (fact/knowledge storage)
- Procedural Memory (learned patterns/skills)
- Core Memory Integration (unified interface)
"""

import sys
from pathlib import Path

# Add parent directory (workspace root) to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.core.memory import CoreMemory
from jarvis.memory.working import WorkingMemory
from jarvis.memory.episodic import EpisodicMemory
from jarvis.memory.semantic import SemanticMemory
from jarvis.memory.procedural import ProceduralMemory


def test_working_memory():
    """Test working memory operations."""
    print("\n=== Testing Working Memory ===")
    
    wm = WorkingMemory(max_messages=10, max_tokens_estimate=2000)
    
    # Test adding messages
    wm.add_message('user', 'Hello, how are you?')
    wm.add_message('assistant', 'I am doing well, thank you!')
    wm.add_message('system', 'System initialized')
    
    assert len(wm.messages) == 3, "Should have 3 messages"
    print("✓ Added messages successfully")
    
    # Test getting recent messages
    recent = wm.get_recent_messages(5)
    assert len(recent) == 3, "Should return all 3 messages"
    print("✓ Retrieved recent messages")
    
    # Test tool result tracking
    wm.add_tool_result('file_read', {'content': 'test data', 'success': True})
    assert len(wm.messages) == 4, "Should have 4 messages after tool result"
    print("✓ Tool results tracked")
    
    # Test message limiting
    for i in range(15):
        wm.add_message('user', f'Message {i}')
    
    assert len(wm.messages) <= 10, "Should limit to max_messages"
    print("✓ Message limiting works")
    
    # Test token estimation via stats
    stats = wm.get_stats()
    assert stats['estimated_tokens'] > 0, "Token estimate should be positive"
    print(f"✓ Token estimation: ~{stats['estimated_tokens']} tokens")
    
    # Test clearing
    wm.clear()
    assert len(wm.messages) == 0, "Should be empty after clear"
    print("✓ Clear working memory")
    
    print("\n✅ Working Memory: ALL TESTS PASSED")
    return True


def test_episodic_memory():
    """Test episodic memory operations."""
    print("\n=== Testing Episodic Memory ===")
    
    em = EpisodicMemory(data_dir='/workspace/jarvis_data')
    
    # Test starting a session
    session_id = em.start_session()
    assert session_id is not None, "Should return session ID"
    print(f"✓ Started session: {session_id}")
    
    # Test storing session with messages
    messages = [
        {'role': 'user', 'content': 'What is the weather?'},
        {'role': 'assistant', 'content': 'It is sunny today.'}
    ]
    stored_id = em.store_session(session_id=session_id, messages=messages, 
                                  metadata={'goal': 'weather check', 'success': True})
    assert stored_id is not None, "Should store session"
    print("✓ Stored session with metadata")
    
    # Test loading session
    loaded = em.load_session(stored_id)
    assert loaded is not None, "Should load session"
    assert loaded['message_count'] == 2, "Should have 2 messages"
    print("✓ Loaded session successfully")
    
    # Test searching sessions
    results = em.search_sessions('weather')
    assert isinstance(results, list), "Should return list of results"
    print(f"✓ Session search returned {len(results)} results")
    
    # Test listing sessions
    sessions = em.list_sessions(limit=10)
    assert len(sessions) >= 1, "Should have at least one session"
    print(f"✓ Listed {len(sessions)} sessions")
    
    # Test ending session
    ended_id = em.end_session(stored_id, messages=[{'role': 'user', 'content': 'Bye'}], 
                               summary='Test session completed')
    assert ended_id is not None, "Should end session"
    print("✓ Ended session with summary")
    
    # Test session stats
    stats = em.get_memory_stats()
    print(f"✓ Total sessions: {stats.get('total_sessions', len(sessions))}")
    
    print("\n✅ Episodic Memory: ALL TESTS PASSED")
    return True


def test_semantic_memory():
    """Test semantic memory operations."""
    print("\n=== Testing Semantic Memory ===")
    
    sm = SemanticMemory(data_dir='/workspace/jarvis_data')
    
    # Test adding facts
    fact_id1 = sm.add_fact('The user prefers dark mode', category='preferences')
    assert fact_id1 is not None, "Should add fact"
    print("✓ Added fact with category")
    
    fact_id2 = sm.add_fact('Python is a programming language', category='knowledge')
    assert fact_id2 is not None, "Should add fact"
    print("✓ Added another fact")
    
    # Test getting facts by category
    facts = sm.get_facts_by_category('preferences')
    assert len(facts) >= 1, "Should retrieve facts by category"
    print(f"✓ Retrieved {len(facts)} facts from category")
    
    # Test search
    results = sm.search('programming', top_k=5)
    assert isinstance(results, list), "Search should return list"
    print(f"✓ Search returned {len(results)} results")
    
    # Test TF-IDF vectorization
    tfidf_vec = sm._compute_tf(sm._tokenize('test query'))
    assert tfidf_vec is not None, "Should create TF vector"
    assert len(tfidf_vec) > 0, "Vector should not be empty"
    print("✓ TF-IDF vectorization works")
    
    # Test fact count
    stats = sm.get_stats()
    print(f"✓ Total facts stored: {stats['total_facts']}")
    
    print("\n✅ Semantic Memory: ALL TESTS PASSED")
    return True


def test_procedural_memory():
    """Test procedural memory operations."""
    print("\n=== Testing Procedural Memory ===")
    
    pm = ProceduralMemory(storage_path=None)
    
    # Test learning a pattern
    context = {'goal': 'open application', 'app_type': 'browser'}
    steps = [
        {'tool': 'find_app', 'params': {'name': 'chrome'}},
        {'tool': 'launch_app', 'params': {'app': 'chrome'}}
    ]
    
    pm.learn_pattern(
        name='open_browser',
        steps=steps,
        context=context
    )
    assert 'open_browser' in pm.patterns, "Should store procedure"
    print("✓ Stored procedure")
    
    # Test listing procedures
    procedures = pm.list_patterns()
    assert len(procedures) >= 1, "Should list procedures"
    print(f"✓ Listed {len(procedures)} procedures")
    
    # Test retrieving procedure
    retrieved = pm.get_pattern('open_browser')
    assert retrieved is not None, "Should retrieve procedure"
    assert retrieved.confidence > 0, "Should have confidence score"
    print("✓ Retrieved procedure")
    
    # Test updating on success - get fresh reference and record success
    updated = pm.get_pattern('open_browser')
    updated.record_success()
    assert updated.success_count >= 1, "Should track successes"
    print(f"✓ Updated success count: {updated.success_count}")
    
    # Test finding patterns by context
    matches = pm.find_patterns_by_context(context)
    assert isinstance(matches, list), "Should return matching patterns"
    print(f"✓ Found {len(matches)} matching patterns")
    
    print("\n✅ Procedural Memory: ALL TESTS PASSED")
    return True


def test_core_memory_integration():
    """Test core memory integration of all memory types."""
    print("\n=== Testing Core Memory Integration ===")
    
    config = {
        'working_memory_max_messages': 20,
        'working_memory_max_tokens': 4000,
        'data_dir': '/workspace/jarvis_data'
    }
    
    cm = CoreMemory(config)
    
    # Test adding messages
    cm.add_user_message('Remember that I like coffee')
    cm.add_assistant_message('I will remember that you like coffee')
    cm.add_system_message('User preference noted')
    
    assert len(cm.working.messages) == 3, "Should have 3 messages in working memory"
    print("✓ Added messages through core interface")
    
    # Test tool result
    cm.add_tool_result('set_preference', {'status': 'saved'})
    print("✓ Added tool result")
    
    # Test context retrieval
    context = cm.retrieve_context(query='coffee', limit=5)
    assert 'working' in context, "Context should include working memory"
    assert 'episodic' in context, "Context should include episodic memory"
    assert 'semantic' in context, "Context should include semantic memory"
    assert 'procedural' in context, "Context should include procedural memory"
    print("✓ Retrieved integrated context from all memory types")
    
    # Test storing experience
    session_id = cm.store_experience(
        goal='Get user preference',
        actions=[{'tool': 'ask_user', 'result': 'coffee'}],
        outcome='User prefers coffee',
        success=True
    )
    assert session_id is not None, "Should store experience"
    print("✓ Stored complete experience")
    
    # Test explicit fact storage
    cm.remember_fact('User drinks coffee in the morning', category='habits')
    print("✓ Stored explicit fact")
    
    # Test memory recall
    memories = cm.recall_memories('coffee', limit=5)
    assert isinstance(memories, list), "Should return list of memories"
    print(f"✓ Recalled {len(memories)} relevant memories")
    
    # Test conversation history
    history = cm.get_conversation_history()
    assert len(history) >= 3, "Should have conversation history"
    print("✓ Retrieved conversation history")
    
    # Test memory stats
    stats = cm.get_memory_stats()
    assert 'working' in stats, "Stats should include working memory"
    assert 'episodic' in stats, "Stats should include episodic memory"
    assert 'semantic' in stats, "Stats should include semantic memory"
    assert 'procedural' in stats, "Stats should include procedural memory"
    print(f"✓ Memory stats: {stats['working']['message_count']} working, "
          f"{stats['episodic']['session_count']} episodic, "
          f"{stats['semantic']['fact_count']} semantic, "
          f"{stats['procedural']['pattern_count']} procedural")
    
    # Test session management
    new_session = cm.start_new_session('Test Session')
    assert new_session is not None, "Should start new session"
    print(f"✓ Started new session: {new_session}")
    
    ended = cm.end_current_session(summary='Test completed')
    assert ended is not None, "Should end session"
    print(f"✓ Ended session: {ended}")
    
    print("\n✅ Core Memory Integration: ALL TESTS PASSED")
    return True


def run_all_tests():
    """Run all Phase 4 memory tests."""
    print("=" * 60)
    print("PHASE 4: MEMORY & CONTEXT SYSTEM - TEST SUITE")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(('Working Memory', test_working_memory()))
    except Exception as e:
        print(f"\n❌ Working Memory FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(('Working Memory', False))
    
    try:
        results.append(('Episodic Memory', test_episodic_memory()))
    except Exception as e:
        print(f"\n❌ Episodic Memory FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(('Episodic Memory', False))
    
    try:
        results.append(('Semantic Memory', test_semantic_memory()))
    except Exception as e:
        print(f"\n❌ Semantic Memory FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(('Semantic Memory', False))
    
    try:
        results.append(('Procedural Memory', test_procedural_memory()))
    except Exception as e:
        print(f"\n❌ Procedural Memory FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(('Procedural Memory', False))
    
    try:
        results.append(('Core Integration', test_core_memory_integration()))
    except Exception as e:
        print(f"\n❌ Core Integration FAILED: {e}")
        import traceback
        traceback.print_exc()
        results.append(('Core Integration', False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 PHASE 4 COMPLETE: All memory systems operational!")
        return True
    else:
        print(f"\n⚠️ PHASE 4 INCOMPLETE: {total - passed} test(s) failed")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
