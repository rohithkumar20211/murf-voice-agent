from typing import List, Optional

from utils.logger import logger
from personas import get_persona_voice

TTS_AVAILABLE = False
_client = None

def initialize_tts():
    """Initialize or reinitialize TTS with current API key"""
    global TTS_AVAILABLE, _client
    
    # Import here to avoid circular dependency
    from api_config import get_api_key
    
    api_key = get_api_key("MURF_API_KEY")
    
    if api_key:
        try:
            import murf  # local import to avoid hard dependency if missing
            _client = murf.Murf(api_key=api_key)
            TTS_AVAILABLE = True
            logger.info("Murf TTS initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Murf client: {e}")
            TTS_AVAILABLE = False
            _client = None
    else:
        logger.warning("MURF_API_KEY not configured; TTS disabled")
        TTS_AVAILABLE = False
        _client = None
    
    return TTS_AVAILABLE

def reinitialize_tts():
    """Reinitialize TTS with potentially new API key"""
    return initialize_tts()

# Initialize on module load
initialize_tts()


def _extract_audio_url(result) -> Optional[str]:
    for attr in ("audio_file", "audio_url", "url"):
        if hasattr(result, attr):
            value = getattr(result, attr)
            if value:
                return str(value)
    return None


def tts_generate(text: str, voice_id: str = None, fmt: str = "mp3") -> Optional[str]:
    if not TTS_AVAILABLE or _client is None:
        return None
    try:
        # Use persona voice if no voice_id specified
        if voice_id is None:
            voice_id = get_persona_voice()
        res = _client.text_to_speech.generate(text=text, voice_id=voice_id, format=fmt)
        return _extract_audio_url(res)
    except Exception as e:
        logger.warning(f"TTS error: {e}")
        return None


def tts_get_voices():
    if not TTS_AVAILABLE or _client is None:
        return []
    try:
        return _client.text_to_speech.get_voices()
    except Exception as e:
        logger.warning(f"Get voices error: {e}")
        return []

