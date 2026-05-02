#!/usr/bin/env python3
"""
JARVIS - Autonomous Windows Desktop AI Agent

Main entry point for the JARVIS system.
Initializes and runs the orchestrator.

Usage:
    python jarvis.py [--config <config_file>] [--mode <chat|agent>]
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to path correctly
current_file = Path(__file__).resolve()
project_root = current_file.parent  # This is the workspace root directory

# Insert project root so we can import jarvis as a package
sys.path.insert(0, str(project_root))

from jarvis.core.orchestrator import Orchestrator, run_orchestrator
from jarvis.config.config import get_config


def setup_logging(config: dict) -> None:
    """
    Configure logging based on config.
    
    Args:
        config: Configuration dict
    """
    log_level = getattr(logging, config.get('log_level', 'INFO').upper())
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Create logs directory
    log_dir = config.get('log_dir', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(log_dir, 'jarvis.log'))
        ]
    )
    
    # Set third-party loggers to WARNING
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='JARVIS - Autonomous Windows Desktop AI Agent'
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration file (default: config/config.yaml)'
    )
    
    parser.add_argument(
        '--mode', '-m',
        type=str,
        choices=['chat', 'agent'],
        default='agent',
        help='Operating mode (default: agent)'
    )
    
    parser.add_argument(
        '--voice', '-v',
        action='store_true',
        help='Enable voice interaction mode'
    )
    
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code
    """
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
    logger.info("=" * 60)
    logger.info("JARVIS - Autonomous Windows Desktop AI Agent")
    logger.info("=" * 60)
    logger.info(f"Starting in {args.mode} mode")
    logger.info(f"Voice enabled: {args.voice}")
    logger.info(f"Config: {config.get('data_dir', 'default')}")
    
    try:
        # Run the orchestrator
        run_orchestrator(config)
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
