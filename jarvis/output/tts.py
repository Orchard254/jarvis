"""
TTS (Text-to-Speech) Output Module

Provides a simple interface for text-to-speech output.
Delegates to the existing TTS implementation in the root directory.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def speak(text: str) -> None:
    """
    Speak text using TTS.
    
    This is a wrapper that delegates to the main TTS implementation.
    For now, it just prints to stdout as a fallback.
    
    Args:
        text: Text to speak
    """
    try:
        # Try to import the main TTS module from root
        import sys
        from pathlib import Path
        
        # Add parent directory to path to find root tts module
        root_path = Path(__file__).parent.parent.parent
        if str(root_path) not in sys.path:
            sys.path.insert(0, str(root_path))
        
        # Import the main TTS speak function
        from tts import speak as root_speak
        root_speak(text)
        
    except ImportError as e:
        logger.warning(f"Root TTS module not available: {e}")
        # Fallback: just print
        print(f"JARVIS: {text}")
        
    except Exception as e:
        logger.error(f"TTS error: {e}")
        # Fallback: just print
        print(f"JARVIS: {text}")


class TTSManager:
    """
    TTS Manager for handling text-to-speech output.
    
    Provides configuration and state management for TTS.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize TTS manager.
        
        Args:
            config: Configuration dict with TTS settings
        """
        self.config = config or {}
        self.enabled = self.config.get('tts_enabled', True)
        self.voice = self.config.get('tts_voice', 'default')
        self.speed = self.config.get('tts_speed', 1.0)
        
        logger.info(f"TTS Manager initialized (enabled={self.enabled})")
    
    def speak(self, text: str) -> None:
        """
        Speak text using TTS.
        
        Args:
            text: Text to speak
        """
        if not self.enabled:
            logger.debug(f"TTS disabled, would speak: {text[:50]}...")
            return
            
        speak(text)
    
    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable TTS.
        
        Args:
            enabled: Whether TTS should be enabled
        """
        self.enabled = enabled
        logger.info(f"TTS {'enabled' if enabled else 'disabled'}")
    
    def set_voice(self, voice: str) -> None:
        """
        Set the TTS voice.
        
        Args:
            voice: Voice name
        """
        self.voice = voice
        logger.info(f"TTS voice set to: {voice}")
    
    def set_speed(self, speed: float) -> None:
        """
        Set the TTS speed.
        
        Args:
            speed: Speed multiplier (1.0 = normal)
        """
        self.speed = max(0.5, min(2.0, speed))
        logger.info(f"TTS speed set to: {self.speed}")
