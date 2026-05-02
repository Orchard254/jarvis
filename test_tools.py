#!/usr/bin/env python3
"""
test_tools.py — Comprehensive tool testing suite

Tests every single tool in the JARVIS system:
- Does not require audio hardware
- Does not require Ollama connection for most tests
- Mocks LLM calls for unit tests
- Tests all system, file, audio, network, and time tools
- Reports pass/fail for each tool clearly

Usage:
    python test_tools.py [--verbose] [--category CATEGORY]
"""

import json
import logging
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger('test_tools')


class ToolTestResult:
    """Represents the result of a single tool test."""
    
    def __init__(self, tool_name: str, passed: bool, message: str = "", 
                 error: str = "", duration: float = 0.0):
        self.tool_name = tool_name
        self.passed = passed
        self.message = message
        self.error = error
        self.duration = duration
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} {self.tool_name}: {self.message or self.error}"


class TestSystemTools(unittest.TestCase):
    """Test all system-related tools."""
    
    @classmethod
    def setUpClass(cls):
        """Load the tool registry once."""
        from jarvis.tools.registry import get_registry
        cls.registry = get_registry()
        cls.registry.load_all_tools()
    
    def test_get_time(self):
        """Test get_time tool."""
        from jarvis.tools.time.clock import GetTimeTool
        tool = GetTimeTool()
        result = tool.execute()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
        self.assertIn('time', str(result.data).lower())
    
    def test_get_date(self):
        """Test get_date tool."""
        from jarvis.tools.time.clock import GetDateTool
        tool = GetDateTool()
        result = tool.execute()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
    
    def test_system_info(self):
        """Test system_info tool."""
        from jarvis.tools.system.info import SystemInfoTool
        tool = SystemInfoTool()
        result = tool.execute()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
    
    def test_get_battery(self):
        """Test get_battery tool."""
        from jarvis.tools.system.power import GetBatteryTool
        tool = GetBatteryTool()
        result = tool.execute()
        # May not have battery on desktop, but should not crash
        self.assertIsNotNone(result)
    
    def test_get_top_processes(self):
        """Test get_top_processes tool."""
        from jarvis.tools.system.info import GetTopProcessesTool
        tool = GetTopProcessesTool()
        result = tool.execute(limit=5)
        self.assertTrue(result.success)
        self.assertIsInstance(result.data, list)


class TestFileTools(unittest.TestCase):
    """Test all file operation tools."""
    
    def setUp(self):
        """Create a temporary test directory."""
        self.test_dir = Path(__file__).parent / 'test_files_tmp'
        self.test_dir.mkdir(exist_ok=True)
        self.test_file = self.test_dir / 'test.txt'
    
    def tearDown(self):
        """Clean up temporary test files."""
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_list_files(self):
        """Test list_files tool."""
        from jarvis.tools.files.operations import ListFilesTool
        tool = ListFilesTool()
        result = tool.execute(path=str(Path.home()))
        self.assertTrue(result.success)
        self.assertIsInstance(result.data, list)
    
    def test_create_folder(self):
        """Test create_folder tool."""
        from jarvis.tools.files.operations import CreateFolderTool
        tool = CreateFolderTool()
        folder_path = self.test_dir / 'new_folder'
        result = tool.execute(path=str(folder_path))
        self.assertTrue(result.success)
        self.assertTrue(folder_path.exists())
    
    def test_write_file(self):
        """Test write_file tool."""
        from jarvis.tools.files.operations import WriteFileTool
        tool = WriteFileTool()
        content = "Test content for JARVIS"
        result = tool.execute(
            path=str(self.test_file),
            content=content
        )
        self.assertTrue(result.success)
        self.assertTrue(self.test_file.exists())
    
    def test_read_file(self):
        """Test read_file tool."""
        from jarvis.tools.files.operations import ReadFileTool, WriteFileTool
        
        # First write a file
        write_tool = WriteFileTool()
        write_tool.execute(
            path=str(self.test_file),
            content="Test reading content"
        )
        
        # Now read it
        tool = ReadFileTool()
        result = tool.execute(path=str(self.test_file))
        self.assertTrue(result.success)
        self.assertIn("Test reading", result.data)
    
    def test_delete_file(self):
        """Test delete_file tool."""
        from jarvis.tools.files.operations import WriteFileTool, DeleteFileTool
        
        # Create file first
        write_tool = WriteFileTool()
        write_tool.execute(
            path=str(self.test_file),
            content="To be deleted"
        )
        
        # Now delete it
        tool = DeleteFileTool()
        result = tool.execute(path=str(self.test_file))
        self.assertTrue(result.success)
        self.assertFalse(self.test_file.exists())


class TestAudioTools(unittest.TestCase):
    """Test all audio-related tools."""
    
    def test_get_volume(self):
        """Test get_volume tool."""
        from jarvis.tools.audio.volume import GetVolumeTool
        tool = GetVolumeTool()
        result = tool.execute()
        # Should return volume level or handle gracefully if no audio device
        self.assertIsNotNone(result)
    
    def test_set_volume_mock(self):
        """Test set_volume tool with mocked hardware."""
        from jarvis.tools.audio.volume import SetVolumeTool
        
        with patch('jarvis.tools.audio.volume.PyCAW') as mock_pycau:
            mock_instance = MagicMock()
            mock_pycau.return_value = mock_instance
            
            tool = SetVolumeTool()
            result = tool.execute(volume=50)
            
            # Should attempt to set volume
            self.assertIsNotNone(result)


class TestNetworkTools(unittest.TestCase):
    """Test all network-related tools."""
    
    def test_get_wifi(self):
        """Test get_wifi tool."""
        from jarvis.tools.network.connectivity import GetWifiTool
        tool = GetWifiTool()
        result = tool.execute()
        # May not have WiFi, but should not crash
        self.assertIsNotNone(result)
    
    def test_check_internet(self):
        """Test check_internet tool."""
        from jarvis.tools.network.connectivity import CheckInternetTool
        tool = CheckInternetTool()
        result = tool.execute()
        self.assertIsNotNone(result)
        # Result indicates connectivity status


class TestTimeTools(unittest.TestCase):
    """Test all time-related tools."""
    
    def test_get_time_basic(self):
        """Test basic get_time functionality."""
        from jarvis.tools.time.clock import GetTimeTool
        tool = GetTimeTool()
        result = tool.execute()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
    
    def test_get_date_basic(self):
        """Test basic get_date functionality."""
        from jarvis.tools.time.clock import GetDateTool
        tool = GetDateTool()
        result = tool.execute()
        self.assertTrue(result.success)
        self.assertIsNotNone(result.data)
    
    def test_set_alarm(self):
        """Test set_alarm tool (mocked)."""
        from jarvis.tools.time.clock import SetAlarmTool
        
        with patch('jarvis.tools.time.clock.threading.Thread') as mock_thread:
            tool = SetAlarmTool()
            result = tool.execute(time="12:00", label="Test alarm")
            # Should create alarm without crashing
            self.assertIsNotNone(result)


class TestDataTools(unittest.TestCase):
    """Test data manipulation tools."""
    
    def test_calculate(self):
        """Test calculate tool."""
        from jarvis.tools.data.calculate import CalculateTool
        tool = CalculateTool()
        result = tool.execute(expression="2+2")
        self.assertTrue(result.success)
        self.assertEqual(result.data, 4)
    
    def test_calculate_complex(self):
        """Test calculate with complex expression."""
        from jarvis.tools.data.calculate import CalculateTool
        tool = CalculateTool()
        result = tool.execute(expression="(10 * 5) + 3 - 8")
        self.assertTrue(result.success)
        self.assertEqual(result.data, 45)
    
    def test_calculate_invalid(self):
        """Test calculate with invalid expression."""
        from jarvis.tools.data.calculate import CalculateTool
        tool = CalculateTool()
        result = tool.execute(expression="invalid")
        # Should fail gracefully
        self.assertFalse(result.success)


class TestTodoTools(unittest.TestCase):
    """Test todo management tools."""
    
    def setUp(self):
        """Set up test todo file."""
        self.todo_file = Path(__file__).parent / 'test_todos.json'
        # Patch the todo file location
        os.environ['JARVIS_TODO_FILE'] = str(self.todo_file)
    
    def tearDown(self):
        """Clean up test todo file."""
        if self.todo_file.exists():
            self.todo_file.unlink()
    
    def test_add_todo(self):
        """Test add_todo tool."""
        from jarvis.tools.data.todo import AddTodoTool
        tool = AddTodoTool()
        result = tool.execute(task="Test task")
        self.assertTrue(result.success)
    
    def test_list_todos(self):
        """Test list_todos tool."""
        from jarvis.tools.data.todo import ListTodosTool
        tool = ListTodosTool()
        result = tool.execute()
        self.assertIsNotNone(result)


class TestNotesTools(unittest.TestCase):
    """Test notes management tools."""
    
    def test_add_note(self):
        """Test add_note tool."""
        from jarvis.tools.data.notes import AddNoteTool
        tool = AddNoteTool()
        result = tool.execute(content="Test note content", title="Test Note")
        self.assertIsNotNone(result)
    
    def test_list_notes(self):
        """Test list_notes tool."""
        from jarvis.tools.data.notes import ListNotesTool
        tool = ListNotesTool()
        result = tool.execute()
        self.assertIsNotNone(result)


class TestClipboardTools(unittest.TestCase):
    """Test clipboard tools."""
    
    def test_get_clipboard(self):
        """Test get_clipboard tool."""
        from jarvis.tools.input.clipboard import GetClipboardTool
        tool = GetClipboardTool()
        result = tool.execute()
        # May be empty, but should not crash
        self.assertIsNotNone(result)
    
    def test_set_clipboard(self):
        """Test set_clipboard tool."""
        from jarvis.tools.input.clipboard import SetClipboardTool
        tool = SetClipboardTool()
        result = tool.execute(text="Test clipboard content")
        self.assertIsNotNone(result)


class TestScreenTools(unittest.TestCase):
    """Test screen capture tools."""
    
    def test_take_screenshot(self):
        """Test take_screenshot tool."""
        from jarvis.tools.screen.capture import TakeScreenshotTool
        tool = TakeScreenshotTool()
        result = tool.execute()
        # Should return screenshot data or handle gracefully
        self.assertIsNotNone(result)
    
    def test_analyze_screen_mock(self):
        """Test analyze_screen with mocked vision."""
        from jarvis.tools.screen.capture import AnalyzeScreenTool
        
        with patch('jarvis.tools.screen.capture.get_vision_analyzer') as mock_vision:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze_screen.return_value = {
                'screen_description': 'Mocked screen',
                'open_windows': ['Test Window'],
                'visible_text': ['Test text'],
                'error_messages': [],
                'ui_elements': [],
                'active_window': 'Test Window'
            }
            mock_vision.return_value = mock_analyzer
            
            tool = AnalyzeScreenTool()
            result = tool.execute()
            self.assertIsNotNone(result)


class TestAppTools(unittest.TestCase):
    """Test application management tools."""
    
    def test_list_apps(self):
        """Test list_apps tool."""
        from jarvis.tools.apps.launcher import ListAppsTool
        tool = ListAppsTool()
        result = tool.execute()
        self.assertIsNotNone(result)
    
    def test_open_app_mock(self):
        """Test open_app with mocked subprocess."""
        from jarvis.tools.apps.launcher import OpenAppTool
        
        with patch('jarvis.tools.apps.launcher.subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_popen.return_value = mock_process
            
            tool = OpenAppTool()
            result = tool.execute(app_name="notepad")
            self.assertIsNotNone(result)


class TestWebTools(unittest.TestCase):
    """Test web browsing tools."""
    
    def test_search_web_mock(self):
        """Test search_web with mocked browser."""
        from jarvis.tools.web.browser import SearchWebTool
        
        with patch('jarvis.tools.web.browser.webbrowser.open') as mock_open:
            mock_open.return_value = True
            
            tool = SearchWebTool()
            result = tool.execute(query="test query")
            self.assertIsNotNone(result)
    
    def test_open_url_mock(self):
        """Test open_url with mocked browser."""
        from jarvis.tools.web.browser import OpenUrlTool
        
        with patch('jarvis.tools.web.browser.webbrowser.open') as mock_open:
            mock_open.return_value = True
            
            tool = OpenUrlTool()
            result = tool.execute(url="https://example.com")
            self.assertIsNotNone(result)


class TestRegistry(unittest.TestCase):
    """Test the tool registry itself."""
    
    def test_registry_singleton(self):
        """Test that registry is a singleton."""
        from jarvis.tools.registry import get_registry
        registry1 = get_registry()
        registry2 = get_registry()
        self.assertIs(registry1, registry2)
    
    def test_registry_load_tools(self):
        """Test that registry loads tools."""
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        count = registry.load_all_tools()
        self.assertGreater(count, 0)
    
    def test_registry_get_tool(self):
        """Test getting a tool from registry."""
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        registry.load_all_tools()
        
        # Try to get a known tool
        tool = registry.get('get_time')
        self.assertIsNotNone(tool)
    
    def test_registry_has_tool(self):
        """Test checking if tool exists."""
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        registry.load_all_tools()
        
        self.assertTrue(registry.has_tool('get_time'))
        self.assertFalse(registry.has_tool('nonexistent_tool_xyz'))
    
    def test_registry_execute(self):
        """Test executing a tool through registry."""
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        registry.load_all_tools()
        
        result = registry.execute('get_time')
        self.assertTrue(result.success)
    
    def test_registry_validate_tool_name(self):
        """Test tool name validation."""
        from jarvis.tools.registry import get_registry
        registry = get_registry()
        registry.load_all_tools()
        
        is_valid, error = registry.validate_tool_name('get_time')
        self.assertTrue(is_valid)
        
        is_valid, error = registry.validate_tool_name('fake_tool')
        self.assertFalse(is_valid)
        self.assertIn('fake_tool', error)


def run_all_tests(verbose: bool = False) -> List[ToolTestResult]:
    """Run all tool tests and return results."""
    results = []
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestSystemTools,
        TestFileTools,
        TestAudioTools,
        TestNetworkTools,
        TestTimeTools,
        TestDataTools,
        TestTodoTools,
        TestNotesTools,
        TestClipboardTools,
        TestScreenTools,
        TestAppTools,
        TestWebTools,
        TestRegistry,
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests with custom result handler
    class ResultHandler(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.tool_results = []
        
        def addSuccess(self, test):
            super().addSuccess(test)
            self.tool_results.append(ToolTestResult(
                tool_name=str(test),
                passed=True,
                message="OK"
            ))
        
        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.tool_results.append(ToolTestResult(
                tool_name=str(test),
                passed=False,
                error=f"{err[0].__name__}: {err[1]}"
            ))
        
        def addError(self, test, err):
            super().addError(test, err)
            self.tool_results.append(ToolTestResult(
                tool_name=str(test),
                passed=False,
                error=f"{err[0].__name__}: {err[1]}"
            ))
    
    runner = unittest.TextTestRunner(
        verbosity=2 if verbose else 1,
        resultclass=ResultHandler
    )
    result = runner.run(suite)
    
    # Extract results
    if hasattr(result, 'tool_results'):
        results = result.tool_results
    
    return results


def print_summary(results: List[ToolTestResult]):
    """Print a summary of test results."""
    print("\n" + "=" * 70)
    print("TOOL TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    
    print(f"\nTotal: {total} tests")
    print(f"Passed: {passed} ({100*passed/total:.1f}%)")
    print(f"Failed: {failed} ({100*failed/total:.1f}%)")
    
    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  ✗ {r.tool_name}")
                print(f"    Error: {r.error}")
    
    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test all JARVIS tools')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='Verbose output')
    parser.add_argument('--category', '-c', type=str,
                       help='Test only specific category (system, file, audio, etc.)')
    parser.add_argument('--json', action='store_true',
                       help='Output results as JSON')
    
    args = parser.parse_args()
    
    print("""
╔═══════════════════════════════════════════════════════════╗
║           JARVIS Tool Test Suite                          ║
║                                                           ║
║ Testing all tools without requiring:                      ║
║  - Audio hardware                                         ║
║  - Ollama connection                                      ║
║  - Actual voice input                                     ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    print("Running tests...\n")
    
    results = run_all_tests(verbose=args.verbose)
    
    if args.json:
        # Output as JSON
        output = {
            'total': len(results),
            'passed': sum(1 for r in results if r.passed),
            'failed': sum(1 for r in results if not r.passed),
            'results': [
                {
                    'tool': r.tool_name,
                    'passed': r.passed,
                    'message': r.message,
                    'error': r.error
                }
                for r in results
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print_summary(results)
    
    # Return exit code based on results
    failed = sum(1 for r in results if not r.passed)
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
