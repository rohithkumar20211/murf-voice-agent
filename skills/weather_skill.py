"""
Weather Skill Handler
Parses natural language commands and fetches weather information
"""

import re
from typing import Dict, Any, Optional, Tuple
from utils.logger import logger

# Import Weather service functions
from services.weather import (
    WEATHER_AVAILABLE,
    get_current_weather,
    get_weather_forecast,
    get_air_quality,
    format_weather_for_speech,
    format_forecast_for_speech,
    format_air_quality_for_speech
)

# Command patterns for natural language processing
WEATHER_COMMAND_PATTERNS = {
    # Current weather requests
    "current_weather": [
        r"(?:what(?:'s|'re| is| are) )?(?:the )?(?:current |today's )?weather(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:how(?:'s| is) )?(?:the )?weather(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:what's |what is )?(?:it )?like (?:outside |out there )?(?:in (.+?))?(?:\?)?$",
        r"(?:is it |will it be )?(?:hot|cold|warm|cool|rainy|sunny|cloudy)(?:\s+(?:in|today in)\s+(.+?))?(?:\?)?$",
        r"temperature(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:give me |tell me |show me )?(?:the )?weather report(?:\s+(?:for|in)\s+(.+?))?(?:\?)?$"
    ],
    # Weather forecast requests
    "forecast": [
        r"(?:what(?:'s|'re| is| are) )?(?:the )?(?:weather )?forecast(?:\s+(?:for|in)\s+(.+?))?(?:\?)?$",
        r"(?:weather )?(?:for )?(?:the )?(?:next |upcoming )(?:few |couple of )?days(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:what )?(?:will |is )(?:the )?weather(?:\s+be)?(?: like)? tomorrow(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:will it |is it going to )?(?:rain|snow|be sunny|be cloudy) (?:tomorrow|this week)(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:give me |tell me |show me )?(?:a )?(?:\d+ )?day forecast(?:\s+(?:for|in)\s+(.+?))?(?:\?)?$"
    ],
    # Air quality requests
    "air_quality": [
        r"(?:what(?:'s|'re| is| are) )?(?:the )?air quality(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:how(?:'s| is) )?(?:the )?(?:air |air pollution )(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:is )?(?:the )?air (?:clean|safe|polluted)(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:check |get |show me )?(?:the )?(?:AQI|air quality index)(?:\s+(?:for|in)\s+(.+?))?(?:\?)?$",
        r"pollution (?:level |levels )?(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$"
    ],
    # Flight conditions (Tony Stark style)
    "flight_conditions": [
        r"(?:are |what are )?(?:the )?(?:flight |flying )conditions(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$",
        r"(?:is it |are conditions )?(?:good |safe )(?:for |to )?(?:fly|flying|take off)(?:\s+(?:in|from)\s+(.+?))?(?:\?)?$",
        r"(?:can I |should I )?(?:fly |take the suit out )(?:today )?(?:\s+(?:in|from)\s+(.+?))?(?:\?)?$",
        r"suit (?:flight )?conditions(?:\s+(?:in|for)\s+(.+?))?(?:\?)?$"
    ]
}

# Default city (can be configured)
DEFAULT_CITY = "New York"

def extract_weather_command(text: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Extract weather command from natural language text
    Returns: (command_type, parameters)
    """
    if not text:
        return None, None
    
    text = text.lower().strip()
    
    # Remove common prefixes
    prefixes_to_remove = ["hey", "jarvis", "arcnova", "can you", "could you", "please", 
                         "would you", "i want", "i need", "tell me", "show me", "give me"]
    for prefix in prefixes_to_remove:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    
    # Check for current weather request
    for pattern in WEATHER_COMMAND_PATTERNS["current_weather"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            city = match.group(1) if match.lastindex else None
            logger.info(f"Detected weather request for: {city or 'default location'}")
            return "current_weather", {"city": city or DEFAULT_CITY}
    
    # Check for forecast request
    for pattern in WEATHER_COMMAND_PATTERNS["forecast"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            city = match.group(1) if match.lastindex else None
            # Extract number of days if specified
            days_match = re.search(r"(\d+)\s*day", text)
            days = int(days_match.group(1)) if days_match else 3
            logger.info(f"Detected forecast request for: {city or 'default location'}")
            return "forecast", {"city": city or DEFAULT_CITY, "days": min(days, 5)}
    
    # Check for air quality request
    for pattern in WEATHER_COMMAND_PATTERNS["air_quality"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            city = match.group(1) if match.lastindex else None
            logger.info(f"Detected air quality request for: {city or 'default location'}")
            return "air_quality", {"city": city or DEFAULT_CITY}
    
    # Check for flight conditions (special Tony Stark feature)
    for pattern in WEATHER_COMMAND_PATTERNS["flight_conditions"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            city = match.group(1) if match.lastindex else None
            logger.info(f"Detected flight conditions request for: {city or 'default location'}")
            return "flight_conditions", {"city": city or DEFAULT_CITY}
    
    # Check for general weather-related keywords
    weather_keywords = ["weather", "temperature", "forecast", "rain", "snow", "sunny", 
                       "cloudy", "hot", "cold", "humidity", "wind", "storm"]
    if any(keyword in text for keyword in weather_keywords):
        # Try to extract city name
        city_match = re.search(r"(?:in|for|at)\s+([a-z\s]+?)(?:\?|$)", text)
        city = city_match.group(1).strip() if city_match else DEFAULT_CITY
        return "current_weather", {"city": city}
    
    return None, None

async def handle_weather_command(command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Execute weather command based on type and parameters
    Returns a response dictionary with success status and message
    """
    if not WEATHER_AVAILABLE:
        return {
            "success": False,
            "message": "Weather service is not available. Add your OpenWeatherMap API key to the .env file. You can get a free API key from openweathermap.org",
            "data": None
        }
    
    params = params or {}
    city = params.get("city", DEFAULT_CITY)
    
    try:
        if command_type == "current_weather":
            # Get current weather
            result = await get_current_weather(city)
            
        elif command_type == "forecast":
            # Get weather forecast
            days = params.get("days", 3)
            result = await get_weather_forecast(city, days)
            
        elif command_type == "air_quality":
            # Get air quality
            result = await get_air_quality(city)
            
        elif command_type == "flight_conditions":
            # Special command combining weather and air quality for flight assessment
            weather_result = await get_current_weather(city)
            air_result = await get_air_quality(city)
            
            if weather_result.get("success") and weather_result.get("data"):
                weather_data = weather_result["data"]
                air_data = air_result.get("data") if air_result.get("success") else None
                
                # Assess flight conditions
                conditions = assess_flight_conditions(weather_data, air_data)
                
                result = {
                    "success": True,
                    "message": "Flight conditions assessed",
                    "data": {
                        "weather": weather_data,
                        "air_quality": air_data,
                        "flight_assessment": conditions
                    }
                }
            else:
                result = weather_result
        
        else:
            result = {
                "success": False,
                "message": f"Unknown weather command: {command_type}",
                "data": None
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error handling weather command: {e}")
        return {
            "success": False,
            "message": f"An error occurred while fetching weather: {str(e)}",
            "data": None
        }

def assess_flight_conditions(weather_data: Dict[str, Any], air_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Assess flight conditions based on weather and air quality data
    Returns assessment with safety rating and recommendations
    """
    assessment = {
        "safe_to_fly": True,
        "rating": "Excellent",
        "concerns": [],
        "recommendations": []
    }
    
    # Check wind speed
    wind_speed = weather_data.get("wind_speed", 0)
    if wind_speed > 50:
        assessment["safe_to_fly"] = False
        assessment["concerns"].append(f"High winds at {wind_speed} km/h")
        assessment["recommendations"].append("Ground the suit - winds too strong")
    elif wind_speed > 30:
        assessment["rating"] = "Moderate"
        assessment["concerns"].append(f"Moderate winds at {wind_speed} km/h")
        assessment["recommendations"].append("Expect turbulence, engage stabilizers")
    
    # Check visibility
    visibility = weather_data.get("visibility", 10)
    if visibility < 1:
        assessment["safe_to_fly"] = False
        assessment["concerns"].append(f"Poor visibility at {visibility} km")
        assessment["recommendations"].append("Use enhanced sensors and HUD")
    elif visibility < 5:
        assessment["rating"] = "Moderate"
        assessment["concerns"].append(f"Limited visibility at {visibility} km")
    
    # Check weather conditions
    condition = weather_data.get("condition", "").lower()
    if "thunderstorm" in condition:
        assessment["safe_to_fly"] = False
        assessment["concerns"].append("Thunderstorm activity detected")
        assessment["recommendations"].append("Avoid flight - electrical interference risk")
    elif "snow" in condition or "rain" in condition:
        assessment["rating"] = "Moderate" if assessment["rating"] == "Excellent" else assessment["rating"]
        assessment["concerns"].append(f"Precipitation: {weather_data.get('description', condition)}")
        assessment["recommendations"].append("Activate weather shielding")
    
    # Check temperature
    temp = weather_data.get("temperature", 20)
    if temp < -20 or temp > 45:
        assessment["rating"] = "Poor"
        assessment["concerns"].append(f"Extreme temperature: {temp}°C")
        assessment["recommendations"].append("Check thermal systems before flight")
    
    # Check air quality if available
    if air_data:
        aqi = air_data.get("aqi", 1)
        if aqi >= 4:
            assessment["rating"] = "Poor" if assessment["rating"] != "Poor" else assessment["rating"]
            assessment["concerns"].append(f"Poor air quality: {air_data.get('aqi_label', 'Unknown')}")
            assessment["recommendations"].append("Seal the suit, use internal oxygen")
    
    # Final rating adjustment
    if not assessment["safe_to_fly"]:
        assessment["rating"] = "Dangerous"
    elif len(assessment["concerns"]) == 0:
        assessment["rating"] = "Perfect"
    elif len(assessment["concerns"]) <= 2 and assessment["rating"] == "Excellent":
        assessment["rating"] = "Good"
    
    return assessment

def format_weather_response(response: Dict[str, Any], persona_style: bool = True) -> str:
    """
    Format weather command response for TTS output with Tony Stark personality
    """
    if not response:
        return "Weather systems are offline. Someone needs to check the satellite connection."
    
    success = response.get("success", False)
    message = response.get("message", "")
    data = response.get("data", None)
    
    if not success:
        # Add personality to error messages
        if persona_style:
            if "not available" in message.lower():
                return "Weather systems are offline. Get an API key from OpenWeatherMap - even a genius needs data access."
            elif "not found" in message.lower():
                return "That city doesn't exist in my database. Did you spell it correctly? I'm a genius, not a mind reader."
            elif "rate limit" in message.lower():
                return "We've exceeded the weather API rate limit. Apparently, even I have limits."
        return message
    
    # Format successful responses based on data type
    if data:
        # Check if it's flight conditions data
        if "flight_assessment" in data:
            assessment = data["flight_assessment"]
            weather = data.get("weather", {})
            
            response_text = f"Flight conditions for {weather.get('city', 'your location')}: "
            
            if assessment["rating"] == "Perfect":
                response_text += "Perfect conditions for flight. Clear skies, minimal wind. The suit is ready when you are. "
            elif assessment["rating"] == "Excellent":
                response_text += "Excellent flying weather. Minor factors to consider but nothing the suit can't handle. "
            elif assessment["rating"] == "Good":
                response_text += "Good conditions overall. A few things to watch out for. "
            elif assessment["rating"] == "Moderate":
                response_text += "Moderate conditions. Proceed with caution. "
            elif assessment["rating"] == "Poor":
                response_text += "Poor conditions for flight. I'd recommend postponing. "
            else:  # Dangerous
                response_text += "Dangerous conditions! Absolutely not safe to fly. "
            
            if assessment["concerns"]:
                response_text += "Concerns: " + ", ".join(assessment["concerns"]) + ". "
            
            if assessment["recommendations"]:
                response_text += "My recommendations: " + ". ".join(assessment["recommendations"]) + ". "
            
            if persona_style:
                if assessment["safe_to_fly"]:
                    response_text += "The Mark 85 is prepped and ready. Your call, boss."
                else:
                    response_text += "I strongly advise keeping the suit in the garage today."
            
            return response_text
        
        # Check if it's forecast data
        elif "forecasts" in data:
            formatted_text = format_forecast_for_speech(data)
            if persona_style:
                formatted_text = f"Accessing weather satellites... {formatted_text} "
                formatted_text += "Plan accordingly - I don't control the weather. Yet."
            return formatted_text
        
        # Check if it's air quality data
        elif "aqi" in data:
            formatted_text = format_air_quality_for_speech(data)
            if persona_style:
                aqi_label = data.get("aqi_label", "Unknown")
                if aqi_label == "Good":
                    formatted_text += " Perfect for a test flight."
                elif aqi_label in ["Poor", "Very Poor"]:
                    formatted_text += " I'd keep the helmet sealed if I were you."
            return formatted_text
        
        # Regular weather data
        else:
            formatted_text = format_weather_for_speech(data)
            if persona_style:
                temp = data.get("temperature", 0)
                condition = data.get("condition", "").lower()
                
                # Add Tony Stark comments
                if temp < 0:
                    formatted_text += " The arc reactor should keep you warm, but maybe grab a jacket for appearances."
                elif temp > 35:
                    formatted_text += " The suit's cooling system will come in handy today."
                
                if "clear" in condition:
                    formatted_text += " Perfect visibility for a high-altitude flight."
                elif "rain" in condition:
                    formatted_text += " The suit's hydrophobic coating will keep you dry."
                elif "snow" in condition:
                    formatted_text += " Time to test the de-icing systems."
            
            return formatted_text
    
    return "Weather data unavailable. Check the satellite uplink."

def is_weather_command(text: str) -> bool:
    """
    Quick check if text contains weather-related intent
    """
    if not text:
        return False
    
    text = text.lower()
    
    # Check for weather-related keywords
    weather_keywords = [
        "weather", "temperature", "forecast", "rain", "snow", "sunny",
        "cloudy", "hot", "cold", "warm", "cool", "humidity", "wind",
        "storm", "air quality", "aqi", "pollution", "flight conditions",
        "visibility", "pressure", "sunrise", "sunset", "celsius", "fahrenheit"
    ]
    
    # Check for weather questions
    weather_questions = [
        "what's the weather", "how's the weather", "is it raining",
        "will it rain", "is it hot", "is it cold", "what's it like outside"
    ]
    
    # Check if text contains weather-related keywords or questions
    has_weather_keyword = any(keyword in text for keyword in weather_keywords)
    has_weather_question = any(question in text for question in weather_questions)
    
    return has_weather_keyword or has_weather_question
