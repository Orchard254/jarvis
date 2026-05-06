"""
7. Media & Interaction Tools (3 tools)
Human-facing interaction layer.
"""

from typing import Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime
import subprocess
import os

logger = logging.getLogger(__name__)


class AudioPlayer:
    """
    audio_player: Control audio playback
    
    Plays music, podcasts, and audio files. Supports YouTube/Spotify integration.
    """
    
    def __init__(self, default_volume: int = 50):
        self.default_volume = default_volume
        self.current_track = None
    
    def execute(self, action: str, media_data: Optional[dict] = None,
                **kwargs) -> dict:
        """
        Control audio playback.
        
        Args:
            action: One of 'play', 'pause', 'stop', 'next', 'previous', 'volume', 'queue'
            media_data: Media details (url, file_path, service, query)
            
        Returns:
            Playback result
        """
        try:
            if action == "play":
                if not media_data:
                    return {"success": False, "error": "media_data required"}
                
                url = media_data.get("url")
                file_path = media_data.get("file_path")
                query = media_data.get("query")
                service = media_data.get("service", "local")
                
                play_url = None
                
                # Handle different sources
                if file_path and os.path.exists(file_path):
                    play_url = file_path
                elif url:
                    play_url = url
                elif query and service in ["youtube", "spotify"]:
                    # In production, would search the service API
                    logger.info(f"Would search {service} for: {query}")
                    return {
                        "success": True,
                        "output": {
                            "status": "simulated",
                            "query": query,
                            "service": service,
                            "note": f"Configure {service} API to actually search and play"
                        }
                    }
                else:
                    return {"success": False, "error": "No valid media source provided"}
                
                # Try to play with system player
                self.current_track = {"url": play_url, "status": "playing"}
                logger.info(f"Playing: {play_url}")
                
                # Use platform-specific player
                if os.name == 'posix':
                    # Try common Linux players
                    players = ['vlc', 'mpv', 'afplay']  # afplay for macOS
                    for player in players:
                        try:
                            subprocess.Popen([player, play_url], 
                                           stdout=subprocess.DEVNULL, 
                                           stderr=subprocess.DEVNULL)
                            return {
                                "success": True,
                                "output": {
                                    "status": "playing",
                                    "track": play_url,
                                    "player": player,
                                    "started_at": datetime.now().isoformat()
                                }
                            }
                        except FileNotFoundError:
                            continue
                
                # Fallback: just log it
                return {
                    "success": True,
                    "output": {
                        "status": "queued",
                        "track": play_url,
                        "note": "No suitable media player found. Track queued."
                    }
                }
            
            elif action == "pause":
                self.current_track = {"status": "paused"} if self.current_track else {}
                return {"success": True, "output": {"status": "paused"}}
            
            elif action == "stop":
                self.current_track = None
                return {"success": True, "output": {"status": "stopped"}}
            
            elif action == "volume":
                volume = media_data.get("level", self.default_volume) if media_data else self.default_volume
                # Set system volume (platform-specific)
                logger.info(f"Setting volume to: {volume}%")
                return {
                    "success": True,
                    "output": {"volume": volume, "note": "Volume setting simulated"}
                }
            
            elif action == "next" or action == "previous":
                return {
                    "success": True,
                    "output": {"action": action, "note": "Track navigation simulated"}
                }
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class VoiceSynthesizer:
    """
    voice_synthesizer: Text-to-Speech (TTS)
    
    Converts text to spoken audio using system TTS engines.
    """
    
    def __init__(self, default_voice: str = "default", rate: int = 150):
        self.default_voice = default_voice
        self.rate = rate
    
    def execute(self, text: str, voice: Optional[str] = None,
                rate: Optional[int] = None, output_file: Optional[str] = None,
                **kwargs) -> dict:
        """
        Convert text to speech.
        
        Args:
            text: Text to synthesize
            voice: Voice name (optional, uses default)
            rate: Speech rate (words per minute)
            output_file: Save to file instead of playing
            
        Returns:
            TTS result
        """
        try:
            if not text:
                return {"success": False, "error": "text required"}
            
            voice = voice or self.default_voice
            rate = rate or self.rate
            
            logger.info(f"TTS: Converting {len(text)} chars to speech")
            
            # Use system TTS
            if os.name == 'posix':
                # macOS
                if os.path.exists('/usr/bin/say'):
                    cmd = ['say', '-r', str(rate), text]
                    if output_file:
                        cmd.extend(['-o', output_file])
                    try:
                        subprocess.run(cmd, check=True, timeout=60)
                        return {
                            "success": True,
                            "output": {
                                "status": "completed",
                                "voice": "macOS System",
                                "chars_processed": len(text),
                                "output_file": output_file
                            }
                        }
                    except subprocess.TimeoutExpired:
                        return {"success": False, "error": "TTS timed out"}
                
                # Linux - try espeak
                try:
                    cmd = ['espeak', '-s', str(rate), text]
                    if output_file:
                        cmd.extend(['-w', output_file])
                    subprocess.run(cmd, check=True, timeout=60,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return {
                        "success": True,
                        "output": {
                            "status": "completed",
                            "voice": "eSpeak",
                            "chars_processed": len(text),
                            "output_file": output_file
                        }
                    }
                except FileNotFoundError:
                    pass
            
            # Windows
            elif os.name == 'nt':
                try:
                    import win32com.client
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    speaker.Speak(text)
                    return {
                        "success": True,
                        "output": {
                            "status": "completed",
                            "voice": "Windows SAPI",
                            "chars_processed": len(text)
                        }
                    }
                except ImportError:
                    pass
            
            # Fallback: simulate
            return {
                "success": True,
                "output": {
                    "status": "simulated",
                    "text_preview": text[:100] + "..." if len(text) > 100 else text,
                    "voice": voice,
                    "rate": rate,
                    "note": "No TTS engine found. Output simulated."
                }
            }
                
        except Exception as e:
            return {"success": False, "error": str(e)}


class VoiceRecognizer:
    """
    voice_recognizer: Speech-to-Text (STT)
    
    Converts spoken audio to text using system STT engines.
    """
    
    def __init__(self, language: str = "en-US"):
        self.language = language
    
    def execute(self, audio_file: Optional[str] = None,
                use_microphone: bool = False,
                language: Optional[str] = None,
                **kwargs) -> dict:
        """
        Convert speech to text.
        
        Args:
            audio_file: Path to audio file
            use_microphone: Record from microphone instead
            language: Language code (e.g., 'en-US')
            
        Returns:
            Transcription result
        """
        try:
            language = language or self.language
            
            if use_microphone:
                # Would record from mic in production
                return {
                    "success": False,
                    "error": "Microphone recording requires additional setup (pyaudio)"
                }
            
            if not audio_file:
                return {"success": False, "error": "audio_file or use_microphone required"}
            
            if not os.path.exists(audio_file):
                return {"success": False, "error": f"Audio file not found: {audio_file}"}
            
            logger.info(f"STT: Processing {audio_file}")
            
            # Try using SpeechRecognition library if available
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(audio_file) as source:
                    audio = recognizer.record(source)
                text = recognizer.recognize_google(audio, language=language)
                return {
                    "success": True,
                    "output": {
                        "text": text,
                        "language": language,
                        "source": "Google Speech API"
                    }
                }
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"SpeechRecognition failed: {e}")
            
            # Fallback: simulate with placeholder
            return {
                "success": True,
                "output": {
                    "status": "simulated",
                    "audio_file": audio_file,
                    "language": language,
                    "text": "[Transcription would appear here - install speech_recognition]",
                    "note": "Install 'speech_recognition' package for actual STT"
                }
            }
                
        except Exception as e:
            return {"success": False, "error": str(e)}


# Factory functions
def get_audio_player(default_volume: int = 50) -> AudioPlayer:
    return AudioPlayer(default_volume=default_volume)


def get_voice_synthesizer(voice: str = "default", rate: int = 150) -> VoiceSynthesizer:
    return VoiceSynthesizer(default_voice=voice, rate=rate)


def get_voice_recognizer(language: str = "en-US") -> VoiceRecognizer:
    return VoiceRecognizer(language=language)
