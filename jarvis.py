#!/usr/bin/env python3
"""
JARVIS Entry Point

This is a minimal entry point that delegates to the new orchestrator-based architecture.
All main loop logic has been migrated to jarvis.core.orchestrator.

Run: python jarvis.py
"""

import sys
import os

# Add workspace to path if needed
workspace_dir = os.path.dirname(os.path.abspath(__file__))
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from jarvis.core.orchestrator import run_orchestrator
from jarvis.config.config import get_config


def main():
    """Main entry point."""
    print("Starting JARVIS...")
    
    # Load configuration
    config = get_config()
    
    # Run the orchestrator (blocks until shutdown)
    run_orchestrator(config)


if __name__ == "__main__":
    main()
