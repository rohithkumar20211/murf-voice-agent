import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from schemas import (
    ChatHistoryResponse,
    ChatMessage,
    LLMQueryAudioResponse,
    LLMQueryRequest,
    TTSRequest,
    TTSResponse,
)
from services.stt import stt_transcribe_bytes, STT_AVAILABLE
from services.tts import tts_generate, tts_get_voices, TTS_AVAILABLE
from services.llm import llm_generate, LLM_AVAILABLE
from utils.text import chunk_text, build_prompt_from_history
from config import FALLBACK_TEXT
from utils.logger import logger

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory chat history store per session
CHAT_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
MAX_HISTORY_MESSAGES = 50


@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate-tts", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    try:
        if not TTS_AVAILABLE:
            return TTSResponse(audio_url="", message=FALLBACK_TEXT)
        audio_url = tts_generate(text=request.text, voice_id=request.voice_id)
        if audio_url:
            return TTSResponse(audio_url=audio_url, message="Audio generated successfully")
        return TTSResponse(audio_url="", message=FALLBACK_TEXT)
    except Exception as e:
        logger.exception("Murf TTS error")
        return TTSResponse(audio_url="", message=FALLBACK_TEXT)


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    file_location = UPLOAD_DIR / file.filename
    content = await file.read()
    with open(file_location, "wb") as f:
        f.write(content)
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
    }


@app.post("/transcribe/file")
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        if not STT_AVAILABLE:
            return {"transcript": None, "status": "unavailable"}
        audio_bytes = await file.read()
        transcript_text, status = stt_transcribe_bytes(audio_bytes)
        return {"transcript": transcript_text, "status": status}
    except Exception:
        logger.exception("Transcription error")
        return {"transcript": None, "status": "error"}


@app.get("/voices")
async def get_voices():
    try:
        if not TTS_AVAILABLE:
            return []
        return tts_get_voices()
    except Exception:
        logger.exception("Get voices error")
        return []


@app.post("/tts/echo")
async def tts_echo(file: UploadFile = File(...)):
    """Echo Bot v2: Transcribe audio and generate new audio with Murf voice"""
    try:
        transcribed_text = None
        if STT_AVAILABLE:
            try:
                audio_bytes = await file.read()
                transcript_text, status = stt_transcribe_bytes(audio_bytes)
                if status == "completed" and transcript_text:
                    transcribed_text = transcript_text.strip()
            except Exception:
                logger.exception("Transcription error (echo)")
        if not transcribed_text:
            return {"transcript": None, "audio_url": "", "message": FALLBACK_TEXT}
        if not TTS_AVAILABLE:
            return {"transcript": transcribed_text, "audio_url": "", "message": FALLBACK_TEXT}
        audio_url = tts_generate(text=transcribed_text, voice_id="en-US-natalie")
        if audio_url:
            return {
                "transcript": transcribed_text,
                "audio_url": audio_url,
                "message": "Audio transcribed and regenerated successfully",
            }
        return {"transcript": transcribed_text, "audio_url": "", "message": FALLBACK_TEXT}
    except Exception:
        logger.exception("Echo processing error")
        return {"transcript": None, "audio_url": "", "message": FALLBACK_TEXT}


@app.post("/llm/query", response_model=LLMQueryAudioResponse)
async def llm_query(
    request: Request,
    file: UploadFile | None = File(None),
    prompt: str | None = Form(None),
    model: str | None = Form(None),
    voice_id: str | None = Form("en-US-natalie"),
):
    """Text or audio input -> LLM -> optional TTS"""
    try:
        content_type = request.headers.get("content-type", "").lower()
        transcript_text: Optional[str] = None
        effective_prompt: Optional[str] = None
        model_name = model or "gemini-1.5-flash-8b"

        if "application/json" in content_type:
            body = await request.json()
            payload = LLMQueryRequest(**body)
            model_name = payload.model or model_name
            effective_prompt = payload.prompt
        else:
            if file is not None and STT_AVAILABLE:
                try:
                    audio_bytes = await file.read()
                    text, status = stt_transcribe_bytes(audio_bytes)
                    if status == "completed" and text:
                        transcript_text = text.strip()
                        effective_prompt = transcript_text
                except Exception:
                    logger.exception("Transcription error (llm_query)")
            if effective_prompt is None:
                if prompt is None or not prompt.strip():
                    return LLMQueryAudioResponse(
                        transcript_text=None,
                        llm_text=FALLBACK_TEXT,
                        model=model_name,
                        audio_urls=[],
                    )
                effective_prompt = prompt.strip()

        llm_text = None
        if LLM_AVAILABLE:
            try:
                llm_text = await llm_generate(model_name=model_name, prompt=effective_prompt)
            except Exception:
                logger.exception("LLM error")
        if not llm_text:
            llm_text = FALLBACK_TEXT

        audio_urls: List[str] = []
        if TTS_AVAILABLE and llm_text != FALLBACK_TEXT:
            try:
                for ch in chunk_text(llm_text, limit=3000):
                    url = tts_generate(text=ch, voice_id=voice_id or "en-US-natalie")
                    if url:
                        audio_urls.append(url)
            except Exception:
                logger.exception("TTS error (llm_query)")
                audio_urls = []

        return LLMQueryAudioResponse(
            transcript_text=transcript_text,
            llm_text=llm_text,
            model=model_name,
            audio_urls=audio_urls,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /llm/query")
        return LLMQueryAudioResponse(
            transcript_text=None,
            llm_text=FALLBACK_TEXT,
            model=(model or "gemini-1.5-flash-8b"),
            audio_urls=[],
        )


@app.post("/agent/chat/{session_id}", response_model=LLMQueryAudioResponse)
async def agent_chat(
    request: Request,
    session_id: str,
    file: UploadFile | None = File(None),
    prompt: str | None = Form(None),
    model: str | None = Form(None),
    voice_id: str | None = Form("en-US-natalie"),
):
    try:
        content_type = request.headers.get("content-type", "").lower()
        history = CHAT_HISTORY.get(session_id, [])

        transcript_text: Optional[str] = None
        effective_user_text: Optional[str] = None
        model_name = model or "gemini-1.5-flash-8b"

        if "application/json" in content_type:
            body = await request.json()
            payload = LLMQueryRequest(**body)
            model_name = payload.model or model_name
            effective_user_text = payload.prompt
        else:
            if file is not None and STT_AVAILABLE:
                try:
                    audio_bytes = await file.read()
                    text, status = stt_transcribe_bytes(audio_bytes)
                    if status == "completed" and text:
                        transcript_text = text.strip()
                        effective_user_text = transcript_text
                except Exception:
                    logger.exception("Transcription error (agent_chat)")
            if effective_user_text is None:
                if prompt is None or not prompt.strip():
                    return LLMQueryAudioResponse(
                        transcript_text=None,
                        llm_text=FALLBACK_TEXT,
                        model=model_name,
                        audio_urls=[],
                    )
                effective_user_text = prompt.strip()

        history.append({"role": "user", "content": effective_user_text, "ts": datetime.now().isoformat()})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        CHAT_HISTORY[session_id] = history

        full_prompt = build_prompt_from_history(history)
        llm_text = None
        if LLM_AVAILABLE:
            try:
                llm_text = await llm_generate(model_name=model_name, prompt=full_prompt)
            except Exception:
                logger.exception("LLM error (agent_chat)")
        if not llm_text:
            llm_text = FALLBACK_TEXT

        history.append({"role": "assistant", "content": llm_text, "ts": datetime.now().isoformat()})
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        CHAT_HISTORY[session_id] = history

        audio_urls: List[str] = []
        if TTS_AVAILABLE and llm_text != FALLBACK_TEXT:
            try:
                for ch in chunk_text(llm_text, limit=3000):
                    url = tts_generate(text=ch, voice_id=voice_id or "en-US-natalie")
                    if url:
                        audio_urls.append(url)
            except Exception:
                logger.exception("TTS error (agent_chat)")
                audio_urls = []

        return LLMQueryAudioResponse(
            transcript_text=transcript_text,
            llm_text=llm_text,
            model=model_name,
            audio_urls=audio_urls,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /agent/chat")
        return LLMQueryAudioResponse(
            transcript_text=None,
            llm_text=FALLBACK_TEXT,
            model=(model or "gemini-1.5-flash-8b"),
            audio_urls=[],
        )


@app.get("/agent/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(session_id: str):
    hist = CHAT_HISTORY.get(session_id, [])
    msgs: List[ChatMessage] = []
    for m in hist:
        msgs.append(
            ChatMessage(
                role=m.get("role", "user"),
                content=str(m.get("content", "")),
                ts=str(m.get("ts", "")),
            )
        )
    return ChatHistoryResponse(session_id=session_id, history=msgs)


@app.delete("/agent/history/{session_id}")
async def clear_history(session_id: str):
    CHAT_HISTORY[session_id] = []
    return {"session_id": session_id, "cleared": True}


# Simple echo WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Accept the WebSocket connection
    await ws.accept()
    try:
        while True:
            # Receive text from client
            msg = await ws.receive_text()
            # Echo back (you can also include timestamp)
            await ws.send_text(f"echo: {msg}")
    except WebSocketDisconnect:
        # Client disconnected gracefully
        pass
    except Exception:
        # Log unexpected errors and close socket
        logger.exception("WebSocket error")
        try:
            await ws.close()
        except Exception:
            pass


@app.websocket("/ws/audio")
async def websocket_audio(ws: WebSocket):
    """
    Receives 16 kHz, 16-bit, mono PCM audio frames from the browser and streams
    them to AssemblyAI's Streaming API. Transcripts are printed to the server
    console and also sent back to the client over the same WebSocket as text
    messages for optional UI display.
    """
    await ws.accept()
    print("\n✅ WebSocket audio connection established\n")

    # Import streaming function
    from services.stt import stream_transcribe

    # Session management
    session = None
    ws_open = True

    async def on_transcript_cb(text: str, end_of_turn: bool):
        """Callback to handle transcripts from AssemblyAI"""
        if not text:
            return
            
        # Check if WebSocket is still open
        if not ws_open:
            logger.warning("WebSocket closed, cannot send transcript")
            return
        
        try:
            # Send structured message to client with transcript type
            import json
            message = {
                "type": "transcript",
                "text": text,
                "is_final": end_of_turn,
                "end_of_turn": end_of_turn
            }
            
            # Send JSON message to client
            json_message = json.dumps(message)
            await ws.send_text(json_message)
            
            # Log what we're sending
            if end_of_turn:
                logger.info(f"📝 Final transcript sent to client: {text}")
                logger.info(f"🔚 End of turn notification sent to UI")
            else:
                logger.info(f"Interim transcript sent to client: {text[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send transcript to client: {e}")
            import traceback
            traceback.print_exc()

    try:
        # Get the current event loop for proper async handling
        loop = asyncio.get_event_loop()
        
        # Create AssemblyAI streaming session with event loop
        logger.info("Creating AssemblyAI streaming session...")
        session = await stream_transcribe(
            on_transcript=on_transcript_cb,
            loop=loop
        )
        
        if session is None:
            logger.error("Failed to create streaming session")
            error_msg = json.dumps({"type": "error", "message": "STT unavailable - check your ASSEMBLYAI_API_KEY"})
            await ws.send_text(error_msg)
            await ws.close()
            return
        
        logger.info("✅ Streaming session ready, waiting for audio...")
        print("\n🎤 Ready to receive audio from browser (16kHz, 16-bit PCM)\n")
        
        # Main loop to receive and forward audio
        while True:
            try:
                message = await ws.receive()
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                break
            except RuntimeError as e:
                if "disconnect" in str(e).lower():
                    logger.info("WebSocket disconnected")
                    break
                raise
            except Exception as e:
                logger.warning(f"Error receiving message: {e}")
                break
            
            # Handle text messages (control commands)
            if "text" in message:
                txt = message.get("text", "")
                if txt.strip().upper() == "EOF":
                    logger.info("Received EOF signal, closing session")
                    break
                # Ignore other text messages
                continue
            
            # Handle binary audio data
            if "bytes" in message:
                audio_data = message.get("bytes")
                if audio_data:
                    # Forward PCM16 audio to AssemblyAI
                    try:
                        await session.send_audio(audio_data)
                        # Only log occasionally to avoid spam
                        # logger.debug(f"Forwarding {len(audio_data)} bytes to AssemblyAI")
                    except Exception as e:
                        logger.error(f"Failed to send audio to AssemblyAI: {e}")
                        break
            else:
                logger.debug(f"Received message without audio data: {message.keys()}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client")
    except (ConnectionClosedError, ConnectionClosedOK):
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.exception(f"Unexpected error in WebSocket handler: {e}")
    finally:
        ws_open = False
        
        # Clean up AssemblyAI session
        if session is not None:
            try:
                logger.info("Closing AssemblyAI session...")
                await session.close()
            except Exception as e:
                logger.warning(f"Error closing AssemblyAI session: {e}")
        
        # Close WebSocket
        try:
            await ws.close()
        except Exception:
            pass
        
        print("\n❌ WebSocket audio connection closed\n")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"detail": str(exc)})
