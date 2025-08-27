import asyncio
import json
from typing import Optional, Dict, Any

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


async def llm_generate(model_name: str, prompt: str, handle_spotify: bool = True) -> Optional[str]:
    if not LLM_AVAILABLE:
        return None
    
    # Check if the prompt is just a greeting (for simple query endpoint)
    if is_greeting(prompt):
        return get_persona_greeting()
    
    # Check if it's a News command
    if handle_spotify:  # Reusing the parameter name for backward compatibility
        try:
            from skills.news_skill import is_news_command, extract_news_command, handle_news_command, format_news_response
            
            if is_news_command(prompt):
                command_type, params = extract_news_command(prompt)
                if command_type:
                    # Execute the News command
                    result = await handle_news_command(command_type, params)
                    # Format the response with personality
                    return format_news_response(result)
        except ImportError:
            logger.warning("News skill not available")
        except Exception as e:
            logger.error(f"Error handling News command: {e}")
    
    try:
        import google.generativeai as genai
        
        # Enhanced system prompt to understand News commands
        enhanced_persona = get_persona_system_prompt() + """
        
You can also fetch news headlines for the user. If they ask about news, current events, headlines, 
or what's happening in the world, acknowledge their request naturally. You have access to news from 
various categories and countries. Respond in character but be informative."""
        
        # If it's a simple prompt without system context, add the persona
        if not prompt.startswith("System:"):
            prompt = f"System: {enhanced_persona}\n\nUser: {prompt}\nAssistant:"
        
        llm_model = genai.GenerativeModel(model_name)
        result = await asyncio.to_thread(llm_model.generate_content, prompt)
        return (getattr(result, "text", None) or "").strip()
    except Exception as e:
        logger.warning(f"LLM error: {e}")
        return None


async def llm_generate_stream(model_name: str, prompt: str, handle_spotify: bool = True):
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
    
    # Check if it's a News command
    if handle_spotify:  # Reusing the parameter name for backward compatibility
        try:
            from skills.news_skill import is_news_command, extract_news_command, handle_news_command, format_news_response
            
            if is_news_command(prompt):
                command_type, params = extract_news_command(prompt)
                if command_type:
                    # Execute the News command
                    result = await handle_news_command(command_type, params)
                    # Format and stream the response
                    response_text = format_news_response(result)
                    
                    # Stream the response in chunks
                    words = response_text.split()
                    for i in range(0, len(words), 3):
                        chunk = ' '.join(words[i:i+3])
                        if i + 3 < len(words):
                            chunk += ' '
                        yield chunk
                        await asyncio.sleep(0.05)  # Small delay for natural streaming
                    return
        except ImportError:
            logger.warning("News skill not available")
        except Exception as e:
            logger.error(f"Error handling News command: {e}")
    
    try:
        import google.generativeai as genai
        
        # Enhanced system prompt to understand News commands
        enhanced_persona = get_persona_system_prompt() + """
        
You can also fetch news headlines for the user. If they ask about news, current events, headlines, 
or what's happening in the world, acknowledge their request naturally. You have access to news from 
various categories and countries. Respond in character but be informative."""
        
        # If it's a simple prompt without system context, add the persona
        if not prompt.startswith("System:"):
            prompt = f"System: {enhanced_persona}\n\nUser: {prompt}\nAssistant:"
        
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

