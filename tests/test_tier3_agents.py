"""
Test suite for Tier 3 Multi-Agent System

Verifies:
- Multi-agent collaboration
- Self-healing workflow
- Dynamic handoff
- Shared context management
"""

import logging
import sys
import unittest
from unittest.mock import Mock, patch

# Mock problematic modules before any imports
class MockPyAutoGUI:
    FAILSAFE = False
    PAUSE = 0.05
    def __getattr__(self, name): return lambda *a, **k: None
    def size(self): return (1920, 1080)
    def position(self): return (0, 0)

class MockWin32:
    def __getattr__(self, name): return lambda *a, **k: None

sys.modules['pyautogui'] = MockPyAutoGUI()
sys.modules['mouseinfo'] = type(sys)('mouseinfo')
sys.modules['win32api'] = MockWin32()
sys.modules['win32gui'] = MockWin32()
sys.modules['win32con'] = MockWin32()
sys.modules['win32process'] = MockWin32()
sys.modules['Xlib'] = type(sys)('Xlib')
sys.modules['Xlib.display'] = type(sys)('Xlib.display')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestSharedContext(unittest.TestCase):
    """Test shared context management."""
    
    def setUp(self):
        from agents.shared_context import SharedContext
        self.context = SharedContext()
    
    def test_create_task(self):
        """Test task creation."""
        task = self.context.create_task("test_001", "Open VLC player")
        self.assertEqual(task.task_id, "test_001")
        self.assertEqual(task.original_goal, "Open VLC player")
        self.assertEqual(task.status, "pending")
    
    def test_update_task(self):
        """Test task state updates."""
        self.context.create_task("test_002", "Find files")
        updated = self.context.update_task("test_002", status="running", current_step=1)
        self.assertEqual(updated.status, "running")
        self.assertEqual(updated.current_step, 1)
    
    def test_working_memory(self):
        """Test shared working memory."""
        self.context.set_working_memory("file_path", "/path/to/file.txt")
        self.context.set_working_memory("result_count", 42)
        
        self.assertEqual(self.context.get_working_memory("file_path"), "/path/to/file.txt")
        self.assertEqual(self.context.get_working_memory("result_count"), 42)
        self.assertEqual(self.context.get_working_memory("nonexistent", "default"), "default")
    
    def test_record_execution(self):
        """Test execution history recording."""
        self.context.record_execution("PlannerAgent", "decompose", 
                                     {"steps": ["step1", "step2"]}, success=True)
        self.context.record_execution("ExecutorAgent", "execute_code", 
                                     {"result": "error"}, success=False, error="Failed")
        
        failures = self.context.get_recent_failures()
        self.assertEqual(len(failures), 1)
        self.assertFalse(failures[0]["success"])
    
    def test_get_full_context(self):
        """Test complete context retrieval for handoff."""
        self.context.create_task("test_003", "Complex task", steps=["step1", "step2"])
        self.context.set_working_memory("intermediate", "data")
        
        full_ctx = self.context.get_full_context("test_003")
        
        self.assertIn("task", full_ctx)
        self.assertIn("working_memory", full_ctx)
        self.assertEqual(full_ctx["task"]["goal"], "Complex task")
        self.assertEqual(full_ctx["task"]["total_steps"], 2)


class TestPlannerAgent(unittest.TestCase):
    """Test planner agent functionality."""
    
    def setUp(self):
        from agents.planner_agent import PlannerAgent
        from agents.shared_context import SharedContext
        self.context = SharedContext()
        self.planner = PlannerAgent(shared_context=self.context)
    
    def test_analyze_simple_task(self):
        """Test analysis of simple tasks."""
        result = self.planner.analyze_task("Open Notepad")
        self.assertIn("complexity_score", result)
        self.assertIn("is_simple", result)
        # Simple tasks should be classified as simple
        self.assertTrue(result["is_simple"])
        self.assertEqual(result["recommendation"], "direct_execution")
    
    def test_analyze_compound_task(self):
        """Test analysis of compound tasks."""
        result = self.planner.analyze_task("Find all Python files and then open them")
        self.assertIn("complexity_score", result)
        # Compound tasks should need decomposition (or have higher complexity)
        self.assertTrue(result.get("complexity_score", 1) >= 2 or not result.get("is_simple", True))
    
    def test_parse_steps(self):
        """Test step parsing from LLM response."""
        content = """
1. First step description
2. Second step with more details
3. Third and final step
"""
        steps = self.planner._parse_steps(content)
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0], "First step description")
    
    def test_validate_plan(self):
        """Test plan validation."""
        valid_steps = ["Step one", "Step two", "Step three"]
        is_valid, reason = self.planner.validate_plan(valid_steps, "Test goal")
        self.assertTrue(is_valid)
        
        # Empty plan should fail
        is_valid, reason = self.planner.validate_plan([], "Test goal")
        self.assertFalse(is_valid)
        
        # Too many steps should fail
        too_many = [f"Step {i}" for i in range(15)]
        is_valid, reason = self.planner.validate_plan(too_many, "Test goal")
        self.assertFalse(is_valid)
    
    def test_optimize_plan(self):
        """Test plan optimization."""
        steps = ["Do something", "Do something", "Next thing"]
        optimized = self.planner.optimize_plan(steps)
        # Should remove duplicate (merges consecutive duplicates)
        self.assertLessEqual(len(optimized), 2)
        self.assertIn("Next thing", optimized[-1] if optimized else "")


class TestCoderAgent(unittest.TestCase):
    """Test coder agent functionality."""
    
    def setUp(self):
        from agents.coder_agent import CoderAgent
        from agents.shared_context import SharedContext
        self.context = SharedContext()
        self.coder = CoderAgent(shared_context=self.context)
    
    def test_validate_safe_code(self):
        """Test code validation with safe code."""
        safe_code = """
import os
import json

def list_files(path):
    return os.listdir(path)
"""
        result = self.coder._validate_code(safe_code)
        self.assertTrue(result["is_valid"])
    
    def test_validate_unsafe_code(self):
        """Test code validation detects dangerous patterns."""
        unsafe_code = """
eval(user_input)
exec(dangerous_code)
"""
        result = self.coder._validate_code(unsafe_code)
        # Should have warnings about dangerous patterns
        self.assertTrue(len(result["warnings"]) > 0)
    
    def test_extract_code_from_markdown(self):
        """Test code extraction from markdown blocks."""
        content = """
Here's the code you requested:

```python
import os
print("Hello")
```

Hope this helps!
"""
        code, explanation = self.coder._extract_code(content)
        self.assertIn("import os", code)
        self.assertIn("print", code)
    
    def test_diagnose_error(self):
        """Test error diagnosis."""
        diagnoses = [
            ("SyntaxError: invalid syntax", "syntax"),
            ("NameError: name 'x' is not defined", "name"),
            ("FileNotFoundError: [Errno 2] No such file", "file"),
            ("PermissionError: Access is denied", "permission"),
            ("ModuleNotFoundError: No module named 'xyz'", "module"),
        ]
        
        for error_msg, expected_type in diagnoses:
            diagnosis = self.coder._diagnose_error(error_msg, "")
            self.assertIn(expected_type, diagnosis.lower())


class TestExecutorAgent(unittest.TestCase):
    """Test executor agent functionality."""
    
    def setUp(self):
        from agents.executor_agent import ExecutorAgent
        from agents.shared_context import SharedContext
        self.context = SharedContext()
        self.executor = ExecutorAgent(shared_context=self.context)
    
    def test_detect_success(self):
        """Test success detection."""
        success_result = {"success": True, "result": "data"}
        fail_result = {"success": False, "error": "failed"}
        stderr_result = {"stdout": "", "stderr": "error message"}
        
        self.assertTrue(self.executor._is_success(success_result))
        self.assertFalse(self.executor._is_success(fail_result))
        self.assertFalse(self.executor._is_success(stderr_result))
    
    def test_extract_error(self):
        """Test error extraction from results."""
        result1 = {"error": "Something went wrong"}
        result2 = {"stderr": "Error message"}
        result3 = {"message": "Failure occurred"}
        
        self.assertEqual(self.executor._extract_error(result1), "Something went wrong")
        self.assertEqual(self.executor._extract_error(result2), "Error message")
        self.assertEqual(self.executor._extract_error(result3), "Failure occurred")
    
    def test_analyze_failure_types(self):
        """Test failure analysis for different error types."""
        test_cases = [
            ("SyntaxError: invalid syntax", "syntax_error"),
            ("NameError: x not defined", "name_error"),
            ("FileNotFoundError", "file_not_found"),
            ("PermissionError: Access denied", "permission_error"),
            ("Operation timed out", "timeout"),
        ]
        
        for error_msg, expected_type in test_cases:
            analysis = self.executor._analyze_failure(error_msg, "", {})
            self.assertEqual(analysis["type"], expected_type, 
                           f"Failed to classify: {error_msg}")
    
    def test_detect_infinite_loop(self):
        """Test infinite loop detection."""
        loop_code = """
while True:
    print("stuck")
"""
        safe_code = """
for i in range(10):
    print(i)
"""
        self.assertTrue(self.executor._detect_infinite_loop(loop_code))
        self.assertFalse(self.executor._detect_infinite_loop(safe_code))


class TestSupervisor(unittest.TestCase):
    """Test supervisor coordination."""
    
    def setUp(self):
        from agents.supervisor import Supervisor
        self.supervisor = Supervisor()
    
    def test_supervisor_initialization(self):
        """Test supervisor initializes all agents."""
        self.assertIsNotNone(self.supervisor._planner)
        self.assertIsNotNone(self.supervisor._coder)
        self.assertIsNotNone(self.supervisor._executor)
        self.assertIsNotNone(self.supervisor._shared_context)
    
    def test_get_system_status(self):
        """Test system status reporting."""
        status = self.supervisor.get_system_status()
        self.assertIn("pending_tasks", status)
        self.assertIn("completed_tasks", status)
        self.assertIn("recent_failures", status)
    
    def test_reset(self):
        """Test supervisor reset."""
        self.supervisor._pending_tasks["test"] = {"data": "value"}
        self.supervisor.reset()
        self.assertEqual(len(self.supervisor._pending_tasks), 0)


class TestIntegration(unittest.TestCase):
    """Integration tests for multi-agent workflow."""
    
    def test_agent_imports(self):
        """Test all agents can be imported."""
        from agents import (
            PlannerAgent,
            CoderAgent,
            ExecutorAgent,
            Supervisor,
            SharedContext
        )
        
        # Verify classes exist
        self.assertTrue(hasattr(PlannerAgent, 'analyze_task'))
        self.assertTrue(hasattr(CoderAgent, 'generate_code'))
        self.assertTrue(hasattr(ExecutorAgent, 'execute_task'))
        self.assertTrue(hasattr(Supervisor, 'process_task'))
    
    def test_shared_context_integration(self):
        """Test shared context works across agents."""
        from agents.shared_context import SharedContext
        from agents.planner_agent import PlannerAgent
        
        context = SharedContext()
        planner = PlannerAgent(shared_context=context)
        
        # Create task
        context.create_task("int_test", "Integration test task")
        
        # Planner records execution
        context.record_execution("PlannerAgent", "test", {}, success=True)
        
        # Verify data is accessible
        task = context.get_task("int_test")
        self.assertIsNotNone(task)
        
        failures = context.get_recent_failures()
        self.assertIsInstance(failures, list)


if __name__ == "__main__":
    print("=" * 60)
    print("Tier 3 Multi-Agent System Test Suite")
    print("=" * 60)
    
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSharedContext))
    suite.addTests(loader.loadTestsFromTestCase(TestPlannerAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestCoderAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutorAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestSupervisor))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ All Tier 3 tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
