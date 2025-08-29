import asyncio
import json
from typing import Optional, Dict, Any

from utils.logger import logger
from personas import is_greeting, get_persona_greeting, get_persona_system_prompt

LLM_AVAILABLE = False
_initialized = False

def initialize_llm():
    """Initialize or reinitialize LLM with current API key"""
    global LLM_AVAILABLE, _initialized
    
    # Import here to avoid circular dependency
    from api_config import get_api_key
    
    api_key = get_api_key("GEMINI_API_KEY")
    
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            LLM_AVAILABLE = True
            _initialized = True
            logger.info("Gemini LLM initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to configure Gemini LLM: {e}")
            LLM_AVAILABLE = False
            _initialized = False
    else:
        logger.warning("GEMINI_API_KEY not configured; LLM disabled")
        LLM_AVAILABLE = False
        _initialized = False
    
    return LLM_AVAILABLE

def reinitialize_llm():
    """Reinitialize LLM with potentially new API key"""
    return initialize_llm()

# Initialize on module load
initialize_llm()


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
        
        # Check if it's a Weather command
        try:
            from skills.weather_skill import is_weather_command, extract_weather_command, handle_weather_command, format_weather_response
            
            if is_weather_command(prompt):
                command_type, params = extract_weather_command(prompt)
                if command_type:
                    # Execute the Weather command
                    result = await handle_weather_command(command_type, params)
                    # Format the response with personality
                    return format_weather_response(result)
        except ImportError:
            logger.warning("Weather skill not available")
        except Exception as e:
            logger.error(f"Error handling Weather command: {e}")
    
    try:
        import google.generativeai as genai
        
        # Enhanced system prompt to understand News and Weather commands
        enhanced_persona = get_persona_system_prompt() + """
        
You can also fetch news headlines and weather information for the user. 
For news: If they ask about news, current events, headlines, or what's happening in the world.
For weather: If they ask about weather, temperature, forecast, air quality, or flight conditions.
You have access to real-time data from various sources. Respond in character but be informative."""
        
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
        
        # Check if it's a Weather command
        try:
            from skills.weather_skill import is_weather_command, extract_weather_command, handle_weather_command, format_weather_response
            
            if is_weather_command(prompt):
                command_type, params = extract_weather_command(prompt)
                if command_type:
                    # Execute the Weather command
                    result = await handle_weather_command(command_type, params)
                    # Format and stream the response
                    response_text = format_weather_response(result)
                    
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
            logger.warning("Weather skill not available")
        except Exception as e:
            logger.error(f"Error handling Weather command: {e}")
    
    try:
        import google.generativeai as genai
        
        # Enhanced system prompt to understand News and Weather commands
        enhanced_persona = get_persona_system_prompt() + """
        
You can also fetch news headlines and weather information for the user. 
For news: If they ask about news, current events, headlines, or what's happening in the world.
For weather: If they ask about weather, temperature, forecast, air quality, or flight conditions.
You have access to real-time data from various sources. Respond in character but be informative."""
        
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

