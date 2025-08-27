"""
News Skill Handler
Parses natural language commands and fetches news headlines
"""

import re
from typing import Dict, Any, Optional, Tuple
from utils.logger import logger

# Import News service functions
from services.news import (
    NEWS_AVAILABLE,
    get_top_headlines,
    search_news,
    format_headlines_for_speech,
    format_headlines_detailed,
    NEWS_CATEGORIES
)

# Command patterns for natural language processing
NEWS_COMMAND_PATTERNS = {
    # General news requests
    "headlines": [
        r"(?:what(?:'s|'re| are) )?(?:the )?(?:latest |top |today's |current )?(?:news|headlines)(?:\?)?$",
        r"(?:give me |tell me |show me )?(?:the )?news(?:\?)?$",
        r"(?:what's |what is )?(?:happening|going on)(?: in the world| today)?(?:\?)?$",
        r"(?:read |get )(?:me )?(?:the )?(?:latest |top )?headlines(?:\?)?$",
        r"news update(?:s)?$",
        r"brief me(?: on the news)?$"
    ],
    # Category-specific news
    "category_news": [
        r"(?:what(?:'s|'re| are) )?(?:the )?(?:latest |top |today's )?(\w+) news(?:\?)?$",
        r"(?:give me |tell me |show me )?(?:the )?(\w+) (?:news|headlines)(?:\?)?$",
        r"(?:what's |what is )?(?:happening|new) in (\w+)(?:\?)?$",
        r"(?:read |get )(?:me )?(?:the )?(?:latest |top )?(\w+) headlines(?:\?)?$"
    ],
    # Search for specific news
    "search_news": [
        r"(?:search |find |look for |news about |headlines about )(.+)$",
        r"(?:what(?:'s|'re| are) )?(?:the )?(?:latest |recent )?news (?:about |on |regarding )(.+)(?:\?)?$",
        r"(?:tell me |show me |find me )(?:news |headlines |articles )(?:about |on |regarding )(.+)$",
        r"(.+) news$"  # Catch-all for "[topic] news"
    ],
    # Country-specific news
    "country_news": [
        r"(?:what(?:'s|'re| are) )?(?:the )?news (?:in |from )(.+)(?:\?)?$",
        r"(?:headlines |news )(?:from |in )(.+)$",
        r"(.+) (?:country )?headlines$"
    ]
}

# Country codes mapping
COUNTRY_CODES = {
    "united states": "us", "usa": "us", "america": "us", "us": "us",
    "united kingdom": "gb", "uk": "gb", "britain": "gb", "england": "gb",
    "india": "in", "canada": "ca", "australia": "au",
    "germany": "de", "france": "fr", "italy": "it", "spain": "es",
    "japan": "jp", "china": "cn", "russia": "ru", "brazil": "br",
    "mexico": "mx", "netherlands": "nl", "norway": "no", "sweden": "se",
    "switzerland": "ch", "belgium": "be", "austria": "at", "poland": "pl",
    "new zealand": "nz", "ireland": "ie", "singapore": "sg", "malaysia": "my",
    "south africa": "za", "egypt": "eg", "israel": "il", "saudi arabia": "sa",
    "uae": "ae", "argentina": "ar", "colombia": "co", "indonesia": "id",
    "south korea": "kr", "turkey": "tr", "ukraine": "ua", "portugal": "pt"
}

def extract_news_command(text: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Extract news command from natural language text
    Returns: (command_type, parameters)
    """
    if not text:
        return None, None
    
    text = text.lower().strip()
    
    # Remove common prefixes
    prefixes_to_remove = ["hey", "can you", "could you", "please", "would you", "i want", "i need"]
    for prefix in prefixes_to_remove:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    
    # Check for general headlines request
    for pattern in NEWS_COMMAND_PATTERNS["headlines"]:
        if re.match(pattern, text, re.IGNORECASE):
            logger.info("Detected general news headlines request")
            return "headlines", {"category": None, "limit": 5}
    
    # Check for category-specific news
    for pattern in NEWS_COMMAND_PATTERNS["category_news"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            category = match.group(1).lower()
            if category in NEWS_CATEGORIES:
                logger.info(f"Detected category news request: {category}")
                return "category_news", {"category": category, "limit": 5}
    
    # Check for country-specific news
    for pattern in NEWS_COMMAND_PATTERNS["country_news"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            country_name = match.group(1).lower()
            country_code = COUNTRY_CODES.get(country_name)
            if country_code:
                logger.info(f"Detected country news request: {country_name} ({country_code})")
                return "country_news", {"country": country_code, "limit": 5}
    
    # Check for news search
    for pattern in NEWS_COMMAND_PATTERNS["search_news"]:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            # Don't treat category names as search queries
            if query.lower() not in NEWS_CATEGORIES:
                logger.info(f"Detected news search: {query}")
                return "search_news", {"query": query, "limit": 5}
    
    # Check if it's a general news-related query
    news_keywords = ["news", "headline", "happening", "current events", "breaking", "latest"]
    if any(keyword in text for keyword in news_keywords):
        return "headlines", {"category": None, "limit": 5}
    
    return None, None

async def handle_news_command(command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Execute news command based on type and parameters
    Returns a response dictionary with success status and message
    """
    if not NEWS_AVAILABLE:
        return {
            "success": False,
            "message": "News service is not available. Please add your NewsAPI key to the .env file. You can get a free API key from newsapi.org",
            "articles": []
        }
    
    params = params or {}
    
    try:
        if command_type == "headlines":
            # Get general top headlines
            result = await get_top_headlines(
                category=params.get("category"),
                limit=params.get("limit", 5)
            )
            
        elif command_type == "category_news":
            # Get category-specific headlines
            category = params.get("category")
            result = await get_top_headlines(
                category=category,
                limit=params.get("limit", 5)
            )
            
        elif command_type == "country_news":
            # Get country-specific headlines
            country = params.get("country")
            result = await get_top_headlines(
                country=country,
                limit=params.get("limit", 5)
            )
            
        elif command_type == "search_news":
            # Search for specific news
            query = params.get("query", "")
            if query:
                result = await search_news(
                    query=query,
                    limit=params.get("limit", 5)
                )
            else:
                result = {
                    "success": False,
                    "message": "What news topic would you like me to search for?",
                    "articles": []
                }
        
        else:
            result = {
                "success": False,
                "message": f"I don't understand the news command: {command_type}",
                "articles": []
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Error handling news command: {e}")
        return {
            "success": False,
            "message": f"An error occurred while fetching news: {str(e)}",
            "articles": []
        }

def format_news_response(response: Dict[str, Any], persona_style: bool = True) -> str:
    """
    Format news command response for TTS output
    Makes responses more natural and conversational
    """
    if not response:
        return "I'm having trouble accessing the news right now."
    
    success = response.get("success", False)
    message = response.get("message", "")
    articles = response.get("articles", [])
    
    if not success:
        # Add personality to error messages (Tony Stark style)
        if persona_style:
            if "not available" in message.lower():
                return "News systems are offline. Apparently, someone forgot to configure the NewsAPI. Get a free key from newsapi.org - even I use their services."
            elif "rate limit" in message.lower():
                return "We've hit the news API rate limit. Too much curiosity for one day? Try again in a few minutes."
            elif "Invalid API key" in message:
                return "Invalid NewsAPI credentials detected. Someone's been tampering with the system. Check your API key."
        return message
    
    # Format successful response
    if articles:
        # Use the formatting function to create speech-friendly output
        formatted_text = format_headlines_for_speech(articles, include_description=False)
        
        if persona_style:
            # Add Tony Stark personality
            intro_phrases = [
                "Scanning global news networks... Here's what's making waves:",
                "I've tapped into the world's news feeds. Let me enlighten you:",
                "According to my sources - and they're always reliable -",
                "Fresh from the digital presses, here's your news briefing:",
                "I've filtered through thousands of articles. Here are the highlights:"
            ]
            
            import random
            intro = random.choice(intro_phrases)
            
            # Replace the generic intro in formatted_text
            if "Here are the top" in formatted_text:
                formatted_text = formatted_text.replace(
                    f"Here are the top {len(articles)} headlines:",
                    intro
                )
            
            # Add a closing remark
            closing_remarks = [
                "Stay informed, stay ahead.",
                "Knowledge is power - use it wisely.",
                "That's all for now. I'll keep monitoring the situation.",
                "Consider yourself briefed.",
                "And that's what's happening in your world."
            ]
            
            formatted_text += f"\n\n{random.choice(closing_remarks)}"
        
        return formatted_text
    else:
        if persona_style:
            return "Interesting... the news feeds are unusually quiet. Either nothing's happening, or someone's blocking my access. Try again later."
        return "No news articles found at the moment."

def is_news_command(text: str) -> bool:
    """
    Quick check if text contains news-related intent
    """
    if not text:
        return False
    
    text = text.lower()
    
    # Check for explicit news mentions
    news_keywords = [
        "news", "headline", "happening", "current events",
        "breaking", "latest", "what's new", "brief me",
        "update", "today's"
    ]
    
    # Check for news categories
    category_keywords = NEWS_CATEGORIES
    
    # Check if text contains news-related keywords
    has_news_keyword = any(keyword in text for keyword in news_keywords)
    
    # Check for patterns like "technology news" or "sports headlines"
    has_category_pattern = any(
        category in text and any(word in text for word in ["news", "headline", "update"])
        for category in category_keywords
    )
    
    return has_news_keyword or has_category_pattern
