"""
7. Media & Interaction (3 tools)
Human-facing interaction layer.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    audio_player: YouTube/Spotify local control
    
    Controls audio playback from various sources.
    """
    
    def __init__(self, default_volume: int = 50):
        self.default_volume = default_volume
        self._current_track = None
    
    def execute(self, action: str, source: Optional[str] = None,
                url: Optional[str] = None, volume: Optional[int] = None,
                **kwargs) -> dict:
        """
        Control audio playback.
        
        Args:
            action: One of 'play', 'pause', 'stop', 'next', 'previous', 'volume'
            source: Source type ('youtube', 'spotify', 'local')
            url: URL or file path
            volume: Volume level (0-100)
            
        Returns:
            Playback status
        """
        try:
            if action == "play":
                if not url and not source:
                    return {"success": False, "error": "url or source required"}
                
                self._current_track = {
                    "source": source or "unknown",
                    "url": url,
                    "status": "playing"
                }
                
                # In production, would integrate with actual player
                logger.info(f"Playing: {url or source}")
                
                return {
                    "success": True,
                    "output": {
                        "status": "playing",
                        "track": self._current_track,
                        "note": "Audio playback simulated - configure actual player backend"
                    }
                }
            
            elif action == "pause":
                if self._current_track:
                    self._current_track["status"] = "paused"
                return {
                    "success": True,
                    "output": {"status": "paused", "track": self._current_track}
                }
            
            elif action == "stop":
                self._current_track = None
                return {"success": True, "output": {"status": "stopped"}}
            
            elif action == "volume":
                if volume is None:
                    return {"success": False, "error": "volume level required"}
                vol = max(0, min(100, volume))
                return {"success": True, "output": {"volume": vol}}
            
            elif action == "next":
                return {
                    "success": True,
                    "output": {"status": "next", "note": "Would play next track"}
                }
            
            elif action == "previous":
                return {
                    "success": True,
                    "output": {"status": "previous", "note": "Would play previous track"}
                }
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class VoiceSynthesizer:
    """
    voice_synthesizer: Text-to-Speech (TTS)
    
    Converts text to spoken audio.
    """
    
    def __init__(self, voice: str = "default", rate: int = 150):
        self.voice = voice
        self.rate = rate
    
    def execute(self, text: str, output_file: Optional[str] = None,
                voice: Optional[str] = None, rate: Optional[int] = None,
                **kwargs) -> dict:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to speak
            output_file: Optional file to save audio
            voice: Voice name
            rate: Speech rate (words per minute)
            
        Returns:
            TTS result
        """
        try:
            selected_voice = voice or self.voice
            selected_rate = rate or self.rate
            
            # Try different TTS backends
            result = self._synthesize(text, selected_voice, selected_rate, output_file)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _synthesize(self, text: str, voice: str, rate: int, 
                    output_file: Optional[str]) -> dict:
        """Perform TTS synthesis."""
        
        # Try pyttsx3 first (offline)
        try:
            import pyttsx3
            
            engine = pyttsx3.init()
            engine.setProperty('voice', voice)
            engine.setProperty('rate', rate)
            
            if output_file:
                engine.save_to_file(text, output_file)
                engine.runAndWait()
                return {
                    "success": True,
                    "output": {
                        "file": output_file,
                        "voice": voice,
                        "rate": rate,
                        "backend": "pyttsx3"
                    }
                }
            else:
                # Just speak (blocking)
                engine.say(text)
                engine.runAndWait()
                return {
                    "success": True,
                    "output": {
                        "spoken": True,
                        "voice": voice,
                        "rate": rate,
                        "backend": "pyttsx3"
                    }
                }
                
        except ImportError:
            pass
        
        # Try espeak via subprocess
        try:
            import subprocess
            
            cmd = ["espeak", "-v", voice, "-s", str(rate), text]
            if output_file:
                cmd.extend(["-w", output_file])
            
            subprocess.run(cmd, check=True, capture_output=True)
            
            return {
                "success": True,
                "output": {
                    "file": output_file,
                    "voice": voice,
                    "rate": rate,
                    "backend": "espeak"
                }
            }
            
        except (ImportError, subprocess.CalledProcessError):
            pass
        
        # Fallback: simulate
        logger.warning("No TTS backend available, simulating")
        return {
            "success": True,
            "output": {
                "text": text,
                "voice": voice,
                "rate": rate,
                "backend": "simulated",
                "note": "Install pyttsx3 or espeak for actual TTS"
            }
        }


class VoiceRecognizer:
    """
    voice_recognizer: Speech-to-Text (STT)
    
    Converts spoken audio to text.
    """
    
    def __init__(self, language: str = "en-US"):
        self.language = language
    
    def execute(self, audio_file: Optional[str] = None,
                audio_data: Optional[bytes] = None,
                language: Optional[str] = None,
                timeout: float = 10.0,
                **kwargs) -> dict:
        """
        Recognize speech from audio.
        
        Args:
            audio_file: Path to audio file
            audio_data: Raw audio bytes
            language: Language code
            timeout: Recognition timeout
            
        Returns:
            Transcribed text
        """
        try:
            selected_lang = language or self.language
            
            # Try speech_recognition library
            try:
                import speech_recognition as sr
                
                recognizer = sr.Recognizer()
                
                if audio_file:
                    with sr.AudioFile(audio_file) as source:
                        audio = recognizer.record(source)
                elif audio_data:
                    audio = sr.AudioData(audio_data, 16000, 2)
                else:
                    # Try microphone
                    with sr.Microphone() as source:
                        audio = recognizer.listen(source, timeout=timeout)
                
                text = recognizer.recognize_google(audio, language=selected_lang)
                
                return {
                    "success": True,
                    "output": {
                        "text": text,
                        "language": selected_lang,
                        "backend": "google"
                    }
                }
                
            except ImportError:
                pass
            except sr.UnknownValueError:
                return {
                    "success": False,
                    "error": "Speech not recognized",
                    "output": None
                }
            except sr.RequestError as e:
                return {
                    "success": False,
                    "error": f"STT service error: {e}",
                    "output": None
                }
            
            # Fallback: simulate
            logger.warning("No STT backend available, returning simulation")
            return {
                "success": True,
                "output": {
                    "text": "[Speech recognition simulated]",
                    "language": selected_lang,
                    "backend": "simulated",
                    "note": "Install speech_recognition for actual STT"
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# Factory functions
def get_audio_player(default_volume: int = 50) -> AudioPlayer:
    return AudioPlayer(default_volume=default_volume)


def get_voice_synthesizer(voice: str = "default", rate: int = 150) -> VoiceSynthesizer:
    return VoiceSynthesizer(voice=voice, rate=rate)


def get_voice_recognizer(language: str = "en-US") -> VoiceRecognizer:
    return VoiceRecognizer(language=language)
