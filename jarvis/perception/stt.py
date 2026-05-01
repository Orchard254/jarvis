"""
JARVIS Speech-to-Text - Converts audio input to text using Google Speech Recognition.

Provides real-time transcription for voice commands with:
- Multiple language support
- Confidence scoring
- Noise handling
- Timeout management
"""

import io
import wave
import threading
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import json

try:
    import speech_recognition as sr
    SPEECH_RECOGNIZER_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNIZER_AVAILABLE = False
    sr = None


class STTResult:
    """Result from speech-to-text conversion."""
    
    def __init__(
        self,
        text: str,
        confidence: float = 1.0,
        language: str = 'en-US',
        duration: float = 0.0,
        error: Optional[str] = None
    ):
        self.text = text
        self.confidence = confidence
        self.language = language
        self.duration = duration
        self.error = error
    
    @property
    def is_success(self) -> bool:
        return self.error is None and bool(self.text.strip())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'text': self.text,
            'confidence': self.confidence,
            'language': self.language,
            'duration': self.duration,
            'error': self.error,
            'success': self.is_success
        }


class SpeechToText:
    """
    Speech-to-text engine using Google Speech Recognition API.
    
    Features:
    - Real-time transcription
    - Multiple language support
    - Adjustable sensitivity
    - Background listening mode
    """
    
    def __init__(
        self,
        language: str = 'en-US',
        timeout: float = 5.0,
        phrase_time_limit: float = 10.0,
        energy_threshold: int = 4000
    ):
        self.language = language
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self.energy_threshold = energy_threshold
        
        if SPEECH_RECOGNIZER_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = energy_threshold
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
        else:
            self.recognizer = None
        
        self._listening = False
        self._listen_thread: Optional[threading.Thread] = None
    
    def listen_from_microphone(
        self,
        microphone_index: Optional[int] = None
    ) -> STTResult:
        """
        Listen to microphone and transcribe speech.
        
        Args:
            microphone_index: Specific microphone index (None = default)
            
        Returns:
            STTResult with transcribed text
        """
        if not SPEECH_RECOGNIZER_AVAILABLE:
            return STTResult(
                text='',
                error='speech_recognition library not installed'
            )
        
        try:
            with sr.Microphone(device_index=microphone_index) as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen for phrase
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit
                )
                
                return self._transcribe_audio(audio)
                
        except sr.WaitTimeoutError:
            return STTResult(
                text='',
                error='Listening timeout - no speech detected'
            )
        except sr.UnknownValueError:
            return STTResult(
                text='',
                error='Speech not recognized'
            )
        except sr.RequestError as e:
            return STTResult(
                text='',
                error=f'Speech recognition service error: {str(e)}'
            )
        except Exception as e:
            return STTResult(
                text='',
                error=f'Microphone error: {str(e)}'
            )
    
    def transcribe_audio_file(self, file_path: str) -> STTResult:
        """
        Transcribe an audio file.
        
        Args:
            file_path: Path to WAV file
            
        Returns:
            STTResult with transcribed text
        """
        if not SPEECH_RECOGNIZER_AVAILABLE:
            return STTResult(
                text='',
                error='speech_recognition library not installed'
            )
        
        try:
            with sr.AudioFile(file_path) as source:
                audio = self.recognizer.record(source)
                return self._transcribe_audio(audio)
        except FileNotFoundError:
            return STTResult(
                text='',
                error=f'Audio file not found: {file_path}'
            )
        except Exception as e:
            return STTResult(
                text='',
                error=f'Audio file error: {str(e)}'
            )
    
    def transcribe_audio_data(self, audio_data: bytes, sample_rate: int = 16000) -> STTResult:
        """
        Transcribe raw audio data.
        
        Args:
            audio_data: Raw PCM audio bytes
            sample_rate: Audio sample rate in Hz
            
        Returns:
            STTResult with transcribed text
        """
        if not SPEECH_RECOGNIZER_AVAILABLE:
            return STTResult(
                text='',
                error='speech_recognition library not installed'
            )
        
        try:
            # Convert to AudioData format
            audio = sr.AudioData(audio_data, sample_rate, 2)  # 16-bit samples
            return self._transcribe_audio(audio)
        except Exception as e:
            return STTResult(
                text='',
                error=f'Audio data error: {str(e)}'
            )
    
    def _transcribe_audio(self, audio: 'sr.AudioData') -> STTResult:
        """Transcribe audio using Google Speech Recognition."""
        try:
            # Use Google Speech Recognition
            text = self.recognizer.recognize_google(
                audio,
                language=self.language,
                show_all=False
            )
            
            return STTResult(
                text=text.strip(),
                confidence=1.0,  # Google doesn't provide confidence in simple mode
                language=self.language,
                duration=len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
            )
            
        except sr.UnknownValueError:
            return STTResult(
                text='',
                error='Speech not recognized'
            )
        except sr.RequestError as e:
            return STTResult(
                text='',
                error=f'Speech recognition service error: {str(e)}'
            )
    
    def start_listening(self, callback: Callable[[STTResult], None]):
        """
        Start background listening with callback.
        
        Args:
            callback: Function to call with STTResult when speech detected
        """
        if not SPEECH_RECOGNIZER_AVAILABLE:
            return
        
        self._listening = True
        
        def listen_loop():
            while self._listening:
                result = self.listen_from_microphone()
                if result.is_success:
                    callback(result)
        
        self._listen_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listen_thread.start()
    
    def stop_listening(self):
        """Stop background listening."""
        self._listening = False
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
            self._listen_thread = None
    
    @property
    def is_listening(self) -> bool:
        return self._listening
    
    def list_microphones(self) -> list:
        """List available microphones."""
        if not SPEECH_RECOGNIZER_AVAILABLE:
            return []
        
        return sr.Microphone.list_microphone_names()
    
    def set_language(self, language: str):
        """Change recognition language."""
        self.language = language
    
    def set_energy_threshold(self, threshold: int):
        """Adjust microphone sensitivity."""
        self.energy_threshold = threshold
        if self.recognizer:
            self.recognizer.energy_threshold = threshold


# Singleton instance
_stt: Optional[SpeechToText] = None


def get_stt(
    language: str = 'en-US',
    timeout: float = 5.0
) -> SpeechToText:
    """Get the singleton STT instance."""
    global _stt
    if _stt is None:
        _stt = SpeechToText(language=language, timeout=timeout)
    return _stt


def reset_stt():
    """Reset the singleton instance (for testing)."""
    global _stt
    if _stt:
        _stt.stop_listening()
    _stt = None


def transcribe_speech(timeout: float = 5.0) -> STTResult:
    """Convenience function to transcribe speech."""
    stt = get_stt(timeout=timeout)
    return stt.listen_from_microphone()
