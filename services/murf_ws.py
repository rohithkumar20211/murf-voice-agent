"""
Murf WebSocket client for real-time TTS streaming
"""
import asyncio
import json
import base64
from typing import Optional, Callable
import websockets
from utils.logger import logger
from config import MURF_API_KEY

MURF_WS_URL = "wss://api.murf.ai/v1/tts/stream"  # This is a hypothetical URL - adjust as needed


class MurfWebSocketClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or MURF_API_KEY
        self.websocket = None
        self.is_connected = False
        
    async def connect(self, voice_id: str = "en-US-natalie"):
        """Connect to Murf WebSocket API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "X-Voice-ID": voice_id
            }
            
            self.websocket = await websockets.connect(
                MURF_WS_URL,
                extra_headers=headers
            )
            self.is_connected = True
            logger.info("Connected to Murf WebSocket API")
            
            # Send initial configuration
            config_msg = {
                "type": "config",
                "voice_id": voice_id,
                "format": "mp3",
                "sample_rate": 16000
            }
            await self.websocket.send(json.dumps(config_msg))
            
        except Exception as e:
            logger.error(f"Failed to connect to Murf WebSocket: {e}")
            self.is_connected = False
            raise
            
    async def send_text(self, text: str):
        """Send text chunk to Murf for TTS conversion"""
        if not self.is_connected or not self.websocket:
            raise Exception("WebSocket not connected")
            
        try:
            message = {
                "type": "text",
                "content": text
            }
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent text to Murf: {text[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to send text to Murf: {e}")
            raise
            
    async def receive_audio(self) -> Optional[str]:
        """Receive base64 encoded audio from Murf"""
        if not self.is_connected or not self.websocket:
            return None
            
        try:
            message = await self.websocket.recv()
            data = json.loads(message)
            
            if data.get("type") == "audio":
                audio_base64 = data.get("audio")
                if audio_base64:
                    logger.debug(f"Received audio from Murf: {len(audio_base64)} bytes (base64)")
                    return audio_base64
                    
            elif data.get("type") == "error":
                logger.error(f"Murf error: {data.get('message')}")
                
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Murf WebSocket connection closed")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Failed to receive audio from Murf: {e}")
            
        return None
        
    async def stream_tts(self, text_generator, on_audio_callback: Callable = None):
        """
        Stream text to Murf and receive audio responses
        
        Args:
            text_generator: Async generator yielding text chunks
            on_audio_callback: Callback function to handle received audio (base64)
        """
        try:
            # Start receiver task
            receive_task = asyncio.create_task(self._receive_loop(on_audio_callback))
            
            # Send text chunks
            async for text_chunk in text_generator:
                if text_chunk:
                    await self.send_text(text_chunk)
                    
            # Send end-of-stream signal
            await self.websocket.send(json.dumps({"type": "end_of_stream"}))
            
            # Wait for all audio to be received
            await asyncio.sleep(2)  # Give time for final audio chunks
            
            # Cancel receiver task
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
                
        except Exception as e:
            logger.error(f"Error in stream_tts: {e}")
            raise
            
    async def _receive_loop(self, on_audio_callback: Callable = None):
        """Internal loop to continuously receive audio"""
        while self.is_connected:
            audio_base64 = await self.receive_audio()
            if audio_base64 and on_audio_callback:
                await on_audio_callback(audio_base64)
                
    async def close(self):
        """Close the WebSocket connection"""
        if self.websocket:
            try:
                await self.websocket.close()
                logger.info("Closed Murf WebSocket connection")
            except Exception as e:
                logger.warning(f"Error closing Murf WebSocket: {e}")
            finally:
                self.is_connected = False
                self.websocket = None


# Alternative implementation using HTTP streaming if WebSocket is not available
async def murf_streaming_tts(text: str, voice_id: str = "en-US-natalie") -> Optional[str]:
    """
    Function using Murf Python SDK with base64 encoding
    Returns base64 encoded audio
    """
    try:
        import base64
        import asyncio
        from services.tts import tts_generate
        
        # Use the existing tts_generate function which works with Murf SDK
        # Run it in a thread since it's synchronous
        audio_url = await asyncio.to_thread(tts_generate, text=text, voice_id=voice_id)
        
        if audio_url:
            # Download the audio from the URL and convert to base64
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(audio_url)
                if response.status_code == 200:
                    # Convert audio bytes to base64
                    audio_bytes = response.content
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                    logger.info(f"Received audio from Murf (converted to base64): {len(audio_base64)} bytes")
                    return audio_base64
                else:
                    logger.error(f"Failed to download audio from URL: {response.status_code}")
        else:
            logger.error("Failed to generate audio URL from Murf")
                
    except Exception as e:
        logger.error(f"Failed to generate TTS via Murf SDK: {e}")
        import traceback
        traceback.print_exc()
        
    return None
