import win32com.client
import pythoncom
import math
import array
import io
import wave
import winsound
import time
import threading
import os
from config import _load_cfg, _save_cfg, _atomic_write_text
from app_utils import get_variables_dir

_speaker = None
_voices = None
_selected_voice = None
_default_volume = 100  # volume for items without their own
_TTS_BOOST = 1.6  # extra loudness; SAPI volume is capped at 100, so speech is rendered, boosted and soft-limited
_SAFT_22KHZ_16BIT_MONO = 22
_base_voice = None  # system default voice, remembered the first time an event voice overrides it
_initialization_failed = False
_speech_queue = []
_is_speaking = False
_max_queue_size = 10  # Prevent unlimited queue growth
_tts_lock = threading.RLock()  # Thread safety for TTS operations

def _write_speaking_flag(speaking: bool):
    """Tell VoiceAttack whether TTS is speaking, so its sounds can wait"""
    try:
        _atomic_write_text(os.path.join(get_variables_dir(), "ttsSpeaking.txt"), "1" if speaking else "0")
    except Exception as e:
        print(f"[ANNOUNCER] Could not write ttsSpeaking.txt: {e}")

_SOUND_WAIT_MAX_SECS = 3.0
_sound_wait_start = None

def _voice_sound_playing() -> bool:
    """True while VoiceAttack is playing a feedback sound (soundPlaying.txt == 1)"""
    try:
        with open(os.path.join(get_variables_dir(), "soundPlaying.txt"), "r", encoding="utf-8") as f:
            return f.read().strip() == "1"
    except Exception:
        return False

def _initialize_tts():
    """Initialize TTS engine with retry logic"""
    global _speaker, _voices, _initialization_failed
    
    if _speaker is not None and not _initialization_failed:
        return True
    
    max_retries = 1  # Reduce retries to prevent multiple instances
    for attempt in range(max_retries):
        try:
            # Ensure we only have one instance
            if _speaker is not None:
                _speaker = None
            _speaker = win32com.client.Dispatch("SAPI.SpVoice")
            _voices = _speaker.GetVoices()
            _initialization_failed = False
            return True
        except Exception as e:
            print(f"[ANNOUNCER] TTS init failed: {e}")
            _initialization_failed = True
    
    return False

def list_voices():
    """Get list of available TTS voices"""
    if not _initialize_tts():
        return []
    try:
        return [v.GetDescription() for v in _voices]
    except Exception as e:
        print(f"[ANNOUNCER ERROR] Failed to list voices: {e}")
        return []

def _set_voice_without_save(name: str) -> bool:
    """Set TTS voice without saving to config (for loading saved settings)"""
    global _selected_voice
    if not _initialize_tts():
        return False
    
    try:
        available_voices = [v.GetDescription() for v in _voices]
        if name not in available_voices:
            return False
        
        for v in _voices:
            if v.GetDescription() == name:
                _speaker.Voice = v
                _selected_voice = name
                return True
    except Exception:
        return False
    return False

def _set_volume_without_save(vol: int):
    """Set TTS volume without saving to config (for loading saved settings)"""
    global _default_volume
    if not _initialize_tts():
        return
    
    try:
        vol = max(0, min(100, int(vol)))
        _speaker.Volume = vol
        _default_volume = vol
    except Exception:
        pass

def set_voice(name: str):
    """Set TTS voice by name and save to config"""
    global _selected_voice
    if not _initialize_tts():
        return False
    
    try:
        # Check if the voice name exists first
        available_voices = [v.GetDescription() for v in _voices]
        if name not in available_voices:
            print(f"[ANNOUNCER ERROR] Voice '{name}' not found in available voices: {available_voices}")
            return False
        
        for v in _voices:
            if v.GetDescription() == name:
                _speaker.Voice = v
                _selected_voice = name
                from config import update_config_value
                update_config_value("tts_voice", name)
                return True
    except Exception as e:
        # Don't save a broken voice to config
        return False
    return False

def set_volume(vol: int):
    """Set TTS volume (0-100) and save to config"""
    global _default_volume
    if not _initialize_tts():
        return
    
    try:
        vol = max(0, min(100, int(vol)))
        _speaker.Volume = vol
        _default_volume = vol
        from config import update_config_value
        update_config_value("tts_volume", vol)
    except Exception as e:
        pass

def get_current_voice():
    """Get the currently active voice name"""
    if not _initialize_tts():
        return "Unknown (TTS not initialized)"
    
    try:
        current_voice = _speaker.Voice.GetDescription()
        return current_voice
    except Exception as e:
        print(f"[ANNOUNCER ERROR] Failed to get current voice: {e}")
        return "Unknown (Error getting voice)"

def get_volume() -> int:
    """Get current TTS volume"""
    if not _initialize_tts():
        return 100
    
    try:
        return int(_speaker.Volume)
    except Exception as e:
        print(f"[ANNOUNCER ERROR] Failed to get volume: {e}")
        return 100

def load_saved_settings():
    """Load saved TTS settings from config"""
    global _selected_voice
    if not _initialize_tts():
        return
    
    cfg = _load_cfg()
    name = cfg.get("tts_voice")
    vol = cfg.get("tts_volume", 100)
    
    # Always set volume first (safer)
    _set_volume_without_save(vol)
    
    # Try to set saved voice, but fall back gracefully if it fails
    if name:
        success = _set_voice_without_save(name)
        if not success:
            # Voice not found - use system default but DON'T save to config
            # This preserves the user's preferred voice in config for when it becomes available
            print(f"[ANNOUNCER] Saved voice '{name}' not available, using system default (not saving)")
            available_voices = list_voices()
            if available_voices:
                _set_voice_without_save(available_voices[0])
    else:
        pass  # No saved voice found, using system default

def _apply_item_voice(voice, volume=None):
    """Use the item's own voice/volume, otherwise the user's selected (or system default) ones"""
    global _base_voice
    try:
        _speaker.Volume = _default_volume if volume is None else max(0, min(100, int(volume)))
        if voice:
            if _base_voice is None:
                _base_voice = _speaker.Voice
            for v in _voices:
                if v.GetDescription() == voice:
                    _speaker.Voice = v
                    return
        if _selected_voice:
            for v in _voices:
                if v.GetDescription() == _selected_voice:
                    _speaker.Voice = v
                    return
        elif _base_voice is not None:
            _speaker.Voice = _base_voice
    except Exception as e:
        print(f"[ANNOUNCER] Could not apply voice '{voice}': {e}")

def say(text: str, voice: str = None, volume: int = None):
    """Queue text for TTS speech with memory leak prevention; voice overrides the selected voice for this item"""
    global _speech_queue, _is_speaking
    print(f"[ANNOUNCER] say() called with: {text}")
    
    if not _initialize_tts():
        print(f"[ANNOUNCER] TTS initialization failed for: {text}")
        return
    
    if text.strip():
        with _tts_lock:  # Thread-safe queue access
            # Prevent unlimited queue growth (memory leak prevention)
            if len(_speech_queue) >= _max_queue_size:
                print(f"[ANNOUNCER] Queue full ({_max_queue_size} items), removing oldest item")
                _speech_queue.pop(0)  # Remove oldest item
            
            _speech_queue.append((text.strip(), voice, volume))
            print(f"[ANNOUNCER] Added to queue: {text} (queue size: {len(_speech_queue)})")
        
        _process_speech_queue()

def _process_speech_queue():
    """Process queued speech items with thread safety"""
    global _is_speaking, _speech_queue, _sound_wait_start

    with _tts_lock:  # Thread-safe access
        if _is_speaking or not _speech_queue:
            return

        if _voice_sound_playing():
            if _sound_wait_start is None:
                _sound_wait_start = time.time()
            if time.time() - _sound_wait_start < _SOUND_WAIT_MAX_SECS:
                threading.Timer(0.2, _process_speech_queue).start()
                return
        _sound_wait_start = None

        try:
            text, voice, volume = _speech_queue.pop(0)
            _apply_item_voice(voice, volume)
            _is_speaking = True
            _write_speaking_flag(True)
            print(f"[ANNOUNCER] Speaking: {text} (remaining queue: {len(_speech_queue)})")
            
            # Use asynchronous speech and check status periodically
            volume_now = _speaker.Volume
            
            threading.Thread(target=_speak_item, args=(text, volume_now), daemon=True).start()
                
        except Exception as e:
            print(f"[ANNOUNCER] Error in _process_speech_queue(): {e}")
            _is_speaking = False
            _reset_tts()

def _finish_speech():
    """Mark speech as done and start the next queued item, or clear the speaking flag"""
    global _is_speaking
    with _tts_lock:
        _is_speaking = False
        print("[ANNOUNCER] Speech completed")
        if _speech_queue:
            _process_speech_queue()
        else:
            _write_speaking_flag(False)

def _render_boosted(text: str, volume: int) -> bytes:
    """Synthesize text to a 22kHz mono wav in memory, boosted and soft-limited"""
    render = win32com.client.Dispatch("SAPI.SpVoice")
    render.Voice = _speaker.Voice
    stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
    fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
    fmt.Type = _SAFT_22KHZ_16BIT_MONO
    stream.Format = fmt
    render.AudioOutputStream = stream
    render.Speak(text, 0)
    samples = array.array("h")
    samples.frombytes(bytes(stream.GetData()))
    gain = max(0, min(100, int(volume))) / 100.0 * _TTS_BOOST
    tanh = math.tanh
    samples = array.array("h", (int(32767 * tanh(x * gain / 32767.0)) for x in samples))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(22050)
        out.writeframes(samples.tobytes())
    return buf.getvalue()

def _speak_item(text: str, volume: int):
    """Speak one queued item boosted; falls back to normal SAPI playback if rendering fails"""
    pythoncom.CoInitialize()
    try:
        winsound.PlaySound(_render_boosted(text, volume), winsound.SND_MEMORY)
    except Exception as e:
        print(f"[ANNOUNCER] Boosted speech failed, using normal playback: {e}")
        try:
            _speaker.Speak(text, 1)
        except Exception:
            pass
        _monitor_speech_completion()
        return
    finally:
        pythoncom.CoUninitialize()
    _finish_speech()

def _monitor_speech_completion():
    """Monitor when speech is complete and process next item"""
    global _is_speaking
    
    try:
        # Async speech may not report "speaking" yet; wait for it to start (max 1s)
        started = time.time()
        while _speaker.Status.RunningState != 2 and time.time() - started < 1.0:
            time.sleep(0.05)

        # Wait for speech to finish
        while _speaker.Status.RunningState == 2:  # Speaking
            time.sleep(0.1)
        
        _finish_speech()

    except Exception as e:
        print(f"[ANNOUNCER] Error monitoring speech: {e}")
        with _tts_lock:
            _is_speaking = False
            _write_speaking_flag(False)

def _reset_tts():
    """Reset TTS engine variables with proper cleanup"""
    global _speaker, _voices, _initialization_failed, _speech_queue, _is_speaking
    
    with _tts_lock:  # Thread-safe cleanup
        # Stop any ongoing speech
        if _speaker:
            try:
                _speaker.Speak("", 2)  # SVSFPurgeBeforeSpeak = 2 (stop current speech)
            except:
                pass
        
        # Clean up COM objects
        _speaker = None
        _voices = None
        _initialization_failed = True
        _speech_queue.clear()
        _is_speaking = False
        _write_speaking_flag(False)
        print("[ANNOUNCER] TTS system reset and cleaned up")


def cleanup_tts():
    """Clean up TTS system for application shutdown"""
    global _speaker, _voices, _speech_queue
    
    with _tts_lock:
        print("[ANNOUNCER] Cleaning up TTS system...")
        
        # Stop any ongoing speech
        if _speaker:
            try:
                _speaker.Speak("", 2)  # Stop current speech
            except:
                pass
        
        # Clear queue and release COM objects
        _speech_queue.clear()
        _speaker = None
        _voices = None
        
        print("[ANNOUNCER] TTS cleanup completed")

def diagnose_tts():
    """Diagnose TTS system for debugging"""
    try:
        # Test TTS initialization
        if _initialize_tts():
            # Test basic functionality with async speech
            _speaker.Speak("TTS test successful", 1)  # Async
            return True
        else:
            return False
    except Exception as e:
        return False

def reinitialize_tts():
    """Force reinitialize TTS engine (useful when voices are recycled)"""
    _reset_tts()
    _initialization_failed = False
    return _initialize_tts()

# Initialize TTS engine and load saved settings on module import
if _initialize_tts():
    load_saved_settings()
