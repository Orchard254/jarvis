"""
TTS (Text-to-Speech) Output Module

Provides text-to-speech output with multiple engine support:
- Kokoro: High-quality neural TTS (preferred)
- pyttsx3: Offline Windows SAPI5 fallback
- edge-tts: Microsoft Edge online TTS

Automatically falls back through engines if preferred is unavailable.
"""

import logging
from typing import Optional, Dict, Any
import threading

logger = logging.getLogger(__name__)


class TTSEngine:
    """Base TTS engine interface."""
    
    def speak(self, text: str) -> bool:
        """
        Speak text.
        
        Args:
            text: Text to speak
            
        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError
    
    def set_voice(self, voice: str) -> None:
        """Set the voice."""
        pass
    
    def set_speed(self, speed: float) -> None:
        """Set speech speed (0.5-2.0)."""
        pass


class KokoroEngine(TTSEngine):
    """Kokoro neural TTS engine - high quality, runs locally on CPU."""
    
    def __init__(self, voice: str = "af_bella", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._model = None
        self._initialized = False
        
        try:
            # Try to import kokoro
            from kokoro import KModel, KPipeline
            self._model = KModel()
            self._pipeline = KPipeline(lang_code='a')  # English
            self._initialized = True
            logger.info("Kokoro TTS engine initialized successfully")
        except ImportError:
            logger.warning("Kokoro not installed - install with: pip install kokoro")
        except Exception as e:
            logger.warning(f"Kokoro initialization failed: {e}")
    
    def speak(self, text: str) -> bool:
        """Speak text using Kokoro."""
        if not self._initialized:
            return False
        
        try:
            import sounddevice as sd
            import numpy as np
            
            # Generate audio with Kokoro
            generator = self._pipeline(
                text, 
                voice=self.voice,
                speed=self.speed
            )
            
            for item in generator:
                # Handle different return formats from Kokoro
                if isinstance(item, tuple) and len(item) >= 2:
                    _, audio_data, _ = item
                    # Check if audio_data is already a numpy array or needs conversion
                    if hasattr(audio_data, 'numpy'):
                        audio_array = audio_data.numpy()
                    elif isinstance(audio_data, np.ndarray):
                        audio_array = audio_data
                    else:
                        # If it's a string or other format, skip this item
                        logger.debug(f"Skipping unexpected audio data type: {type(audio_data)}")
                        continue
                    
                    # Play audio
                    sd.play(audio_array, samplerate=24000)
                    sd.wait()
                else:
                    logger.debug(f"Unexpected generator item format: {type(item)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Kokoro TTS error: {e}")
            return False
    
    def set_voice(self, voice: str) -> None:
        self.voice = voice
    
    def set_speed(self, speed: float) -> None:
        self.speed = max(0.5, min(2.0, speed))


class Pyttsx3Engine(TTSEngine):
    """pyttsx3 offline TTS engine - uses Windows SAPI5."""
    
    def __init__(self, voice: str = "", speed: float = 1.0):
        self.voice_name = voice
        self.speed = speed
        self._engine = None
        self._initialized = False
        
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            
            # Configure voice
            if voice:
                voices = self._engine.getProperty('voices')
                for v in voices:
                    if voice.lower() in v.name.lower():
                        self._engine.setProperty('voice', v.id)
                        break
            
            # Set speed
            rate = self._engine.getProperty('rate')
            self._engine.setProperty('rate', int(rate * speed))
            
            self._initialized = True
            logger.info("pyttsx3 TTS engine initialized successfully")
            
        except ImportError:
            logger.warning("pyttsx3 not installed - install with: pip install pyttsx3")
        except Exception as e:
            logger.warning(f"pyttsx3 initialization failed: {e}")
    
    def speak(self, text: str) -> bool:
        """Speak text using pyttsx3."""
        if not self._initialized:
            return False
        
        try:
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except Exception as e:
            logger.error(f"pyttsx3 TTS error: {e}")
            return False
    
    def set_voice(self, voice: str) -> None:
        self.voice_name = voice
        if self._engine:
            voices = self._engine.getProperty('voices')
            for v in voices:
                if voice.lower() in v.name.lower():
                    self._engine.setProperty('voice', v.id)
                    break
    
    def set_speed(self, speed: float) -> None:
        self.speed = max(0.5, min(2.0, speed))
        if self._engine:
            rate = self._engine.getProperty('rate')
            base_rate = rate / self.speed  # Calculate base rate
            self._engine.setProperty('rate', int(base_rate * speed))


class EdgeTTSEngine(TTSEngine):
    """Edge TTS - Microsoft's online TTS service."""
    
    def __init__(self, voice: str = "en-US-JennyNeural", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._initialized = False
        
        try:
            import edge_tts
            # Validate the voice by checking if it's a valid format
            # Common valid voice formats: en-US-JennyNeural, en-GB-SoniaNeural, etc.
            if not voice or '-' not in voice:
                logger.warning(f"Invalid voice format '{voice}', using default: en-US-JennyNeural")
                self.voice = "en-US-JennyNeural"
            self._initialized = True
            logger.info("Edge TTS engine initialized successfully")
        except ImportError:
            logger.warning("edge-tts not installed - install with: pip install edge-tts")
    
    def speak(self, text: str) -> bool:
        """Speak text using Edge TTS."""
        if not self._initialized:
            return False
        
        try:
            import asyncio
            import edge_tts
            import pygame
            import os
            
            # Calculate rate parameter correctly
            rate_percent = int((self.speed - 1) * 100)
            rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"
            
            async def _speak():
                communicate = edge_tts.Communicate(text, self.voice, rate=rate_str)
                output_file = "temp_tts.mp3"
                await communicate.save(output_file)
                
                pygame.mixer.init()
                pygame.mixer.music.load(output_file)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                pygame.mixer.quit()
                
                os.remove(output_file)
            
            asyncio.run(_speak())
            return True
            
        except Exception as e:
            logger.error(f"Edge TTS error: {e}")
            return False
    
    def set_voice(self, voice: str) -> None:
        self.voice = voice
    
    def set_speed(self, speed: float) -> None:
        self.speed = max(0.5, min(2.0, speed))


# Global TTS manager instance
_tts_manager: Optional['TTSManager'] = None


class TTSManager:
    """
    TTS Manager with automatic engine fallback.
    
    Tries engines in order: Kokoro → Edge TTS → pyttsx3
    Uses first available engine.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize TTS manager.
        
        Args:
            config: Configuration dict with TTS settings
        """
        self.config = config or {}
        self.enabled = self.config.get('tts_enabled', True)
        self.preferred_engine = 'edge-tts'  # Force edge-tts only
        self.voice = self.config.get('tts_voice', 'en-US-JennyNeural')
        self.speed = self.config.get('tts_speed', 1.0)
        
        # Set default voice for Edge TTS
        if not self.voice or self.voice in ['af_bella', 'af_heart', 'af_nicole', 'af_sarah', 'af_sky', 'am_adam', 'am_michael']:
            self.voice = "en-US-JennyNeural"
        
        # Initialize engines
        self._engines: Dict[str, TTSEngine] = {}
        self._active_engine: Optional[TTSEngine] = None
        
        self._initialize_engines()
        
        logger.info(f"TTS Manager initialized (enabled={self.enabled}, engine={self._get_active_engine_name()})")
    
    def _initialize_engines(self) -> None:
        """Initialize all available TTS engines."""
        # Only initialize edge-tts engine
        engine_order = ['edge-tts']
        
        for engine_name in engine_order:
            try:
                if engine_name == 'edge-tts':
                    engine = EdgeTTSEngine(voice=self.voice, speed=self.speed)
                else:
                    continue
                
                if engine._initialized:
                    self._engines[engine_name] = engine
                    if self._active_engine is None:
                        self._active_engine = engine
                        logger.info(f"Using {engine_name} as active TTS engine")
                        
            except Exception as e:
                logger.debug(f"Failed to initialize {engine_name}: {e}")
        
        if not self._active_engine:
            logger.warning("No TTS engines available - speech output disabled")
    
    def _get_active_engine_name(self) -> str:
        """Get name of active engine."""
        if self._active_engine:
            for name, engine in self._engines.items():
                if engine is self._active_engine:
                    return name
        return "none"
    
    def speak(self, text: str) -> None:
        """
        Speak text using TTS.
        
        Args:
            text: Text to speak
        """
        # Skip empty or whitespace-only text
        if not text or not text.strip():
            return
        
        if not self.enabled:
            logger.debug(f"TTS disabled, would speak: {text[:50]}...")
            return
        
        if not self._active_engine:
            logger.debug("No TTS engine available")
            return
        
        # Run in background thread to avoid blocking
        def _speak_thread():
            self._active_engine.speak(text)
        
        thread = threading.Thread(target=_speak_thread, daemon=True)
        thread.start()
    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable TTS."""
        self.enabled = enabled
        logger.info(f"TTS {'enabled' if enabled else 'disabled'}")
    
    def set_voice(self, voice: str) -> None:
        """Set the TTS voice."""
        self.voice = voice
        if self._active_engine:
            self._active_engine.set_voice(voice)
        logger.info(f"TTS voice set to: {voice}")
    
    def set_speed(self, speed: float) -> None:
        """Set the TTS speed."""
        self.speed = max(0.5, min(2.0, speed))
        if self._active_engine:
            self._active_engine.set_speed(speed)
        logger.info(f"TTS speed set to: {self.speed}")
    
    def list_voices(self) -> list:
        """List available voices for active engine."""
        if isinstance(self._active_engine, Pyttsx3Engine) and self._active_engine._engine:
            voices = self._active_engine._engine.getProperty('voices')
            return [{'id': v.id, 'name': v.name, 'languages': v.languages} for v in voices]
        elif isinstance(self._active_engine, KokoroEngine):
            return [
                {'id': 'af_heart', 'name': 'Heart (Female)'},
                {'id': 'af_bella', 'name': 'Bella (Female)'},
                {'id': 'af_nicole', 'name': 'Nicole (Female)'},
                {'id': 'af_sarah', 'name': 'Sarah (Female)'},
                {'id': 'af_sky', 'name': 'Sky (Female)'},
                {'id': 'am_adam', 'name': 'Adam (Male)'},
                {'id': 'am_michael', 'name': 'Michael (Male)'},
                {'id': 'bf_emma', 'name': 'Emma (Female)'},
                {'id': 'bf_isabella', 'name': 'Isabella (Female)'},
                {'id': 'bm_george', 'name': 'George (Male)'},
                {'id': 'bm_lewis', 'name': 'Lewis (Male)'},
            ]
        return []


def speak(text: str) -> None:
    """
    Convenience function to speak text.
    
    Args:
        text: Text to speak
    """
    global _tts_manager
    if _tts_manager is None:
        _tts_manager = TTSManager()
    _tts_manager.speak(text)


def get_tts_manager(config: Optional[Dict[str, Any]] = None) -> TTSManager:
    """Get the singleton TTS manager instance."""
    global _tts_manager
    if _tts_manager is None:
        _tts_manager = TTSManager(config)
    return _tts_manager


def reset_tts_manager():
    """Reset the TTS manager (for testing)."""
    global _tts_manager
    _tts_manager = None
