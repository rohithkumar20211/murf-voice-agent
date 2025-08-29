"""
API Configuration Manager
Handles dynamic API key configuration with user-provided keys taking priority over environment variables
"""

import os
import json
from typing import Dict, Optional, Any
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import logger

# Load environment variables
load_dotenv()

# Configuration file path
CONFIG_FILE = Path("user_config.json")

# API key names
API_KEYS = {
    "GEMINI_API_KEY": "Google Gemini AI",
    "ASSEMBLYAI_API_KEY": "AssemblyAI Speech-to-Text",
    "MURF_API_KEY": "Murf Text-to-Speech",
    "NEWS_API_KEY": "News API",
    "OPENWEATHER_API_KEY": "OpenWeatherMap"
}

class APIConfigManager:
    """Manages API configuration with user overrides"""
    
    def __init__(self):
        self._env_keys = {}
        self._user_keys = {}
        self._load_env_keys()
        self._load_user_config()
    
    def _load_env_keys(self):
        """Load API keys from environment variables"""
        for key_name in API_KEYS:
            value = os.getenv(key_name)
            if value:
                self._env_keys[key_name] = value
                logger.info(f"Loaded {key_name} from environment")
    
    def _load_user_config(self):
        """Load user-provided API keys from config file"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self._user_keys = config.get('api_keys', {})
                    logger.info(f"Loaded {len(self._user_keys)} user API keys from config")
            except Exception as e:
                logger.error(f"Failed to load user config: {e}")
                self._user_keys = {}
    
    def save_user_config(self, api_keys: Dict[str, str]):
        """Save user-provided API keys to config file"""
        try:
            # Filter out empty values
            filtered_keys = {k: v for k, v in api_keys.items() if v and v.strip()}
            
            config = {
                'api_keys': filtered_keys,
                'version': '1.0'
            }
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            
            self._user_keys = filtered_keys
            logger.info(f"Saved {len(filtered_keys)} user API keys to config")
            return True
        except Exception as e:
            logger.error(f"Failed to save user config: {e}")
            return False
    
    def get_api_key(self, key_name: str) -> Optional[str]:
        """Get API key with user override priority"""
        # User-provided keys take priority
        if key_name in self._user_keys and self._user_keys[key_name]:
            return self._user_keys[key_name]
        
        # Fall back to environment variables
        if key_name in self._env_keys:
            return self._env_keys[key_name]
        
        return None
    
    def get_all_keys(self) -> Dict[str, Optional[str]]:
        """Get all API keys with their current values"""
        result = {}
        for key_name in API_KEYS:
            result[key_name] = self.get_api_key(key_name)
        return result
    
    def get_config_status(self) -> Dict[str, Any]:
        """Get configuration status for all services"""
        status = {}
        for key_name, service_name in API_KEYS.items():
            key_value = self.get_api_key(key_name)
            status[key_name] = {
                'name': service_name,
                'configured': bool(key_value),
                'source': 'user' if key_name in self._user_keys else 'env' if key_name in self._env_keys else None,
                'masked_value': self._mask_api_key(key_value) if key_value else None
            }
        return status
    
    def _mask_api_key(self, key: str) -> str:
        """Mask API key for display"""
        if not key or len(key) < 8:
            return '*' * 8
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
    
    def validate_api_key(self, key_name: str, key_value: str) -> Dict[str, Any]:
        """Validate an API key by attempting to use it"""
        result = {'valid': False, 'message': 'Unknown key type'}
        
        if key_name == 'GEMINI_API_KEY':
            result = self._validate_gemini_key(key_value)
        elif key_name == 'ASSEMBLYAI_API_KEY':
            result = self._validate_assemblyai_key(key_value)
        elif key_name == 'MURF_API_KEY':
            result = self._validate_murf_key(key_value)
        elif key_name == 'NEWS_API_KEY':
            result = self._validate_news_key(key_value)
        elif key_name == 'OPENWEATHER_API_KEY':
            result = self._validate_weather_key(key_value)
        
        return result
    
    def _validate_gemini_key(self, key: str) -> Dict[str, Any]:
        """Validate Google Gemini API key"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash-8b')
            # Try a simple generation
            response = model.generate_content("Hello")
            if response:
                return {'valid': True, 'message': 'Gemini API key is valid'}
        except Exception as e:
            return {'valid': False, 'message': f'Invalid Gemini key: {str(e)[:100]}'}
        
        return {'valid': False, 'message': 'Failed to validate Gemini key'}
    
    def _validate_assemblyai_key(self, key: str) -> Dict[str, Any]:
        """Validate AssemblyAI API key"""
        try:
            import requests
            headers = {'authorization': key}
            response = requests.get('https://api.assemblyai.com/v2/account', headers=headers)
            if response.status_code == 200:
                return {'valid': True, 'message': 'AssemblyAI API key is valid'}
            else:
                return {'valid': False, 'message': f'Invalid AssemblyAI key: Status {response.status_code}'}
        except Exception as e:
            return {'valid': False, 'message': f'Failed to validate AssemblyAI key: {str(e)[:100]}'}
    
    def _validate_murf_key(self, key: str) -> Dict[str, Any]:
        """Validate Murf API key"""
        # Murf validation would require testing with their API
        # For now, just check if it looks valid
        if key and len(key) > 10 and key.startswith('ap2_'):
            return {'valid': True, 'message': 'Murf API key format appears valid'}
        return {'valid': False, 'message': 'Invalid Murf API key format'}
    
    def _validate_news_key(self, key: str) -> Dict[str, Any]:
        """Validate News API key"""
        try:
            import requests
            response = requests.get(f'https://newsapi.org/v2/top-headlines?country=us&apiKey={key}')
            if response.status_code == 200:
                return {'valid': True, 'message': 'News API key is valid'}
            else:
                return {'valid': False, 'message': f'Invalid News API key: Status {response.status_code}'}
        except Exception as e:
            return {'valid': False, 'message': f'Failed to validate News key: {str(e)[:100]}'}
    
    def _validate_weather_key(self, key: str) -> Dict[str, Any]:
        """Validate OpenWeatherMap API key"""
        try:
            import requests
            response = requests.get(f'https://api.openweathermap.org/data/2.5/weather?q=London&appid={key}')
            if response.status_code == 200:
                return {'valid': True, 'message': 'OpenWeather API key is valid'}
            else:
                return {'valid': False, 'message': f'Invalid OpenWeather key: Status {response.status_code}'}
        except Exception as e:
            return {'valid': False, 'message': f'Failed to validate Weather key: {str(e)[:100]}'}
    
    def clear_user_config(self):
        """Clear all user-provided API keys"""
        self._user_keys = {}
        if CONFIG_FILE.exists():
            try:
                CONFIG_FILE.unlink()
                logger.info("Cleared user configuration")
            except Exception as e:
                logger.error(f"Failed to clear config file: {e}")

# Global instance
api_config = APIConfigManager()

# Helper functions for backward compatibility
def get_api_key(key_name: str) -> Optional[str]:
    """Get an API key with user override priority"""
    return api_config.get_api_key(key_name)

def get_all_api_keys() -> Dict[str, Optional[str]]:
    """Get all API keys"""
    return api_config.get_all_keys()

def save_api_keys(keys: Dict[str, str]) -> bool:
    """Save user-provided API keys"""
    return api_config.save_user_config(keys)

def get_config_status() -> Dict[str, Any]:
    """Get configuration status"""
    return api_config.get_config_status()