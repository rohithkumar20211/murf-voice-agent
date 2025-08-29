import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Body
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
from utils.logger import logger
from config import FALLBACK_TEXT
from personas import get_persona_voice
from api_config import api_config, get_api_key, save_api_keys, get_config_status

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory chat history store per session
CHAT_HISTORY: Dict[str, List[Dict[str, Any]]] = {}
MAX_HISTORY_MESSAGES = 50

USER_API_KEYS = {}

@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/config")
async def save_api_keys(payload: dict = Body(...)):
    murf_key = payload.get("murfKey")
    assembly_key = payload.get("assemblyKey")
    gemini_key = payload.get("geminiKey")
    news_key = payload.get("newsKey")
    weather_key = payload.get("weatherKey")
    # You can make all keys required, or just some
    if not murf_key or not assembly_key or not gemini_key or not news_key or not weather_key:
        return {"success": False, "detail": "All keys required"}
    USER_API_KEYS["murf"] = murf_key
    USER_API_KEYS["assembly"] = assembly_key
    USER_API_KEYS["gemini"] = gemini_key
    USER_API_KEYS["news"] = news_key
    USER_API_KEYS["weather"] = weather_key
    return {"success": True}


@app.post("/generate-tts", response_model=TTSResponse)
async def generate_tts(request: TTSRequest):
    try:
        murf_api_key = USER_API_KEYS.get("murf")
        if not murf_api_key:
            return TTSResponse(audio_url="", message="Murf API key not set")
        audio_url = tts_generate(text=request.text, voice_id=request.voice_id, api_key=murf_api_key)
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
        audio_url = tts_generate(text=transcribed_text, voice_id=get_persona_voice())
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
    voice_id: str | None = Form(None),
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
                    url = tts_generate(text=ch, voice_id=voice_id or get_persona_voice())
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
    voice_id: str | None = Form(None),
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
                    url = tts_generate(text=ch, voice_id=voice_id or get_persona_voice())
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


# News endpoints
@app.get("/news/headlines")
async def get_news_headlines(category: Optional[str] = None, country: Optional[str] = None):
    """Get latest news headlines"""
    try:
        from services.news import get_top_headlines, format_headlines_detailed
        
        result = await get_top_headlines(category=category, country=country, limit=5)
        
        if result.get("success"):
            articles = result.get("articles", [])
            detailed_text = format_headlines_detailed(articles)
            return {
                "success": True,
                "formatted_text": detailed_text,
                "articles": articles,
                "total": result.get("total_results", 0)
            }
        else:
            return result
            
    except Exception as e:
        logger.exception("News headlines error")
        return {"success": False, "message": str(e), "articles": []}


@app.post("/news/search")
async def search_news(request: Request):
    """Search for news articles"""
    try:
        body = await request.json()
        query = body.get("query", "")
        
        if not query:
            return {"success": False, "message": "Query is required", "articles": []}
        
        from services.news import search_news as search_news_func
        
        result = await search_news_func(query=query, limit=5)
        return result
        
    except Exception as e:
        logger.exception("News search error")
        return {"success": False, "message": str(e), "articles": []}


@app.post("/news/command")
async def news_command(request: Request):
    """Process a natural language news command"""
    try:
        body = await request.json()
        command_text = body.get("command", "")
        
        from skills.news_skill import extract_news_command, handle_news_command, format_news_response
        
        command_type, params = extract_news_command(command_text)
        if command_type:
            result = await handle_news_command(command_type, params)
            return {
                "success": result.get("success", False),
                "message": format_news_response(result),
                "articles": result.get("articles", []),
                "raw_response": result
            }
        else:
            return {
                "success": False,
                "message": "Not recognized as a news command. Try 'What's the latest news?' or 'Technology headlines'",
                "articles": []
            }
            
    except Exception as e:
        logger.exception("News command error")
        return {"success": False, "message": str(e), "articles": []}


@app.get("/news/status")
async def news_status():
    """Check news service status"""
    try:
        from services.news import NEWS_AVAILABLE, NEWS_CATEGORIES
        
        return {
            "available": NEWS_AVAILABLE,
            "categories": NEWS_CATEGORIES,
            "message": "News service is ready" if NEWS_AVAILABLE else "News service not configured. Add NEWS_API_KEY to .env"
        }
        
    except Exception as e:
        logger.exception("News status error")
        return {"available": False, "error": str(e)}


# Weather endpoints
@app.get("/weather/current")
async def get_weather(city: Optional[str] = None, country: Optional[str] = None):
    """Get current weather for a city"""
    try:
        from services.weather import get_current_weather, format_weather_for_speech
        from config import DEFAULT_WEATHER_CITY
        
        city = city or DEFAULT_WEATHER_CITY
        result = await get_current_weather(city, country)
        
        if result.get("success"):
            weather_data = result.get("data")
            speech_text = format_weather_for_speech(weather_data)
            return {
                "success": True,
                "formatted_text": speech_text,
                "data": weather_data,
                "message": result.get("message")
            }
        else:
            return result
            
    except Exception as e:
        logger.exception("Weather current error")
        return {"success": False, "message": str(e), "data": None}


@app.get("/weather/forecast")
async def get_forecast(city: Optional[str] = None, days: Optional[int] = 3):
    """Get weather forecast for a city"""
    try:
        from services.weather import get_weather_forecast, format_forecast_for_speech
        from config import DEFAULT_WEATHER_CITY
        
        city = city or DEFAULT_WEATHER_CITY
        result = await get_weather_forecast(city, days)
        
        if result.get("success"):
            forecast_data = result.get("data")
            speech_text = format_forecast_for_speech(forecast_data)
            return {
                "success": True,
                "formatted_text": speech_text,
                "data": forecast_data,
                "message": result.get("message")
            }
        else:
            return result
            
    except Exception as e:
        logger.exception("Weather forecast error")
        return {"success": False, "message": str(e), "data": None}


@app.get("/weather/air-quality")
async def get_air(city: Optional[str] = None):
    """Get air quality for a city"""
    try:
        from services.weather import get_air_quality, format_air_quality_for_speech
        from config import DEFAULT_WEATHER_CITY
        
        city = city or DEFAULT_WEATHER_CITY
        result = await get_air_quality(city)
        
        if result.get("success"):
            air_data = result.get("data")
            speech_text = format_air_quality_for_speech(air_data)
            return {
                "success": True,
                "formatted_text": speech_text,
                "data": air_data,
                "message": result.get("message")
            }
        else:
            return result
            
    except Exception as e:
        logger.exception("Air quality error")
        return {"success": False, "message": str(e), "data": None}


@app.post("/weather/command")
async def weather_command(request: Request):
    """Process a natural language weather command"""
    try:
        body = await request.json()
        command_text = body.get("command", "")
        
        from skills.weather_skill import extract_weather_command, handle_weather_command, format_weather_response
        
        command_type, params = extract_weather_command(command_text)
        if command_type:
            result = await handle_weather_command(command_type, params)
            return {
                "success": result.get("success", False),
                "message": format_weather_response(result),
                "data": result.get("data"),
                "raw_response": result
            }
        else:
            return {
                "success": False,
                "message": "Not recognized as a weather command. Try 'What's the weather?' or 'Weather forecast for London'",
                "data": None
            }
            
    except Exception as e:
        logger.exception("Weather command error")
        return {"success": False, "message": str(e), "data": None}


@app.get("/weather/status")
async def weather_status():
    """Check weather service status"""
    try:
        from services.weather import WEATHER_AVAILABLE
        
        return {
            "available": WEATHER_AVAILABLE,
            "message": "Weather service is ready" if WEATHER_AVAILABLE else "Weather service not configured. Add OPENWEATHER_API_KEY to .env"
        }
        
    except Exception as e:
        logger.exception("Weather status error")
        return {"available": False, "error": str(e)}


# API Configuration endpoints
@app.get("/config/status")
async def get_api_config_status():
    """Get current API configuration status"""
    try:
        return {
            "success": True,
            "config": get_config_status()
        }
    except Exception as e:
        logger.exception("Config status error")
        return {"success": False, "error": str(e)}


@app.post("/config/save")
async def save_api_config(request: Request):
    """Save user-provided API keys"""
    try:
        body = await request.json()
        api_keys = body.get("api_keys", {})
        
        # Save the configuration
        success = save_api_keys(api_keys)
        
        if success:
            # Reload services with new keys
            from services import llm, stt, tts, news, weather
            
            # Reinitialize services with new keys
            llm.reinitialize_llm()
            stt.reinitialize_stt()
            tts.reinitialize_tts()
            news.reinitialize_news()
            weather.reinitialize_weather()
            
            return {
                "success": True,
                "message": "API configuration saved and services reloaded",
                "config": get_config_status()
            }
        else:
            return {
                "success": False,
                "message": "Failed to save configuration"
            }
    except Exception as e:
        logger.exception("Save config error")
        return {"success": False, "error": str(e)}


@app.post("/config/validate")
async def validate_api_key(request: Request):
    """Validate a single API key"""
    try:
        body = await request.json()
        key_name = body.get("key_name")
        key_value = body.get("key_value")
        
        if not key_name or not key_value:
            return {
                "success": False,
                "message": "Missing key_name or key_value"
            }
        
        result = api_config.validate_api_key(key_name, key_value)
        return {
            "success": result.get("valid", False),
            "message": result.get("message", "Unknown error")
        }
    except Exception as e:
        logger.exception("Validate key error")
        return {"success": False, "error": str(e)}


@app.delete("/config/clear")
async def clear_api_config():
    """Clear all user-provided API keys"""
    try:
        api_config.clear_user_config()
        return {
            "success": True,
            "message": "User configuration cleared"
        }
    except Exception as e:
        logger.exception("Clear config error")
        return {"success": False, "error": str(e)}


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

    # Session management - extract from query params
    session_id = None
    try:
        # Get session ID from query params if available
        query_params = ws.url.query
        if query_params:
            import urllib.parse
            params = urllib.parse.parse_qs(query_params)
            if 'session' in params:
                session_id = params['session'][0]
                print(f"📝 Using session ID: {session_id}")
    except Exception as e:
        logger.warning(f"Could not extract session ID: {e}")
    
    # Session management
    session = None
    ws_open = True
    last_transcript = ""  # Track last transcript to avoid duplicates
    processing_llm = False  # Flag to prevent concurrent LLM processing
    last_transcript_time = 0  # Track timestamp of last processed transcript

    async def on_transcript_cb(text: str, end_of_turn: bool):
        """Callback to handle transcripts from AssemblyAI"""
        nonlocal last_transcript, processing_llm, last_transcript_time
        
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
            
            # Only process final transcripts and avoid duplicates
            if end_of_turn:
                import time
                current_time = time.time()
                
                # Check if this is essentially the same as the last transcript (case-insensitive)
                # Also check if text is too short or similar to avoid processing noise
                normalized_text = text.lower().strip()
                
                # Skip if same text was processed within last 2 seconds (duplicate detection)
                time_since_last = current_time - last_transcript_time
                is_duplicate_text = normalized_text == last_transcript.lower().strip()
                is_too_soon = time_since_last < 2.0  # 2 second debounce
                
                if normalized_text and len(normalized_text) > 2:
                    if is_duplicate_text and is_too_soon:
                        logger.info(f"Skipping duplicate transcript (within {time_since_last:.1f}s): {text}")
                    elif not processing_llm:
                        # New transcript or enough time has passed
                        processing_llm = True
                        last_transcript = text
                        last_transcript_time = current_time
                        # Generate and stream LLM response when end of turn is detected
                        await process_llm_response(text, ws, ws_open, session_id)
                        processing_llm = False
                    else:
                        logger.info(f"Already processing LLM, skipping: {text}")
            # Remove interim transcript logging for cleaner output
        except Exception as e:
            logger.error(f"Failed to send transcript to client: {e}")
            import traceback
            traceback.print_exc()
    
    async def process_llm_response(transcript: str, websocket: WebSocket, socket_open: bool, session_id: str = None):
        """Process the final transcript with LLM and stream the response with Murf TTS"""
        if not LLM_AVAILABLE:
            return
        
        try:
            from services.llm import llm_generate_stream
            from services.murf_ws import MurfWebSocketClient, murf_streaming_tts
            from datetime import datetime
            
            # Clean console output - just show user query
            print(f"\n👤 USER: {transcript}")
            
            # Save user message to chat history if session_id provided
            if session_id:
                if session_id not in CHAT_HISTORY:
                    CHAT_HISTORY[session_id] = []
                CHAT_HISTORY[session_id].append({
                    "role": "user",
                    "content": transcript,
                    "ts": datetime.now().isoformat()
                })
                # Trim history if too long
                if len(CHAT_HISTORY[session_id]) > MAX_HISTORY_MESSAGES:
                    CHAT_HISTORY[session_id] = CHAT_HISTORY[session_id][-MAX_HISTORY_MESSAGES:]
            
            # Send LLM start message to client
            if socket_open:
                start_msg = json.dumps({
                    "type": "llm_start",
                    "message": "Generating response..."
                })
                await websocket.send_text(start_msg)
            
            # Accumulate the full response for console logging
            accumulated_response = ""
            model_name = "gemini-1.5-flash-8b"  # Default model
            voice_id = get_persona_voice()  # Use persona's voice
            
            # Initialize Murf WebSocket client
            murf_client = None
            use_murf_ws = False  # Disabled as Murf doesn't provide WebSocket API
            
            # Skip WebSocket connection attempt since Murf doesn't support it
            # We'll use HTTP fallback instead
            
            
            text_chunks_for_tts = []
            
            
            async for chunk in llm_generate_stream(model_name, transcript):
                if chunk is None:
                    break
                
                
                accumulated_response += chunk
                text_chunks_for_tts.append(chunk)
                
                
                if murf_client and murf_client.is_connected:
                    try:
                        await murf_client.send_text(chunk)
                    except Exception as e:
                        logger.error(f"Failed to send text to Murf: {e}")
                
                
                if socket_open:
                    try:
                        chunk_msg = json.dumps({
                            "type": "llm_chunk",
                            "text": chunk
                        })
                        await websocket.send_text(chunk_msg)
                    except Exception as e:
                        break
            
            # Print only the final response in a clean format
            print(f"\n🤖 ASSISTANT: {accumulated_response}")
            
            # Save assistant response to chat history if session_id provided
            if session_id and accumulated_response:
                CHAT_HISTORY[session_id].append({
                    "role": "assistant",
                    "content": accumulated_response,
                    "ts": datetime.now().isoformat()
                })
                # Trim history if too long
                if len(CHAT_HISTORY[session_id]) > MAX_HISTORY_MESSAGES:
                    CHAT_HISTORY[session_id] = CHAT_HISTORY[session_id][-MAX_HISTORY_MESSAGES:]
            
            # Handle TTS audio generation and reception
            if murf_client and murf_client.is_connected:
                try:
                    # Signal end of text stream to Murf
                    await murf_client.websocket.send(json.dumps({"type": "end_of_stream"}))
                    
                    # Receive audio chunks from Murf
                    print("\n📢 Receiving audio from Murf WebSocket...")
                    audio_chunks_received = 0
                    
                    while True:
                        audio_base64 = await asyncio.wait_for(
                            murf_client.receive_audio(), 
                            timeout=5.0
                        )
                        if audio_base64:
                            audio_chunks_received += 1
                            # Print base64 audio to console as requested
                            print(f"\n🔊 Base64 Audio Chunk {audio_chunks_received} (length: {len(audio_base64)} bytes):")
                            print(f"{audio_base64[:200]}..." if len(audio_base64) > 200 else audio_base64)
                            
                            # Send audio to client if needed
                            if socket_open:
                                try:
                                    audio_msg = json.dumps({
                                        "type": "tts_audio",
                                        "audio_base64": audio_base64,
                                        "chunk_index": audio_chunks_received
                                    })
                                    await websocket.send_text(audio_msg)
                                except Exception as e:
                                    logger.error(f"Failed to send audio to client: {e}")
                        else:
                            break
                    
                    print(f"\n✅ Received {audio_chunks_received} audio chunks from Murf")
                    
                except asyncio.TimeoutError:
                    logger.info("Finished receiving audio from Murf (timeout)")
                except Exception as e:
                    logger.error(f"Error receiving audio from Murf: {e}")
                finally:
                    # Close Murf connection
                    if murf_client:
                        await murf_client.close()
            
            # Fallback: Use HTTP-based TTS if WebSocket not available
            elif TTS_AVAILABLE and accumulated_response and accumulated_response != FALLBACK_TEXT:
                try:
                    print("\n📢 Using HTTP-based TTS fallback...")
                    
                    # Option to control chunking behavior
                    USE_SINGLE_AUDIO = True  # Set to True for single audio response, False for chunked streaming
                    
                    if USE_SINGLE_AUDIO:
                        # Generate single audio for entire response (up to 3000 chars)
                        truncated_response = accumulated_response[:3000]  # Limit to prevent API errors
                        if len(accumulated_response) > 3000:
                            print(f"\n⚠️ Response truncated from {len(accumulated_response)} to 3000 chars for single audio")
                        
                        audio_base64 = await murf_streaming_tts(
                            text=truncated_response,
                            voice_id=voice_id
                        )
                        if audio_base64:
                            # Print base64 audio to console
                            print(f"\n🔊 Single Audio Response (length: {len(audio_base64)} bytes):")
                            print(f"{audio_base64[:200]}..." if len(audio_base64) > 200 else audio_base64)
                            
                            # Send to client
                            if socket_open:
                                try:
                                    audio_msg = json.dumps({
                                        "type": "tts_audio",
                                        "audio_base64": audio_base64,
                                        "chunk_index": 1
                                    })
                                    await websocket.send_text(audio_msg)
                                except Exception as e:
                                    logger.error(f"Failed to send audio to client: {e}")
                    else:
                        # Split long text into chunks for better streaming
                        from utils.text import chunk_text
                        text_chunks = list(chunk_text(accumulated_response, limit=500))  # Smaller chunks for better streaming
                        
                        print(f"\n📄 Split response into {len(text_chunks)} chunks for TTS")
                        
                        for idx, text_chunk in enumerate(text_chunks, 1):
                            audio_base64 = await murf_streaming_tts(
                                text=text_chunk,
                                voice_id=voice_id
                            )
                            if audio_base64:
                                # Print base64 audio to console
                                print(f"\n🔊 Base64 Audio Chunk {idx}/{len(text_chunks)} (length: {len(audio_base64)} bytes):")
                                print(f"{audio_base64[:200]}..." if len(audio_base64) > 200 else audio_base64)
                                
                                # Send to client
                                if socket_open:
                                    try:
                                        audio_msg = json.dumps({
                                            "type": "tts_audio",
                                            "audio_base64": audio_base64,
                                            "chunk_index": idx
                                        })
                                        await websocket.send_text(audio_msg)
                                        # Small delay between chunks to allow processing
                                        await asyncio.sleep(0.1)
                                    except Exception as e:
                                        logger.error(f"Failed to send audio chunk {idx} to client: {e}")
                                        break
                except Exception as e:
                    logger.error(f"HTTP TTS fallback failed: {e}")
            
            # Send completion message to client
            if socket_open:
                try:
                    complete_msg = json.dumps({
                        "type": "llm_complete",
                        "full_response": accumulated_response
                    })
                    await websocket.send_text(complete_msg)
                except Exception as e:
                    pass
            
        except Exception as e:
            logger.error(f"Error processing LLM response: {e}")
            import traceback
            traceback.print_exc()
            
            # Send error message to client
            if socket_open:
                try:
                    error_msg = json.dumps({
                        "type": "llm_error",
                        "message": "Failed to generate response"
                    })
                    await websocket.send_text(error_msg)
                except:
                    pass

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


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Voice Agent Server...")
    print("📍 Open http://127.0.0.1:8000 in your browser")
    print("🎤 Make sure to allow microphone access when prompted\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
