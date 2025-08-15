from typing import List, Optional, Tuple

from utils.logger import logger
from config import ASSEMBLYAI_API_KEY

STT_AVAILABLE = False
_transcriber = None

try:
    if ASSEMBLYAI_API_KEY:
        import assemblyai as aai  # local import to avoid hard dependency if missing

        aai.settings.api_key = ASSEMBLYAI_API_KEY
        _transcriber = aai.Transcriber()
        STT_AVAILABLE = True
    else:
        logger.warning("ASSEMBLYAI_API_KEY not set; STT disabled")
except Exception as e:
    logger.warning(f"Failed to initialize AssemblyAI transcriber: {e}")
    STT_AVAILABLE = False


def stt_transcribe_bytes(audio_bytes: bytes) -> Tuple[Optional[str], str]:
    """Return (text, status)."""
    if not STT_AVAILABLE or _transcriber is None:
        return None, "unavailable"
    try:
        transcript = _transcriber.transcribe(audio_bytes)
        text = getattr(transcript, "text", None)
        status = getattr(transcript, "status", "unknown")
        return text, status
    except Exception as e:
        logger.warning(f"STT error: {e}")
        return None, f"error"

