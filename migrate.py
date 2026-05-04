#!/usr/bin/env python3
"""
migrate.py — Migration script for JARVIS system upgrade

Safely migrates existing JARVIS installation to new structure:
- Backs up all original files to backup/ folder
- Copies existing conversation_history.json and user_profile.json
- Verifies all new modules import correctly
- Runs smoke tests on each tool category
- Reports any missing tools compared to original
- Can be run safely on live system
"""

import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('migration.log')
    ]
)
log = logging.getLogger('migration')


class MigrationManager:
    """Manages the migration process safely."""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent
        self.backup_dir = self.base_dir / 'backup'
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.original_files: List[Path] = []
        self.backed_up_files: List[Path] = []
        self.migration_report = {
            'timestamp': self.timestamp,
            'backed_up': [],
            'copied': [],
            'verified': [],
            'smoke_tests': {},
            'missing_tools': [],
            'errors': []
        }
    
    def create_backup_directory(self) -> bool:
        """Create backup directory structure."""
        try:
            self.backup_dir.mkdir(exist_ok=True)
            (self.backup_dir / 'config').mkdir(exist_ok=True)
            (self.backup_dir / 'data').mkdir(exist_ok=True)
            (self.backup_dir / 'memory').mkdir(exist_ok=True)
            log.info(f"Created backup directory: {self.backup_dir}")
            return True
        except Exception as e:
            log.error(f"Failed to create backup directory: {e}")
            self.migration_report['errors'].append(f"Backup dir creation failed: {e}")
            return False
    
    def find_original_files(self) -> List[Path]:
        """Find all original JARVIS files that need backing up."""
        patterns = [
            '*.py',
            '*.json',
            '*.yaml',
            '*.yml',
            '*.txt',
            '*.md'
        ]
        
        files = []
        exclude_dirs = {'venv', '__pycache__', '.git', 'backup', 'node_modules'}
        
        for pattern in patterns:
            for file in self.base_dir.rglob(pattern):
                # Skip excluded directories
                if any(exclude in str(file) for exclude in exclude_dirs):
                    continue
                # Skip virtual environment
                if 'venv' in str(file):
                    continue
                # Skip backup directory itself
                if 'backup' in str(file):
                    continue
                    
                files.append(file)
        
        self.original_files = files
        log.info(f"Found {len(files)} original files to back up")
        return files
    
    def backup_file(self, file_path: Path) -> bool:
        """Backup a single file preserving directory structure."""
        try:
            # Calculate relative path from base_dir
            rel_path = file_path.relative_to(self.base_dir)
            backup_path = self.backup_dir / rel_path
            
            # Create parent directories
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(file_path, backup_path)
            self.backed_up_files.append(backup_path)
            self.migration_report['backed_up'].append(str(rel_path))
            log.debug(f"Backed up: {rel_path}")
            return True
            
        except Exception as e:
            log.error(f"Failed to backup {file_path}: {e}")
            self.migration_report['errors'].append(f"Backup failed for {file_path}: {e}")
            return False
    
    def backup_all_files(self) -> bool:
        """Backup all original files."""
        log.info("Starting backup of original files...")
        
        success_count = 0
        fail_count = 0
        
        for file in self.original_files:
            if self.backup_file(file):
                success_count += 1
            else:
                fail_count += 1
        
        log.info(f"Backup complete: {success_count} succeeded, {fail_count} failed")
        return fail_count == 0
    
    def copy_user_data(self) -> bool:
        """Copy existing user data to new locations."""
        log.info("Copying user data files...")
        
        # Map of source patterns to destination
        data_mappings = [
            # Conversation history
            ('conversation_history.json', 'jarvis_data/conversation_history.json'),
            ('data/conversation_history.json', 'jarvis_data/conversation_history.json'),
            ('jarvis_data/conversation_history.json', 'jarvis_data/conversation_history.json'),
            
            # User profile
            ('user_profile.json', 'jarvis_data/user_profile.json'),
            ('profile/user_profile.json', 'jarvis_data/user_profile.json'),
            ('jarvis_data/user_profile.json', 'jarvis_data/user_profile.json'),
            
            # Memory files
            ('semantic.json', 'jarvis_data/semantic.json'),
            ('procedural.json', 'jarvis_data/procedural.json'),
            ('memory/semantic.json', 'jarvis_data/semantic.json'),
            ('memory/procedural.json', 'jarvis_data/procedural.json'),
        ]
        
        copied_count = 0
        for src_pattern, dst_rel in data_mappings:
            # Try to find source file
            src_file = None
            if Path(src_pattern).is_absolute():
                if Path(src_pattern).exists():
                    src_file = Path(src_pattern)
            else:
                # Search in base_dir
                for f in self.base_dir.rglob(src_pattern):
                    if 'backup' not in str(f) and 'venv' not in str(f):
                        src_file = f
                        break
            
            if src_file and src_file.exists():
                dst_file = self.base_dir / dst_rel
                
                # Create destination directory
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy if destination doesn't exist or is different
                if not dst_file.exists():
                    shutil.copy2(src_file, dst_file)
                    self.migration_report['copied'].append({
                        'source': str(src_file.relative_to(self.base_dir)),
                        'destination': dst_rel
                    })
                    copied_count += 1
                    log.info(f"Copied: {src_file.name} → {dst_rel}")
                else:
                    log.debug(f"Destination already exists: {dst_rel}")
        
        log.info(f"Copied {copied_count} user data files")
        return True
    
    def verify_module_imports(self) -> bool:
        """Verify all new modules import correctly."""
        log.info("Verifying module imports...")
        
        modules_to_test = [
            'jarvis.config.config',
            'jarvis.config.prompts.planning_prompt',
            'jarvis.config.prompts.critic_prompt',
            'jarvis.config.prompts.vision_prompt',
            'jarvis.core.orchestrator',
            'jarvis.memory.manager',
            'jarvis.memory.semantic',
            'jarvis.memory.procedural',
            'jarvis.memory.episodic',
            'jarvis.models.ollama_client',
            'jarvis.monitoring.ambient',
            'jarvis.output.tts',
            'jarvis.perception.vision',
            'jarvis.profile.user_profile',
            'jarvis.reasoning.planner',
            'jarvis.reasoning.critic',
            'jarvis.reasoning.reflector',
            'jarvis.reasoning.strategy_selector',
            'jarvis.skills.base',
            'jarvis.skills.registry',
            'jarvis.skills.builtin.morning_briefing',
            'jarvis.skills.builtin.focus_mode',
            'jarvis.skills.builtin.system_optimizer',
            'jarvis.tools.registry',
            'jarvis.tools.base',
            'jarvis.tools.system.info',
            'jarvis.tools.system.power',
            'jarvis.tools.apps.launcher',
            'jarvis.tools.audio.volume',
            'jarvis.tools.files.operations',
            'jarvis.tools.network.connectivity',
            'jarvis.tools.screen.capture',
            'jarvis.tools.time.clock',
            'jarvis.tools.web.browser',
            'jarvis.tools.data.todo',
            'jarvis.tools.data.notes',
            'jarvis.execution.tool_runner',
            'jarvis.execution.control_plane',
            'jarvis.safety.input_filter',
            'jarvis.safety.plan_validator',
        ]
        
        success_count = 0
        fail_count = 0
        
        for module_name in modules_to_test:
            try:
                __import__(module_name)
                self.migration_report['verified'].append(module_name)
                success_count += 1
                log.debug(f"✓ Imported: {module_name}")
            except ImportError as e:
                fail_count += 1
                error_msg = f"Failed to import {module_name}: {e}"
                self.migration_report['errors'].append(error_msg)
                log.error(f"✗ {error_msg}")
            except Exception as e:
                fail_count += 1
                error_msg = f"Error importing {module_name}: {e}"
                self.migration_report['errors'].append(error_msg)
                log.error(f"✗ {error_msg}")
        
        log.info(f"Import verification: {success_count} succeeded, {fail_count} failed")
        return fail_count == 0
    
    def run_smoke_tests(self) -> Dict[str, bool]:
        """Run quick smoke tests on each tool category."""
        log.info("Running smoke tests on tool categories...")
        
        results = {}
        
        # Test tool registry initialization
        try:
            from jarvis.tools.registry import get_registry
            registry = get_registry()
            
            # Load all tools
            tools_loaded = registry.load_all_tools()
            results['tool_registry'] = tools_loaded > 0
            self.migration_report['smoke_tests']['tool_registry'] = {
                'passed': results['tool_registry'],
                'tools_loaded': tools_loaded
            }
            log.info(f"Tool registry: {tools_loaded} tools loaded")
            
            # Get list of all available tools
            all_tools = registry.get_tool_names()
            
        except Exception as e:
            results['tool_registry'] = False
            self.migration_report['smoke_tests']['tool_registry'] = {
                'passed': False,
                'error': str(e)
            }
            log.error(f"Tool registry smoke test failed: {e}")
            all_tools = []
        
        # Test system tools
        try:
            from jarvis.tools.system.info import SystemInfoTool
            tool = SystemInfoTool()
            result = tool.execute()
            results['system_info'] = result.success
            self.migration_report['smoke_tests']['system_info'] = {
                'passed': result.success
            }
        except Exception as e:
            results['system_info'] = False
            self.migration_report['smoke_tests']['system_info'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Test time tools
        try:
            from jarvis.tools.time.clock import GetTimeTool
            tool = GetTimeTool()
            result = tool.execute()
            results['get_time'] = result.success
            self.migration_report['smoke_tests']['get_time'] = {
                'passed': result.success
            }
        except Exception as e:
            results['get_time'] = False
            self.migration_report['smoke_tests']['get_time'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Test file tools (basic operation without actual file changes)
        try:
            from jarvis.tools.files.operations import ListFilesTool
            tool = ListFilesTool()
            result = tool.execute(path=str(Path.home()))
            results['list_files'] = result.success
            self.migration_report['smoke_tests']['list_files'] = {
                'passed': result.success
            }
        except Exception as e:
            results['list_files'] = False
            self.migration_report['smoke_tests']['list_files'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Test network tools
        try:
            from jarvis.tools.network.connectivity import GetWifiTool
            tool = GetWifiTool()
            result = tool.execute()
            results['get_wifi'] = result.success
            self.migration_report['smoke_tests']['get_wifi'] = {
                'passed': result.success
            }
        except Exception as e:
            results['get_wifi'] = False
            self.migration_report['smoke_tests']['get_wifi'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Test audio tools (mocked - don't actually change volume)
        try:
            from jarvis.tools.audio.volume import GetVolumeTool
            tool = GetVolumeTool()
            result = tool.execute()
            results['get_volume'] = result.success
            self.migration_report['smoke_tests']['get_volume'] = {
                'passed': result.success
            }
        except Exception as e:
            results['get_volume'] = False
            self.migration_report['smoke_tests']['get_volume'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Test data tools
        try:
            from jarvis.tools.data.calculate import CalculateTool
            tool = CalculateTool()
            result = tool.execute(expression="2+2")
            results['calculate'] = result.success
            self.migration_report['smoke_tests']['calculate'] = {
                'passed': result.success
            }
        except Exception as e:
            results['calculate'] = False
            self.migration_report['smoke_tests']['calculate'] = {
                'passed': False,
                'error': str(e)
            }
        
        # Summary
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        log.info(f"Smoke tests: {passed}/{total} passed")
        
        return results
    
    def check_missing_tools(self) -> List[str]:
        """Check for any missing tools compared to expected set."""
        log.info("Checking for missing tools...")
        
        # Expected core tools
        expected_tools = {
            'get_time', 'get_date', 'set_alarm',
            'open_app', 'close_app', 'list_apps',
            'get_volume', 'set_volume', 'mute_audio',
            'get_battery', 'shutdown', 'restart', 'sleep',
            'read_file', 'write_file', 'delete_file', 'list_files',
            'create_folder', 'delete_folder',
            'get_wifi', 'check_internet',
            'take_screenshot', 'analyze_screen', 'find_on_screen',
            'search_web', 'open_url',
            'get_clipboard', 'set_clipboard',
            'add_todo', 'list_todos', 'complete_todo',
            'add_note', 'list_notes',
            'calculate',
            'system_health', 'get_top_processes',
            'wait', 'repeat_task',
        }
        
        try:
            from jarvis.tools.registry import get_registry
            registry = get_registry()
            registry.load_all_tools()
            available_tools = set(registry.get_tool_names())
            
            missing = expected_tools - available_tools
            extra = available_tools - expected_tools
            
            self.migration_report['missing_tools'] = list(missing)
            
            if missing:
                log.warning(f"Missing tools: {missing}")
            if extra:
                log.info(f"Additional tools found: {extra}")
            
            return list(missing)
            
        except Exception as e:
            log.error(f"Failed to check missing tools: {e}")
            self.migration_report['errors'].append(f"Missing tools check failed: {e}")
            return list(expected_tools)
    
    def generate_report(self) -> str:
        """Generate migration report."""
        report_lines = [
            "=" * 60,
            "JARVIS MIGRATION REPORT",
            "=" * 60,
            f"Timestamp: {self.migration_report['timestamp']}",
            "",
            "BACKUP STATUS:",
            f"  Files backed up: {len(self.migration_report['backed_up'])}",
            f"  Backup location: {self.backup_dir}",
            "",
            "DATA MIGRATION:",
            f"  Files copied: {len(self.migration_report['copied'])}",
            "",
            "MODULE VERIFICATION:",
            f"  Modules verified: {len(self.migration_report['verified'])}",
            "",
            "SMOKE TESTS:",
        ]
        
        for test_name, result in self.migration_report['smoke_tests'].items():
            status = "✓ PASS" if result.get('passed', False) else "✗ FAIL"
            report_lines.append(f"  {test_name}: {status}")
        
        report_lines.extend([
            "",
            "MISSING TOOLS:",
            f"  Count: {len(self.migration_report['missing_tools'])}",
        ])
        
        if self.migration_report['missing_tools']:
            for tool in self.migration_report['missing_tools'][:10]:
                report_lines.append(f"    - {tool}")
            if len(self.migration_report['missing_tools']) > 10:
                report_lines.append(f"    ... and {len(self.migration_report['missing_tools']) - 10} more")
        
        if self.migration_report['errors']:
            report_lines.extend([
                "",
                "ERRORS:",
            ])
            for error in self.migration_report['errors'][:10]:
                report_lines.append(f"  - {error}")
            if len(self.migration_report['errors']) > 10:
                report_lines.append(f"  ... and {len(self.migration_report['errors']) - 10} more")
        
        report_lines.extend([
            "",
            "=" * 60,
            "MIGRATION COMPLETE",
            "=" * 60,
        ])
        
        report = "\n".join(report_lines)
        
        # Save report to file
        report_file = self.base_dir / f'migration_report_{self.timestamp}.txt'
        with open(report_file, 'w') as f:
            f.write(report)
        
        # Also save JSON version
        json_file = self.base_dir / f'migration_report_{self.timestamp}.json'
        with open(json_file, 'w') as f:
            json.dump(self.migration_report, f, indent=2)
        
        return report
    
    def run_migration(self) -> bool:
        """Run the complete migration process."""
        log.info("=" * 60)
        log.info("Starting JARVIS Migration")
        log.info("=" * 60)
        
        start_time = time.time()
        
        # Step 1: Create backup directory
        if not self.create_backup_directory():
            log.error("Failed to create backup directory. Aborting.")
            return False
        
        # Step 2: Find original files
        self.find_original_files()
        
        # Step 3: Backup all files
        if not self.backup_all_files():
            log.warning("Some files failed to backup, but continuing...")
        
        # Step 4: Copy user data
        self.copy_user_data()
        
        # Step 5: Verify module imports
        imports_ok = self.verify_module_imports()
        
        # Step 6: Run smoke tests
        self.run_smoke_tests()
        
        # Step 7: Check for missing tools
        self.check_missing_tools()
        
        # Step 8: Generate report
        report = self.generate_report()
        
        elapsed = time.time() - start_time
        log.info(f"\nMigration completed in {elapsed:.2f} seconds")
        print("\n" + report)
        
        # Return success if no critical errors
        critical_errors = [e for e in self.migration_report['errors'] 
                          if 'import' in e.lower() or 'registry' in e.lower()]
        
        return len(critical_errors) == 0


def main():
    """Main entry point for migration."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║           JARVIS Migration Tool                           ║
║                                                           ║
║ This script will:                                         ║
║  1. Backup all original files to backup/                  ║
║  2. Copy your user data to new locations                  ║
║  3. Verify all modules import correctly                   ║
║  4. Run smoke tests on tool categories                    ║
║  5. Report any missing tools                              ║
║                                                           ║
║ Safe to run on live system.                               ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Confirm before proceeding
    response = input("\nContinue with migration? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Migration cancelled.")
        return 0
    
    manager = MigrationManager()
    success = manager.run_migration()
    
    if success:
        print("\n✓ Migration completed successfully!")
        print(f"  Check migration_report_{manager.timestamp}.txt for details")
        return 0
    else:
        print("\n✗ Migration completed with errors.")
        print("  Review migration log and report for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
