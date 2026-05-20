import os
import sys
import asyncio
import time

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.abspath("."))

def test_edge_tts():
    print("==================================================")
    print("                CHECKING EDGE TTS                 ")
    print("==================================================")
    
    # 1. Check edge-tts import
    print("\n[Step 1] Checking edge-tts package import...")
    try:
        import edge_tts
        print("OK: edge_tts imported successfully!")
        print(f"  Path: {edge_tts.__file__}")
    except ImportError as e:
        print(f"ERROR: Failed to import edge_tts: {e}")
        print("  Please make sure 'edge-tts' is installed in the virtual environment.")
        return

    # 2. Check settings
    print("\n[Step 2] Checking voice and TTS settings...")
    import settings
    print(f"  TTS_ENGINE: {getattr(settings, 'TTS_ENGINE', 'edge')}")
    print(f"  TTS_ENABLED: {getattr(settings, 'TTS_ENABLED', True)}")
    print(f"  EDGE_TTS_VOICE: {getattr(settings, 'EDGE_TTS_VOICE', 'en-US-JennyNeural')}")
    print(f"  EDGE_TTS_RATE: {getattr(settings, 'EDGE_TTS_RATE', '+0%')}")
    print(f"  EDGE_TTS_TIMEOUT: {getattr(settings, 'EDGE_TTS_TIMEOUT', 15)}")

    # 3. Test online synthesis
    print("\n[Step 3] Testing online synthesis with Microsoft Edge TTS server...")
    text = "Hello! This is a test of Microsoft Edge Text to Speech."
    voice = getattr(settings, 'EDGE_TTS_VOICE', 'en-US-JennyNeural')
    rate = getattr(settings, 'EDGE_TTS_RATE', '+0%')
    volume = getattr(settings, 'EDGE_TTS_VOLUME', '+0%')
    pitch = getattr(settings, 'EDGE_TTS_PITCH', '+0Hz')
    
    mp3_path = "test_edge_tts.mp3"
    if os.path.exists(mp3_path):
        try:
            os.remove(mp3_path)
        except Exception:
            pass
            
    async def run_synthesis():
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch
        )
        await communicate.save(mp3_path)

    start_time = time.time()
    try:
        asyncio.run(run_synthesis())
        elapsed = round(time.time() - start_time, 2)
        print(f"OK: Synthesis completed successfully in {elapsed}s!")
        if os.path.exists(mp3_path):
            size = os.path.getsize(mp3_path)
            print(f"  MP3 file created: {mp3_path} ({size} bytes)")
        else:
            print("ERROR: MP3 file was not found on disk.")
    except Exception as e:
        print(f"ERROR: Synthesis failed: {e}")
        print("  This usually indicates an internet connection issue or that the Edge TTS servers are unreachable.")

    # 4. Check Pygame Audio Mixer
    print("\n[Step 4] Checking pygame audio mixer initialisation...")
    try:
        import pygame
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        if not pygame.get_init():
            pygame.init()
        pygame.mixer.init()
        print("OK: pygame mixer initialised successfully!")
        
        # Test loading the MP3
        if os.path.exists(mp3_path):
            print("OK: Loading synthesised MP3 into pygame mixer...")
            pygame.mixer.music.load(mp3_path)
            print("OK: Playing audio (non-blocking)...")
            pygame.mixer.music.play()
            
            # Wait a few seconds to let it play
            play_time = 3.0
            print(f"  Playing for {play_time} seconds...")
            time.sleep(play_time)
            
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            print("OK: Audio playback finished!")
    except Exception as e:
        print(f"ERROR: Pygame audio initialisation or playback failed: {e}")
        print("  This can happen in headless environments or if no audio output device is connected.")

    # 5. Check TTS main module interface
    print("\n[Step 5] Checking main output.tts interface...")
    try:
        from output.tts import speak
        print("OK: output.tts imported successfully!")
        print("  Calling speak('Edge TTS check successfully completed.') ...")
        # Ensure TTS is enabled for the test
        original_enabled = settings.TTS_ENABLED
        settings.TTS_ENABLED = True
        
        # We run it blocking=True so it waits for completion
        success = speak("Edge TTS check successfully completed.", blocking=True)
        settings.TTS_ENABLED = original_enabled
        print(f"OK: speak() returned: {success}")
    except Exception as e:
        print(f"ERROR: Call to speak() raised exception: {e}")

    # Clean up
    if os.path.exists(mp3_path):
        try:
            os.remove(mp3_path)
            print("\nOK: Cleaned up temporary MP3 file.")
        except Exception:
            pass

    print("\n==================================================")
    print("             EDGE TTS CHECK FINISHED              ")
    print("==================================================")

if __name__ == "__main__":
    test_edge_tts()
