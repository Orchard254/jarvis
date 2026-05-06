#!/usr/bin/env python3
"""
JARVIS - Autonomous Desktop AI Agent (New Capability-Based Architecture)

Main entry point using the new 30-tool capability architecture.
This version replaces the old tool-based system with a clean capability-driven design.

Usage:
    python jarvis_new.py [--config <config_file>] [--mode <chat|agent>]
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent
sys.path.insert(0, str(project_root))

from jarvis.capabilities.registry import initialize_registry, CapabilityRegistry
from jarvis.config.config import get_config


class ModelWrapper:
    """Wrapper for GPT-OSS 120B and Gemma 3 27B models."""
    
    def __init__(self, reasoning_model=None, vision_model=None):
        """Initialize model wrappers."""
        self.reasoning_model = reasoning_model  # GPT-OSS 120B
        self.vision_model = vision_model  # Gemma 3 27B
        
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using reasoning model."""
        if self.reasoning_model:
            return self.reasoning_model.generate(prompt, **kwargs)
        # Fallback: echo for testing
        return f"[Reasoning Model Response]: {prompt[:100]}..."
        
    def analyze_image(self, image_data: bytes, prompt: str) -> str:
        """Analyze image using vision model."""
        if self.vision_model:
            return self.vision_model.analyze(image_data, prompt)
        # Fallback: echo for testing
        return f"[Vision Model Response]: Analyzing image with prompt: {prompt}"


def setup_logging(config: dict) -> None:
    """Configure logging based on config."""
    log_level = getattr(logging, config.get('log_level', 'INFO').upper())
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    log_dir = config.get('log_dir', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(log_dir, 'jarvis.log'), encoding='utf-8')
        ]
    )
    
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='JARVIS - Autonomous Desktop AI Agent (Capability-Based)'
    )
    
    parser.add_argument('--config', '-c', type=str, default=None,
                        help='Path to configuration file')
    parser.add_argument('--mode', '-m', type=str, choices=['chat', 'agent'],
                        default='agent', help='Operating mode')
    parser.add_argument('--voice', '-v', action='store_true',
                        help='Enable voice interaction mode')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Run in test mode (no actual AI models)')
    
    return parser.parse_args()


class JARVISAgent:
    """Main JARVIS agent using capability-based architecture."""
    
    def __init__(self, config: Dict[str, Any], test_mode: bool = False):
        """Initialize JARVIS with capability registry."""
        self.config = config
        self.test_mode = test_mode
        self.logger = logging.getLogger(__name__)
        
        # Initialize models (placeholder for actual model loading)
        if test_mode:
            self.logger.info("Running in TEST MODE - using mock models")
            self.models = ModelWrapper()
        else:
            self.logger.info("Loading AI models (GPT-OSS 120B + Gemma 3 27B)...")
            # TODO: Load actual models here
            # self.models = ModelWrapper(
            #     reasoning_model=load_gpt_oss_120b(),
            #     vision_model=load_gemma_3_27b()
            # )
            self.models = ModelWrapper()
        
        # Initialize capability registry with models
        self.registry = initialize_registry(
            reasoning_model=self.models.reasoning_model,
            vision_model=self.models.vision_model
        )
        
        self.logger.info(f"Initialized {len(self.registry.list_capabilities())} capabilities")
        
    def process_command(self, command: str) -> Dict[str, Any]:
        """Process a user command through the capability system."""
        self.logger.info(f"Processing command: {command}")
        
        try:
            # Step 1: Use intent_router to classify the command
            intent_result = self.registry.execute(
                "intent_router",
                input_text=command
            )
            
            if not intent_result.get('success'):
                return {
                    'success': False,
                    'error': f"Intent routing failed: {intent_result.get('error')}",
                    'output': None
                }
            
            intent = intent_result.get('output', {}).get('intent', 'unknown')
            confidence = intent_result.get('output', {}).get('confidence', 0)
            
            self.logger.info(f"Detected intent: {intent} (confidence: {confidence})")
            
            # Step 2: If complex task, use task_planner
            if intent_result.get('output', {}).get('requires_planning', False):
                plan_result = self.registry.execute(
                    "task_planner",
                    goal=command,
                    context=intent_result.get('output', {})
                )
                
                if not plan_result.get('success'):
                    return plan_result
                
                steps = plan_result.get('output', {}).get('steps', [])
                self.logger.info(f"Generated {len(steps)} step plan")
                
                # Step 3: Execute each step via tool_dispatcher
                results = []
                for step in steps:
                    step_result = self.registry.execute(
                        "tool_dispatcher",
                        capability_name=step.get('tool'),
                        parameters=step.get('parameters', {})
                    )
                    results.append(step_result)
                    
                    if not step_result.get('success'):
                        return {
                            'success': False,
                            'error': f"Step failed: {step_result.get('error')}",
                            'output': results
                        }
                
                return {
                    'success': True,
                    'output': results,
                    'metadata': {'plan_executed': True, 'steps': len(steps)}
                }
            
            # Step 4: Simple task - execute directly via tool_dispatcher
            else:
                result = self.registry.execute(
                    "tool_dispatcher",
                    capability_name=intent,
                    parameters={'input_text': command}
                )
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error processing command: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'output': None
            }
    
    def run_interactive(self):
        """Run interactive mode."""
        print("\n" + "="*60)
        print("JARVIS - Capability-Based AI Agent")
        print("="*60)
        print(f"Mode: {self.config.get('mode', 'agent')}")
        print(f"Capabilities available: {len(self.registry.list_capabilities())}")
        print("Type 'quit' or 'exit' to stop\n")
        
        while True:
            try:
                user_input = input("\n🤖 JARVIS> ").strip()
                
                if not user_input:
                    continue
                    
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Shutting down JARVIS...")
                    break
                
                if user_input.lower() == 'help':
                    self._show_help()
                    continue
                
                # Process command
                result = self.process_command(user_input)
                
                if result.get('success'):
                    output = result.get('output')
                    if isinstance(output, dict):
                        import json
                        print(json.dumps(output, indent=2))
                    else:
                        print(f"✓ {output}")
                else:
                    print(f"✗ Error: {result.get('error')}")
                    
            except KeyboardInterrupt:
                print("\nInterrupted. Type 'quit' to exit.")
                continue
            except EOFError:
                break
    
    def _show_help(self):
        """Show available capabilities."""
        print("\n--- Available Capabilities ---")
        caps = self.registry.list_capabilities()
        
        # Group by category
        categories = {}
        for cap_name in caps:
            parts = cap_name.split('.')
            category = parts[0] if len(parts) > 1 else 'other'
            if category not in categories:
                categories[category] = []
            categories[category].append(cap_name)
        
        for category, cap_list in sorted(categories.items()):
            print(f"\n{category.upper()}:")
            for cap in cap_list:
                print(f"  - {cap}")
        
        print("\nUsage examples:")
        print("  - 'What's my CPU usage?' → system_info")
        print("  - 'Take a screenshot' → screen_capture")
        print("  - 'Search for AI news' → web_search")
        print("  - 'List all processes' → process_manager")


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Load configuration
    try:
        config = get_config(config_path=args.config)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        print("Using default configuration...")
        config = get_config()
    
    # Override config with command line args
    if args.debug:
        config['log_level'] = 'DEBUG'
    
    config['mode'] = args.mode
    config['voice_enabled'] = args.voice
    
    # Setup logging
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("JARVIS - Capability-Based AI Agent")
    logger.info("="*60)
    logger.info(f"Starting in {args.mode} mode")
    logger.info(f"Test mode: {args.test}")
    
    try:
        # Create and run agent
        agent = JARVISAgent(config, test_mode=args.test)
        agent.run_interactive()
        return 0
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        return 0
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        print("\nCheck logs/jarvis.log for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
