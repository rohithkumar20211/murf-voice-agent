"""
Weather Service Module
Fetches weather data and air quality using OpenWeatherMap API
"""

import os
from typing import Optional, Dict, Any
from datetime import datetime
import httpx
from utils.logger import logger

# Weather availability will be checked dynamically
WEATHER_AVAILABLE = False
_api_key = None

def initialize_weather():
    """Initialize or reinitialize Weather service with current API key"""
    global WEATHER_AVAILABLE, _api_key
    
    # Import here to avoid circular dependency
    from api_config import get_api_key
    
    _api_key = get_api_key("OPENWEATHER_API_KEY")
    WEATHER_AVAILABLE = bool(_api_key)
    
    if WEATHER_AVAILABLE:
        logger.info("Weather service initialized with OpenWeatherMap API")
    else:
        logger.warning("Weather service not available - OPENWEATHER_API_KEY not configured")
    
    return WEATHER_AVAILABLE

def reinitialize_weather():
    """Reinitialize Weather service with potentially new API key"""
    return initialize_weather()

# Initialize on module load
initialize_weather()

# OpenWeatherMap endpoints
WEATHER_API_BASE_URL = "https://api.openweathermap.org/data/2.5"
CURRENT_WEATHER_ENDPOINT = f"{WEATHER_API_BASE_URL}/weather"
FORECAST_ENDPOINT = f"{WEATHER_API_BASE_URL}/forecast"
AIR_POLLUTION_ENDPOINT = f"{WEATHER_API_BASE_URL}/air_pollution"
GEOCODING_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"

# Weather condition emoji mapping
WEATHER_EMOJIS = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧️",
    "Drizzle": "🌦️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Mist": "🌫️",
    "Haze": "🌫️",
    "Fog": "🌫️"
}

# Air Quality Index levels
AQI_LEVELS = {
    1: ("Good", "🟢"),
    2: ("Fair", "🟡"),
    3: ("Moderate", "🟠"),
    4: ("Poor", "🔴"),
    5: ("Very Poor", "🟣")
}

def check_weather_availability() -> bool:
    """Check if Weather service is properly configured"""
    if not _api_key:
        logger.warning("OpenWeatherMap API key not configured. Weather features disabled.")
        return False
    return True

async def get_coordinates(city_name: str, country_code: Optional[str] = None) -> Optional[tuple]:
    """
    Get coordinates for a city name using geocoding API
    
    Args:
        city_name: Name of the city
        country_code: Optional 2-letter country code (US, GB, etc.)
    
    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    if not WEATHER_AVAILABLE:
        return None
    
    try:
        params = {
            "q": f"{city_name},{country_code}" if country_code else city_name,
            "limit": 1,
            "appid": _api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(GEOCODING_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data:
                location = data[0]
                return (location.get("lat"), location.get("lon"))
            
            return None
            
    except Exception as e:
        logger.error(f"Failed to get coordinates for {city_name}: {e}")
        return None

async def get_current_weather(city: str, country_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch current weather for a city
    
    Args:
        city: City name
        country_code: Optional 2-letter country code
    
    Returns:
        Dictionary with weather data and success status
    """
    if not WEATHER_AVAILABLE:
        return {
            "success": False,
            "message": "Weather service is not available. Please configure your OpenWeatherMap API key.",
            "data": None
        }
    
    try:
        params = {
            "q": f"{city},{country_code}" if country_code else city,
            "appid": _api_key,
            "units": "metric"  # Use Celsius
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(CURRENT_WEATHER_ENDPOINT, params=params)
            
            if response.status_code == 404:
                return {
                    "success": False,
                    "message": f"City '{city}' not found. Please check the city name.",
                    "data": None
                }
            
            response.raise_for_status()
            data = response.json()
            
            # Format the weather data
            weather_info = {
                "city": data.get("name", city),
                "country": data.get("sys", {}).get("country", ""),
                "temperature": round(data.get("main", {}).get("temp", 0)),
                "feels_like": round(data.get("main", {}).get("feels_like", 0)),
                "condition": data.get("weather", [{}])[0].get("main", "Unknown"),
                "description": data.get("weather", [{}])[0].get("description", ""),
                "humidity": data.get("main", {}).get("humidity", 0),
                "pressure": data.get("main", {}).get("pressure", 0),
                "wind_speed": round(data.get("wind", {}).get("speed", 0) * 3.6, 1),  # Convert m/s to km/h
                "wind_direction": data.get("wind", {}).get("deg", 0),
                "visibility": data.get("visibility", 0) / 1000,  # Convert to km
                "clouds": data.get("clouds", {}).get("all", 0),
                "sunrise": datetime.fromtimestamp(data.get("sys", {}).get("sunrise", 0)).strftime("%H:%M"),
                "sunset": datetime.fromtimestamp(data.get("sys", {}).get("sunset", 0)).strftime("%H:%M"),
                "coordinates": {
                    "lat": data.get("coord", {}).get("lat", 0),
                    "lon": data.get("coord", {}).get("lon", 0)
                }
            }
            
            return {
                "success": True,
                "message": f"Weather data retrieved for {weather_info['city']}",
                "data": weather_info
            }
            
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}"
        if e.response.status_code == 401:
            error_msg = "Invalid API key. Please check your OpenWeatherMap credentials."
        elif e.response.status_code == 429:
            error_msg = "Rate limit exceeded. Please try again later."
        
        logger.error(f"OpenWeatherMap HTTP error: {e}")
        return {
            "success": False,
            "message": error_msg,
            "data": None
        }
    except Exception as e:
        logger.error(f"Failed to fetch weather: {e}")
        return {
            "success": False,
            "message": f"Error fetching weather: {str(e)}",
            "data": None
        }

async def get_weather_forecast(city: str, days: int = 5) -> Dict[str, Any]:
    """
    Fetch weather forecast for a city (5 day / 3 hour forecast)
    
    Args:
        city: City name
        days: Number of days to forecast (max 5)
    
    Returns:
        Dictionary with forecast data and success status
    """
    if not WEATHER_AVAILABLE:
        return {
            "success": False,
            "message": "Weather service is not available.",
            "data": None
        }
    
    try:
        params = {
            "q": city,
            "appid": _api_key,
            "units": "metric",
            "cnt": min(days * 8, 40)  # 8 forecasts per day (3-hour intervals)
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(FORECAST_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Group forecasts by day
            daily_forecasts = {}
            for item in data.get("list", []):
                date = datetime.fromtimestamp(item.get("dt", 0)).strftime("%Y-%m-%d")
                if date not in daily_forecasts:
                    daily_forecasts[date] = {
                        "date": date,
                        "day": datetime.fromtimestamp(item.get("dt", 0)).strftime("%A"),
                        "temperatures": [],
                        "conditions": [],
                        "descriptions": []
                    }
                
                daily_forecasts[date]["temperatures"].append(item.get("main", {}).get("temp", 0))
                daily_forecasts[date]["conditions"].append(item.get("weather", [{}])[0].get("main", ""))
                daily_forecasts[date]["descriptions"].append(item.get("weather", [{}])[0].get("description", ""))
            
            # Calculate daily summaries
            forecast_summary = []
            for date, day_data in list(daily_forecasts.items())[:days]:
                temps = day_data["temperatures"]
                # Most common weather condition
                most_common_condition = max(set(day_data["conditions"]), key=day_data["conditions"].count)
                
                forecast_summary.append({
                    "date": date,
                    "day": day_data["day"],
                    "min_temp": round(min(temps)),
                    "max_temp": round(max(temps)),
                    "avg_temp": round(sum(temps) / len(temps)),
                    "condition": most_common_condition,
                    "emoji": WEATHER_EMOJIS.get(most_common_condition, "🌡️")
                })
            
            return {
                "success": True,
                "message": f"Forecast retrieved for {data.get('city', {}).get('name', city)}",
                "data": {
                    "city": data.get("city", {}).get("name", city),
                    "country": data.get("city", {}).get("country", ""),
                    "forecasts": forecast_summary
                }
            }
            
    except Exception as e:
        logger.error(f"Failed to fetch forecast: {e}")
        return {
            "success": False,
            "message": f"Error fetching forecast: {str(e)}",
            "data": None
        }

async def get_air_quality(city: str) -> Dict[str, Any]:
    """
    Fetch air quality data for a city
    
    Args:
        city: City name
    
    Returns:
        Dictionary with air quality data and success status
    """
    if not WEATHER_AVAILABLE:
        return {
            "success": False,
            "message": "Weather service is not available.",
            "data": None
        }
    
    try:
        # First get coordinates for the city
        coords = await get_coordinates(city)
        if not coords:
            return {
                "success": False,
                "message": f"Could not find coordinates for {city}",
                "data": None
            }
        
        lat, lon = coords
        
        params = {
            "lat": lat,
            "lon": lon,
            "appid": _api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(AIR_POLLUTION_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("list"):
                air_data = data["list"][0]
                aqi = air_data.get("main", {}).get("aqi", 0)
                components = air_data.get("components", {})
                
                aqi_label, aqi_emoji = AQI_LEVELS.get(aqi, ("Unknown", "❓"))
                
                air_quality_info = {
                    "city": city,
                    "aqi": aqi,
                    "aqi_label": aqi_label,
                    "aqi_emoji": aqi_emoji,
                    "components": {
                        "co": round(components.get("co", 0), 2),  # Carbon monoxide
                        "no2": round(components.get("no2", 0), 2),  # Nitrogen dioxide
                        "o3": round(components.get("o3", 0), 2),  # Ozone
                        "pm2_5": round(components.get("pm2_5", 0), 2),  # Fine particles
                        "pm10": round(components.get("pm10", 0), 2),  # Coarse particles
                        "so2": round(components.get("so2", 0), 2)  # Sulfur dioxide
                    }
                }
                
                return {
                    "success": True,
                    "message": f"Air quality data retrieved for {city}",
                    "data": air_quality_info
                }
            
            return {
                "success": False,
                "message": "No air quality data available",
                "data": None
            }
            
    except Exception as e:
        logger.error(f"Failed to fetch air quality: {e}")
        return {
            "success": False,
            "message": f"Error fetching air quality: {str(e)}",
            "data": None
        }

def format_weather_for_speech(weather_data: Dict[str, Any], include_details: bool = True) -> str:
    """
    Format weather data for text-to-speech output
    
    Args:
        weather_data: Weather data dictionary
        include_details: Whether to include detailed information
    
    Returns:
        Formatted string ready for TTS
    """
    if not weather_data:
        return "No weather data available."
    
    city = weather_data.get("city", "Unknown")
    temp = weather_data.get("temperature", 0)
    feels_like = weather_data.get("feels_like", 0)
    condition = weather_data.get("condition", "Unknown")
    description = weather_data.get("description", "")
    humidity = weather_data.get("humidity", 0)
    wind_speed = weather_data.get("wind_speed", 0)
    
    formatted_text = f"Current weather in {city}: "
    formatted_text += f"{temp} degrees Celsius with {description}. "
    
    if abs(temp - feels_like) > 3:
        formatted_text += f"Feels like {feels_like} degrees. "
    
    if include_details:
        formatted_text += f"Humidity is {humidity} percent. "
        if wind_speed > 0:
            formatted_text += f"Wind speed is {wind_speed} kilometers per hour. "
        
        # Add weather advice
        if temp < 5:
            formatted_text += "It's quite cold, dress warmly. "
        elif temp > 30:
            formatted_text += "It's hot outside, stay hydrated. "
        
        if "rain" in description.lower():
            formatted_text += "Don't forget an umbrella. "
        elif "snow" in description.lower():
            formatted_text += "Be careful on the roads. "
    
    return formatted_text.strip()

def format_forecast_for_speech(forecast_data: Dict[str, Any]) -> str:
    """
    Format weather forecast for text-to-speech output
    
    Args:
        forecast_data: Forecast data dictionary
    
    Returns:
        Formatted string ready for TTS
    """
    if not forecast_data or not forecast_data.get("forecasts"):
        return "No forecast data available."
    
    city = forecast_data.get("city", "your location")
    forecasts = forecast_data.get("forecasts", [])[:3]  # Limit to 3 days for speech
    
    formatted_text = f"Weather forecast for {city}: "
    
    for i, day in enumerate(forecasts):
        day_name = day.get("day", "")
        min_temp = day.get("min_temp", 0)
        max_temp = day.get("max_temp", 0)
        condition = day.get("condition", "")
        
        if i == 0:
            formatted_text += f"Tomorrow, "
        else:
            formatted_text += f"{day_name}, "
        
        formatted_text += f"{condition} with temperatures from {min_temp} to {max_temp} degrees. "
    
    return formatted_text.strip()

def format_air_quality_for_speech(air_data: Dict[str, Any]) -> str:
    """
    Format air quality data for text-to-speech output
    
    Args:
        air_data: Air quality data dictionary
    
    Returns:
        Formatted string ready for TTS
    """
    if not air_data:
        return "No air quality data available."
    
    city = air_data.get("city", "your location")
    aqi_label = air_data.get("aqi_label", "Unknown")
    pm25 = air_data.get("components", {}).get("pm2_5", 0)
    
    formatted_text = f"Air quality in {city} is {aqi_label}. "
    
    if aqi_label == "Good":
        formatted_text += "The air is clean and safe for all activities. "
    elif aqi_label == "Fair":
        formatted_text += "Air quality is acceptable for most people. "
    elif aqi_label == "Moderate":
        formatted_text += "Sensitive individuals should limit prolonged outdoor activity. "
    elif aqi_label in ["Poor", "Very Poor"]:
        formatted_text += "Everyone should avoid outdoor activities. Consider using air purification indoors. "
    
    if pm25 > 35:
        formatted_text += f"Fine particle levels are elevated at {pm25} micrograms per cubic meter. "
    
    return formatted_text.strip()

# Module initialization complete
