from typing import List, Optional

from utils.logger import logger
from config import MURF_API_KEY
from personas import get_persona_voice

TTS_AVAILABLE = False
_client = None

try:
    if MURF_API_KEY:
        import murf  # local import to avoid hard dependency if missing

        _client = murf.Murf(api_key=MURF_API_KEY)
        TTS_AVAILABLE = True
    else:
        logger.warning("MURF_API_KEY not set; TTS disabled")
except Exception as e:
    logger.warning(f"Failed to initialize Murf client: {e}")
    TTS_AVAILABLE = False


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

