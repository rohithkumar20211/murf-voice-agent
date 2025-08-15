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

