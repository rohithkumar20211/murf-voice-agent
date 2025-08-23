import asyncio
from typing import Optional

from utils.logger import logger
from config import GEMINI_API_KEY

LLM_AVAILABLE = False

try:
    if GEMINI_API_KEY:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        LLM_AVAILABLE = True
    else:
        logger.warning("GEMINI_API_KEY not set; LLM disabled")
except Exception as e:
    logger.warning(f"Failed to configure Gemini LLM: {e}")
    LLM_AVAILABLE = False


async def llm_generate(model_name: str, prompt: str) -> Optional[str]:
    if not LLM_AVAILABLE:
        return None
    try:
        import google.generativeai as genai

        llm_model = genai.GenerativeModel(model_name)
        result = await asyncio.to_thread(llm_model.generate_content, prompt)
        return (getattr(result, "text", None) or "").strip()
    except Exception as e:
        logger.warning(f"LLM error: {e}")
        return None


async def llm_generate_stream(model_name: str, prompt: str):
    """Generate LLM response with streaming support.
    
    Yields text chunks as they arrive from the LLM API.
    """
    if not LLM_AVAILABLE:
        yield None
        return
    
    try:
        import google.generativeai as genai
        
        llm_model = genai.GenerativeModel(model_name)
        
        # Generate content with streaming enabled
        response = await asyncio.to_thread(
            llm_model.generate_content,
            prompt,
            stream=True
        )
        
        # Yield chunks as they arrive
        for chunk in response:
            if hasattr(chunk, 'text') and chunk.text:
                yield chunk.text
                
    except Exception as e:
        logger.error(f"LLM streaming error: {e}")
        yield None

