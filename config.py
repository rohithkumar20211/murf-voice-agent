import os
from dotenv import load_dotenv

load_dotenv()

# Fallback text used when any API fails
FALLBACK_TEXT = "I'm having trouble connecting right now. Please try again."

# API Keys
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
MURF_API_KEY = os.getenv("MURF_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# NewsAPI Configuration
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_COUNTRY = os.getenv("NEWS_COUNTRY", "us")  # Default country for news
NEWS_LANGUAGE = os.getenv("NEWS_LANGUAGE", "en")  # Default language

