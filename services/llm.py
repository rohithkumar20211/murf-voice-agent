import asyncio
from typing import Optional

from utils.logger import logger
from config import GEMINI_API_KEY
from personas import is_greeting, get_persona_greeting, get_persona_system_prompt

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
    
    # Check if the prompt is just a greeting (for simple query endpoint)
    if is_greeting(prompt):
        return get_persona_greeting()
    
    try:
        import google.generativeai as genai
        
        # If it's a simple prompt without system context, add the persona
        if not prompt.startswith("System:"):
            prompt = f"System: {get_persona_system_prompt()}\n\nUser: {prompt}\nAssistant:"
        
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
    
    # Check if the prompt is just a greeting
    if is_greeting(prompt):
        # Stream the greeting in chunks for a more natural feel
        greeting = get_persona_greeting()
        words = greeting.split()
        for i in range(0, len(words), 3):
            chunk = ' '.join(words[i:i+3])
            if i + 3 < len(words):
                chunk += ' '
            yield chunk
            await asyncio.sleep(0.1)  # Small delay for natural streaming
        return
    
    try:
        import google.generativeai as genai
        
        # If it's a simple prompt without system context, add the persona
        if not prompt.startswith("System:"):
            prompt = f"System: {get_persona_system_prompt()}\n\nUser: {prompt}\nAssistant:"
        
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

