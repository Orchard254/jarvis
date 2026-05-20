import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure current directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Windows console encoding fix ─────────────────────────────────────────────
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # non-interactive / piped — ignore

import settings


class TestVoicePipelineUpgrade(unittest.TestCase):
    def setUp(self):
        # Backup original settings
        self.orig_enabled = settings.VOICE_ENABLED
        self.orig_tts_enabled = settings.TTS_ENABLED
        
        # Ensure enabled for the test
        settings.VOICE_ENABLED = True
        settings.TTS_ENABLED = True

    def tearDown(self):
        # Restore settings
        settings.VOICE_ENABLED = self.orig_enabled
        settings.TTS_ENABLED = self.orig_tts_enabled

    @patch("output.sounds._play_thread")
    def test_sounds_chime_trigger(self, mock_play_thread):
        """Verify that play_chime spins up background threads without exceptions."""
        from output.sounds import play_chime
        
        # Play different chime types
        play_chime("wake")
        play_chime("success")
        play_chime("error")
        
        # Verify it attempts to trigger the background thread for playback
        self.assertEqual(mock_play_thread.call_count, 3)
        mock_play_thread.assert_any_call("wake")
        mock_play_thread.assert_any_call("success")
        mock_play_thread.assert_any_call("error")
        print("[OK] output.sounds.play_chime correctly dispatches threads!")

    @patch("perception.stt._capture")
    @patch("perception.stt._transcribe")
    def test_stt_settings_binding(self, mock_transcribe, mock_capture):
        """Verify that STT engine respects settings from environment."""
        from perception import stt
        
        mock_capture.return_value = (MagicMock(), None)
        mock_transcribe.return_value = "hello jarvis"
        
        # Capture speech
        result = stt.listen(timeout=2.0)
        
        # Verify that SpeechRecognition bounds match .env / settings
        # Note: energy_threshold may be adjusted dynamically by _calibrate_once() if a mic is present.
        self.assertTrue(stt._recognizer.energy_threshold > 0)
        self.assertEqual(stt._recognizer.pause_threshold, settings.SILENCE_DURATION)
        self.assertTrue(stt._recognizer.dynamic_energy_threshold)
        
        self.assertEqual(result, "hello jarvis")
        print("[OK] perception.stt correctly binds settings and transcribes!")

    @patch("perception.input_handler.stt.listen")
    @patch("output.sounds.play_chime")
    @patch("output.tts.speak")
    def test_input_handler_integration(self, mock_speak, mock_chime, mock_listen):
        """Verify that InputHandler correctly plays chimes and routes speech."""
        from perception.input_handler import InputHandler
        
        # Mock orchestrator and routing
        mock_orc = MagicMock()
        mock_orc.handle.return_value = "Responding to command"
        
        handler = InputHandler(mock_orc)
        
        # 1. Simulate speech transcription returning "hello"
        mock_listen.return_value = "hello"
        
        # Trigger the wake word event
        handler._on_wake(wake_word="alexa")
        
        # Verify:
        # A. Triggered 'wake' chime
        mock_chime.assert_any_call("wake")
        # B. Listened for speech
        mock_listen.assert_called_once()
        # C. Triggered 'success' chime upon transcribing "hello"
        mock_chime.assert_any_call("success")
        # D. Routed to orchestrator
        mock_orc.handle.assert_called_with("hello")
        
        print("[OK] InputHandler successfully plays chimes, prints indicators, and routes response!")


if __name__ == "__main__":
    print("==================================================")
    print("         RUNNING INTEGRATED VOICE TESTS           ")
    print("==================================================")
    unittest.main()
