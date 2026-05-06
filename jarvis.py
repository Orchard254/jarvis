#!/usr/bin/env python3
"""
JARVIS - Autonomous Desktop AI Agent (New Capability-Based Architecture)

Main entry point using the new 30-tool capability architecture.
This version replaces the old tool-based system with a clean capability-driven design.

Usage:
    python jarvis.py [--config <config_file>] [--mode <chat|agent>]
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
from jarvis.models.model_adapter import (
    get_reasoning_model,
    get_vision_model,
    GPTOSSAdapter,
    Gemma3Adapter,
    initialize_all_adapters
)
import logging

logger = logging.getLogger(__name__)


class ModelManager:
    """Manager for GPT-OSS 120B and Gemma 3 27B models with health checking."""
    
    def __init__(self):
        """Initialize model adapters with health status tracking."""
        self.reasoning_model: Optional[GPTOSSAdapter] = None
        self.vision_model: Optional[Gemma3Adapter] = None
        self.reasoning_available = False
        self.vision_available = False
        self._initialize_models()
    
    def _initialize_models(self):
        """Attempt to initialize both model adapters."""
        try:
            logger.info("Initializing GPT-OSS 120B adapter...")
            self.reasoning_model = get_reasoning_model()
            self.reasoning_available = True
            logger.info(f"✓ GPT-OSS 120B ready: {self.reasoning_model.model_name}")
        except Exception as e:
            logger.warning(f"✗ GPT-OSS 120B initialization failed: {e}")
            self.reasoning_available = False
        
        try:
            logger.info("Initializing Gemma 3 27B adapter...")
            self.vision_model = get_vision_model()
            self.vision_available = True
            logger.info(f"✓ Gemma 3 27B ready: {self.vision_model.model_name}")
        except Exception as e:
            logger.warning(f"✗ Gemma 3 27B initialization failed: {e}")
            self.vision_available = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get model availability status."""
        return {
            "reasoning_model": {
                "available": self.reasoning_available,
                "model_name": self.reasoning_model.model_name if self.reasoning_model else None
            },
            "vision_model": {
                "available": self.vision_available,
                "model_name": self.vision_model.model_name if self.vision_model else None
            }
        }
    
    def is_fully_operational(self) -> bool:
        """Check if both models are available."""
        return self.reasoning_available and self.vision_available


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
        """Initialize JARVIS with capability registry and real model adapters."""
        self.config = config
        self.test_mode = test_mode
        self.logger = logging.getLogger(__name__)
        
        # Initialize models with health checking
        if test_mode:
            self.logger.info("Running in TEST MODE - models will use fallback behavior")
            self.model_manager = ModelManager()
        else:
            self.logger.info("Loading AI models (GPT-OSS 120B + Gemma 3 27B)...")
            self.model_manager = ModelManager()
            
            # Report model status
            status = self.model_manager.get_status()
            if status["reasoning_model"]["available"]:
                self.logger.info(f"✓ Reasoning model ready: {status['reasoning_model']['model_name']}")
            else:
                self.logger.warning("✗ Reasoning model unavailable - will use fallback")
                
            if status["vision_model"]["available"]:
                self.logger.info(f"✓ Vision model ready: {status['vision_model']['model_name']}")
            else:
                self.logger.warning("✗ Vision model unavailable - will use fallback")
        
        # Initialize capability registry with model adapters
        # The registry uses the adapters directly from the model_adapter module
        self.registry = initialize_registry(
            reasoning_model=self.model_manager.reasoning_model,
            vision_model=self.model_manager.vision_model
        )
        
        caps_count = len(self.registry.list_capabilities())
        self.logger.info(f"Initialized {caps_count} capabilities")
        
        # Show operational status
        if self.model_manager.is_fully_operational():
            self.logger.info("✓ JARVIS is fully operational with both models")
        else:
            self.logger.warning("⚠ JARVIS running with limited model availability")
        
    def process_command(self, command: str) -> Dict[str, Any]:
        """Process a user command through the capability system."""
        self.logger.info(f"Processing command: {command}")
        
        try:
            # Step 1: Use intent_router to classify the command
            intent_result = self.registry.execute(
                "intent_router",
                user_input=command
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
                    # For tool_dispatcher, pass parameters as keyword args (registry passes **kwargs)
                    step_result = self.registry.execute(
                        "tool_dispatcher",
                        tool_name=step.get('tool'),
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
                # For tool_dispatcher, pass parameters as keyword args (registry passes **kwargs)
                result = self.registry.execute(
                    "tool_dispatcher",
                    tool_name=intent,
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
        """Show available capabilities and model status."""
        print("\n--- Available Capabilities ---")
        caps = self.registry.list_capabilities()
        
        # Group by category - handle both dict and string formats
        categories = {}
        for cap in caps:
            # Handle dict format from registry
            if isinstance(cap, dict):
                cap_name = cap.get('name', 'unknown')
                category = cap.get('category', 'other')
            else:
                # Handle string format (legacy)
                cap_name = str(cap)
                parts = cap_name.split('.')
                category = parts[0] if len(parts) > 1 else 'other'
            
            if category not in categories:
                categories[category] = []
            categories[category].append(cap_name)
        
        for category, cap_list in sorted(categories.items()):
            print(f"\n{category.upper()}:")
            for cap in cap_list:
                print(f"  - {cap}")
        
        # Show model status
        print("\n--- Model Status ---")
        status = self.model_manager.get_status()
        reasoning_status = "✓" if status["reasoning_model"]["available"] else "✗"
        vision_status = "✓" if status["vision_model"]["available"] else "✗"
        print(f"  {reasoning_status} Reasoning (GPT-OSS 120B): {status['reasoning_model']['model_name'] or 'unavailable'}")
        print(f"  {vision_status} Vision (Gemma 3 27B): {status['vision_model']['model_name'] or 'unavailable'}")
        
        print("\nUsage examples:")
        print("  - 'What's my CPU usage?' → system_info")
        print("  - 'Take a screenshot' → screen_capture")
        print("  - 'Search for AI news' → web_search")
        print("  - 'List all processes' → process_manager")
        print("  - 'Plan a complex task' → Uses GPT-OSS 120B for planning")
        print("  - 'Classify this text' → Uses Gemma 3 27B for classification")


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
    
    # Enhanced startup banner with model status
    print("\n" + "="*70)
    print("  🤖 JARVIS - Capability-Based AI Agent v2.0")
    print("="*70)
    print(f"\n📋 Configuration:")
    print(f"   Mode: {args.mode}")
    print(f"   Test Mode: {'Yes' if args.test else 'No'}")
    print(f"   Debug: {'Yes' if args.debug else 'No'}")
    
    logger.info("="*70)
    logger.info("JARVIS - Capability-Based AI Agent")
    logger.info("="*70)
    logger.info(f"Starting in {args.mode} mode")
    logger.info(f"Test mode: {args.test}")
    
    # Pre-initialize models to show status before agent creation
    print(f"\n🔧 Initializing Models...")
    try:
        from jarvis.models.model_adapter import get_reasoning_model, get_vision_model
        
        # Try to initialize reasoning model (GPT-OSS 120B)
        try:
            reasoning_model = get_reasoning_model()
            print(f"   ✓ GPT-OSS 120B: {reasoning_model.model_name}")
        except Exception as e:
            print(f"   ⚠ GPT-OSS 120B: Unavailable ({str(e)[:50]})")
        
        # Try to initialize vision model (Gemma 3 27B)
        try:
            vision_model = get_vision_model()
            print(f"   ✓ Gemma 3 27B: {vision_model.model_name}")
        except Exception as e:
            print(f"   ⚠ Gemma 3 27B: Unavailable ({str(e)[:50]})")
            
    except Exception as e:
        print(f"   ⚠ Model initialization warning: {e}")
    
    print(f"\n📦 Loading Capabilities...")
    
    try:
        # Create and run agent
        agent = JARVISAgent(config, test_mode=args.test)
        
        # Show final status
        status = agent.model_manager.get_status()
        is_fully_operational = agent.model_manager.is_fully_operational()
        
        print(f"\n{'='*70}")
        if is_fully_operational:
            print("  ✅ STATUS: Fully Operational")
        else:
            print("  ⚠️  STATUS: Limited Mode (some models unavailable)")
        print(f"{'='*70}")
        print(f"   Capabilities Loaded: {len(agent.registry.list_capabilities())}")
        print(f"   Reasoning Model: {'Active' if status['reasoning_model']['available'] else 'Inactive'}")
        print(f"   Vision Model: {'Active' if status['vision_model']['available'] else 'Inactive'}")
        print(f"{'='*70}\n")
        
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
