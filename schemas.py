from typing import List, Optional
from pydantic import BaseModel


class TTSRequest(BaseModel):
    text: str
    voice_id: str = "en-US-natalie"


class TTSResponse(BaseModel):
    audio_url: str
    message: str


class LLMQueryRequest(BaseModel):
    prompt: str
    model: Optional[str] = "gemini-1.5-flash-8b"


class LLMQueryAudioResponse(BaseModel):
    transcript_text: Optional[str] = None
    llm_text: str
    model: str
    audio_urls: List[str]


class ChatMessage(BaseModel):
    role: str
    content: str
    ts: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    history: List[ChatMessage]

