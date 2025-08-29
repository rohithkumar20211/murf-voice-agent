from typing import Optional, Tuple, Callable, Awaitable
import asyncio
from utils.logger import logger
from api_config import get_api_key

STT_AVAILABLE = False
_transcriber = None
_api_key = None

def initialize_stt():
    """Initialize or reinitialize STT with current API key"""
    global STT_AVAILABLE, _transcriber, _api_key
    
    # Import here to avoid circular dependency
    from api_config import get_api_key
    
    _api_key = get_api_key("ASSEMBLYAI_API_KEY")
    
    if _api_key:
        try:
            import assemblyai as aai
            aai.settings.api_key = _api_key
            _transcriber = aai.Transcriber()
            STT_AVAILABLE = True
            logger.info("AssemblyAI STT initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize AssemblyAI transcriber: {e}")
            STT_AVAILABLE = False
            _transcriber = None
    else:
        logger.warning("ASSEMBLYAI_API_KEY not configured; STT disabled")
        STT_AVAILABLE = False
        _transcriber = None
    
    return STT_AVAILABLE

def reinitialize_stt():
    """Reinitialize STT with potentially new API key"""
    return initialize_stt()

# Initialize on module load
initialize_stt()


def stt_transcribe_bytes(audio_bytes: bytes) -> Tuple[Optional[str], str]:
    """Return (text, status) using non-streaming API (file upload style)."""
    assembly_key = get_api_key("ASSEMBLYAI_API_KEY")
    if not assembly_key:
        return None, "AssemblyAI API key not set"
    
    if not STT_AVAILABLE or _transcriber is None:
        return None, "unavailable"
    try:
        # Transcriber.transcribe is sync; run in a thread to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        transcript = loop.run_until_complete(asyncio.to_thread(_transcriber.transcribe, audio_bytes)) if loop.is_running() else _transcriber.transcribe(audio_bytes)
        text = getattr(transcript, "text", None)
        status = getattr(transcript, "status", "unknown")
        return text, status
    except Exception as e:
        logger.warning(f"STT error: {e}")
        return None, "error"


# ---------- Streaming implementation using AssemblyAI v3 ----------
_V3_OK = False
try:
    from assemblyai.streaming.v3 import (  # type: ignore
        BeginEvent,
        StreamingClient,
        StreamingClientOptions,
        StreamingParameters,
        StreamingSessionParameters,
        StreamingError,
        StreamingEvents,
        TurnEvent,
        TerminationEvent,
    )
    _V3_OK = True
except Exception as e:
    logger.warning(f"AssemblyAI v3 streaming import failed: {e}")
    _V3_OK = False


class AssemblyAIStreamingWrapper:
    """Wrapper for AssemblyAI streaming client following the reference implementation"""
    def __init__(self, sample_rate=16000, on_transcript=None, loop=None):
        self.on_transcript_callback = on_transcript
        self.is_connected = False
        self.loop = loop or asyncio.get_event_loop()
        
        # Get the current API key
        from api_config import get_api_key
        api_key = get_api_key("ASSEMBLYAI_API_KEY")
        
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not configured")
        
        self.client = StreamingClient(
            StreamingClientOptions(
                api_key=api_key,
                api_host="streaming.assemblyai.com"
            )
        )
        
        
        self._setup_event_handlers()
        
        
        try:
            # Enable turn formatting from the start for proper turn detection
            self.client.connect(StreamingParameters(
                sample_rate=sample_rate,
                format_turns=True,  # Enable turn detection from the beginning
                disable_partial_transcripts=False  # Keep partial transcripts for real-time feedback
            ))
            self.is_connected = True
            logger.info("AssemblyAI streaming client connected with turn detection enabled")
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            raise
    
    def _setup_event_handlers(self):
        """Set up event handlers following the reference implementation pattern"""
        
        # Store self reference for use in handlers
        wrapper = self
        
        # The SDK passes 'self' as first argument, then the event
        def on_begin(self_arg, event: BeginEvent):
            # Silent - no console output for cleaner logs
            logger.info(f"Session started: {event.id}")
        
        def on_turn(self_arg, event: TurnEvent):
            # Don't print transcripts here - they'll be handled by the main app
            if event.transcript:
                # Send to callback if available with turn status
                if wrapper.on_transcript_callback and wrapper.loop:
                    try:
                        # Schedule the async callback to run in the main event loop
                        future = asyncio.run_coroutine_threadsafe(
                            wrapper.on_transcript_callback(event.transcript, event.end_of_turn),
                            wrapper.loop
                        )
                        # We can optionally add a timeout or check the result
                        # future.result(timeout=2)
                    except Exception as e:
                        logger.error(f"Failed to schedule transcript callback: {e}")
                elif not wrapper.loop:
                    logger.warning("No event loop provided for transcript callback.")
                else:
                    logger.info(f"Transcript received (callback not set): {event.transcript}")
        
        def on_terminated(self_arg, event: TerminationEvent):
            duration = getattr(event, 'audio_duration_seconds', 0)
            # Silent - no console output for cleaner logs
            logger.info(f"Session terminated: {duration} seconds processed")
        
        def on_error(self_arg, error: StreamingError):
            # Silent - just log to logger, not console
            logger.warning(f"Streaming error: {error}")
        
        # Register handlers
        self.client.on(StreamingEvents.Begin, on_begin)
        self.client.on(StreamingEvents.Turn, on_turn)
        self.client.on(StreamingEvents.Termination, on_terminated)
        self.client.on(StreamingEvents.Error, on_error)
    
    async def send_audio(self, audio_chunk: bytes):
        """Send audio data to AssemblyAI"""
        if self.is_connected:
            try:
                # Debug: log audio chunk size
                if len(audio_chunk) > 0:
                    logger.debug(f"Streaming {len(audio_chunk)} bytes to AssemblyAI")
                self.client.stream(audio_chunk)
            except Exception as e:
                logger.warning(f"Failed to send audio: {e}")
    
    async def close(self):
        """Close the streaming session"""
        if self.is_connected:
            try:
                self.client.disconnect(terminate=True)
                self.is_connected = False
            except Exception as e:
                logger.warning(f"Error closing session: {e}")


async def stream_transcribe(
    on_transcript: Callable[[str, bool], Awaitable[None]],
    loop: Optional[asyncio.AbstractEventLoop] = None
) -> Optional[object]:
    """Create a streaming transcription session with AssemblyAI"""
    if not STT_AVAILABLE or not _V3_OK:
        logger.warning("STT not available or v3 SDK not imported")
        return None
    
    try:
        # Create wrapper with callback and event loop
        wrapper = AssemblyAIStreamingWrapper(
            sample_rate=16000,
            on_transcript=on_transcript,
            loop=loop
        )
        return wrapper
    except Exception as e:
        logger.error(f"Failed to create streaming session: {e}")
        return None

