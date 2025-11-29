import win32com.client
import time
import threading
from config import _load_cfg, _save_cfg

_speaker = None
_voices = None
_selected_voice = None
_initialization_failed = False
_speech_queue = []
_is_speaking = False
_max_queue_size = 10  # Prevent unlimited queue growth
_tts_lock = threading.RLock()  # Thread safety for TTS operations

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
    if not _initialize_tts():
        return
    
    try:
        vol = max(0, min(100, int(vol)))
        _speaker.Volume = vol
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
    if not _initialize_tts():
        return
    
    try:
        vol = max(0, min(100, int(vol)))
        _speaker.Volume = vol
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

def say(text: str):
    """Queue text for TTS speech with memory leak prevention"""
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
            
            _speech_queue.append(text.strip())
            print(f"[ANNOUNCER] Added to queue: {text} (queue size: {len(_speech_queue)})")
        
        _process_speech_queue()

def _process_speech_queue():
    """Process queued speech items with thread safety"""
    global _is_speaking, _speech_queue
    
    with _tts_lock:  # Thread-safe access
        if _is_speaking or not _speech_queue:
            return
        
        try:
            text = _speech_queue.pop(0)
            _is_speaking = True
            print(f"[ANNOUNCER] Speaking: {text} (remaining queue: {len(_speech_queue)})")
            
            # Use asynchronous speech and check status periodically
            _speaker.Speak(text, 1)  # SVSFlagsAsync = 1 (asynchronous)
            
            # Start monitoring speech completion
            threading.Thread(target=_monitor_speech_completion, daemon=True).start()
                
        except Exception as e:
            print(f"[ANNOUNCER] Error in _process_speech_queue(): {e}")
            _is_speaking = False
            _reset_tts()

def _monitor_speech_completion():
    """Monitor when speech is complete and process next item"""
    global _is_speaking
    
    try:
        # Wait for speech to finish
        while _speaker.Status.RunningState == 2:  # Speaking
            time.sleep(0.1)
        
        with _tts_lock:  # Thread-safe access
            _is_speaking = False
            print(f"[ANNOUNCER] Speech completed")
            
            # Process next item if any
            if _speech_queue:
                _process_speech_queue()
                
    except Exception as e:
        print(f"[ANNOUNCER] Error monitoring speech: {e}")
        with _tts_lock:
            _is_speaking = False

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
