"""
JARVIS Wake Word Detection - Detects wake words using openwakeword.

Provides always-on wake word detection with:
- Multiple wake word support
- Custom model loading
- Configurable sensitivity
- Low-latency detection
"""

import threading
import numpy as np
from typing import Optional, Callable, List, Dict, Any
from pathlib import Path

try:
    import openwakeword
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    Model = None

try:
    import sounddevice as sd
    SOUNDEVICE_AVAILABLE = True
except (ImportError, OSError):
    SOUNDEVICE_AVAILABLE = False
    sd = None


class WakeWordDetection:
    """
    Wake word detection engine using openwakeword.
    
    Features:
    - Always-on listening
    - Multiple wake word models
    - Adjustable sensitivity per model
    - Callback-based detection
    """
    
    DEFAULT_WAKE_WORDS = ['hey jarvis', 'ok jarvis']
    
    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        inference_framework: str = 'tflite',
        chunk_size: int = 1280,
        threshold: float = 0.5
    ):
        self.wake_words = wake_words or self.DEFAULT_WAKE_WORDS
        self.inference_framework = inference_framework
        self.chunk_size = chunk_size
        self.threshold = threshold
        
        self._model: Optional[Model] = None
        self._listening = False
        self._audio_stream = None
        self._listen_thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[[str], None]] = []
        
        if OPENWAKEWORD_AVAILABLE and SOUNDEVICE_AVAILABLE:
            self._initialize_model()
    
    def _initialize_model(self):
        """Initialize openwakeword model with wake word models."""
        try:
            # Load default models or custom ones
            wakeword_models = []
            for ww in self.wake_words:
                # Try to load custom model, fall back to defaults
                model_path = self._find_model_for_wakeword(ww)
                if model_path:
                    wakeword_models.append(model_path)
            
            if wakeword_models:
                self._model = Model(
                    wakeword_models=wakeword_models,
                    inference_framework=self.inference_framework
                )
            else:
                # Use built-in models
                self._model = Model()
                
        except Exception as e:
            print(f"Warning: Could not initialize wake word model: {e}")
            self._model = None
    
    def _find_model_for_wakeword(self, wake_word: str) -> Optional[Path]:
        """Find model file for a wake word."""
        # Look in common locations
        possible_paths = [
            Path(__file__).parent.parent / 'models' / 'wakewords' / f'{wake_word.replace(" ", "_")}.tflite',
            Path(__file__).parent.parent / 'models' / 'wakewords' / f'{wake_word.replace(" ", "_")}.onnx',
            Path.home() / '.jarvis' / 'wakewords' / f'{wake_word.replace(" ", "_")}.tflite',
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        return None
    
    def add_callback(self, callback: Callable[[str], None]):
        """Add callback for wake word detection."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[str], None]):
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start_listening(self, device_index: Optional[int] = None):
        """
        Start wake word detection.
        
        Args:
            device_index: Microphone device index (None = default)
        """
        if not OPENWAKEWORD_AVAILABLE or not SOUNDEVICE_AVAILABLE:
            print("Warning: Required libraries not available for wake word detection")
            return
        
        if self._listening:
            return
        
        self._listening = True
        
        def audio_callback(indata, frames, time, status):
            """Process audio chunks for wake word detection."""
            if status:
                print(f"Audio stream status: {status}")
            
            if self._model is None:
                return
            
            # Get predictions from model
            predictions = self._model.predict(indata.flatten())
            
            # Check each model for wake word detection
            for model_name, prediction in predictions.items():
                if prediction > self.threshold:
                    # Wake word detected
                    self._on_wake_word_detected(model_name)
        
        try:
            # Start audio stream
            self._audio_stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                blocksize=self.chunk_size,
                callback=audio_callback,
                device=device_index
            )
            self._audio_stream.start()
            
        except Exception as e:
            print(f"Error starting wake word detection: {e}")
            self._listening = False
    
    def stop_listening(self):
        """Stop wake word detection."""
        self._listening = False
        
        if self._audio_stream:
            try:
                self._audio_stream.stop()
                self._audio_stream.close()
            except Exception as e:
                print(f"Error stopping audio stream: {e}")
            self._audio_stream = None
        
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
            self._listen_thread = None
    
    def _on_wake_word_detected(self, model_name: str):
        """Handle wake word detection event."""
        # Extract wake word from model name
        wake_word = model_name.replace('.tflite', '').replace('.onnx', '').replace('_', ' ')
        
        # Call all registered callbacks
        for callback in self._callbacks:
            try:
                callback(wake_word)
            except Exception as e:
                print(f"Error in wake word callback: {e}")
    
    @property
    def is_listening(self) -> bool:
        return self._listening
    
    def set_threshold(self, threshold: float):
        """Set detection threshold (0.0 to 1.0)."""
        self.threshold = max(0.0, min(1.0, threshold))
    
    def list_audio_devices(self) -> List[Dict[str, Any]]:
        """List available audio input devices."""
        if not SOUNDEVICE_AVAILABLE:
            return []
        
        devices = []
        try:
            device_list = sd.query_devices()
            for i, dev in enumerate(device_list):
                if dev['max_input_channels'] > 0:
                    devices.append({
                        'index': i,
                        'name': dev['name'],
                        'channels': dev['max_input_channels'],
                        'sample_rate': dev['default_samplerate']
                    })
        except Exception as e:
            print(f"Error listing audio devices: {e}")
        
        return devices
    
    def load_custom_model(self, model_path: str, wake_word_name: str) -> bool:
        """
        Load a custom wake word model.
        
        Args:
            model_path: Path to .tflite or .onnx model
            wake_word_name: Name to associate with this model
            
        Returns:
            True if successful
        """
        if not OPENWAKEWORD_AVAILABLE:
            return False
        
        try:
            path = Path(model_path)
            if not path.exists():
                return False
            
            # Reload model with new wakeword
            if self._model:
                current_models = getattr(self._model, 'wakeword_models', [])
                current_models.append(str(path))
                self._model = Model(wakeword_models=current_models)
            else:
                self._model = Model(wakeword_models=[str(path)])
            
            if wake_word_name not in self.wake_words:
                self.wake_words.append(wake_word_name)
            
            return True
            
        except Exception as e:
            print(f"Error loading custom model: {e}")
            return False


# Singleton instance
_wake_word: Optional[WakeWordDetection] = None


def get_wake_word_detection(
    wake_words: Optional[List[str]] = None,
    threshold: float = 0.5
) -> WakeWordDetection:
    """Get the singleton wake word detection instance."""
    global _wake_word
    if _wake_word is None:
        _wake_word = WakeWordDetection(wake_words=wake_words, threshold=threshold)
    return _wake_word


def reset_wake_word_detection():
    """Reset the singleton instance (for testing)."""
    global _wake_word
    if _wake_word:
        _wake_word.stop_listening()
    _wake_word = None


def start_wake_word_detection(callback: Callable[[str], None]):
    """Convenience function to start wake word detection."""
    detector = get_wake_word_detection()
    detector.add_callback(callback)
    detector.start_listening()


def stop_wake_word_detection():
    """Convenience function to stop wake word detection."""
    detector = get_wake_word_detection()
    detector.stop_listening()
