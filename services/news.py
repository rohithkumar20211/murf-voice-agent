"""
News Service Module
Fetches latest news headlines using NewsAPI
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from utils.logger import logger
from config import NEWS_API_KEY, NEWS_COUNTRY, NEWS_LANGUAGE

# Check if News service is available
NEWS_AVAILABLE = bool(NEWS_API_KEY)

# NewsAPI endpoints
NEWS_API_BASE_URL = "https://newsapi.org/v2"
TOP_HEADLINES_ENDPOINT = f"{NEWS_API_BASE_URL}/top-headlines"
EVERYTHING_ENDPOINT = f"{NEWS_API_BASE_URL}/everything"

# News categories
NEWS_CATEGORIES = [
    "business", "entertainment", "general", "health", 
    "science", "sports", "technology"
]

def check_news_availability() -> bool:
    """Check if News service is properly configured"""
    if not NEWS_API_KEY:
        logger.warning("News API key not configured. News features disabled.")
        return False
    return True

async def get_top_headlines(
    category: Optional[str] = None,
    country: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Fetch top news headlines
    
    Args:
        category: News category (business, technology, etc.)
        country: Country code (us, gb, in, etc.)
        query: Search query for headlines
        limit: Maximum number of headlines to return
    
    Returns:
        Dictionary with success status and headlines
    """
    if not NEWS_AVAILABLE:
        return {
            "success": False,
            "message": "News service is not available. Please configure your NewsAPI key.",
            "articles": []
        }
    
    try:
        params = {
            "apiKey": NEWS_API_KEY,
            "pageSize": limit,
            "country": country or NEWS_COUNTRY
        }
        
        if category and category.lower() in NEWS_CATEGORIES:
            params["category"] = category.lower()
        
        if query:
            params["q"] = query
            # Remove country filter when searching with query
            params.pop("country", None)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(TOP_HEADLINES_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") != "ok":
                return {
                    "success": False,
                    "message": data.get("message", "Failed to fetch news"),
                    "articles": []
                }
            
            articles = data.get("articles", [])
            
            # Format articles for better presentation
            formatted_articles = []
            for article in articles[:limit]:
                formatted_article = {
                    "title": article.get("title", "No title"),
                    "description": article.get("description", ""),
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "url": article.get("url", ""),
                    "published_at": article.get("publishedAt", ""),
                    "author": article.get("author", "")
                }
                formatted_articles.append(formatted_article)
            
            return {
                "success": True,
                "message": f"Found {len(formatted_articles)} headlines",
                "articles": formatted_articles,
                "total_results": data.get("totalResults", 0)
            }
            
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}"
        if e.response.status_code == 401:
            error_msg = "Invalid API key. Please check your NewsAPI credentials."
        elif e.response.status_code == 429:
            error_msg = "Rate limit exceeded. Please try again later."
        
        logger.error(f"NewsAPI HTTP error: {e}")
        return {
            "success": False,
            "message": error_msg,
            "articles": []
        }
    except Exception as e:
        logger.error(f"Failed to fetch headlines: {e}")
        return {
            "success": False,
            "message": f"Error fetching news: {str(e)}",
            "articles": []
        }

async def search_news(
    query: str,
    sort_by: str = "popularity",
    language: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Search for news articles
    
    Args:
        query: Search query
        sort_by: Sort order (relevancy, popularity, publishedAt)
        language: Language code (en, es, fr, etc.)
        limit: Maximum number of articles to return
    
    Returns:
        Dictionary with success status and articles
    """
    if not NEWS_AVAILABLE:
        return {
            "success": False,
            "message": "News service is not available. Please configure your NewsAPI key.",
            "articles": []
        }
    
    try:
        params = {
            "apiKey": NEWS_API_KEY,
            "q": query,
            "sortBy": sort_by,
            "pageSize": limit,
            "language": language or NEWS_LANGUAGE
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(EVERYTHING_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") != "ok":
                return {
                    "success": False,
                    "message": data.get("message", "Failed to search news"),
                    "articles": []
                }
            
            articles = data.get("articles", [])
            
            # Format articles
            formatted_articles = []
            for article in articles[:limit]:
                formatted_article = {
                    "title": article.get("title", "No title"),
                    "description": article.get("description", ""),
                    "source": article.get("source", {}).get("name", "Unknown"),
                    "url": article.get("url", ""),
                    "published_at": article.get("publishedAt", ""),
                    "author": article.get("author", "")
                }
                formatted_articles.append(formatted_article)
            
            return {
                "success": True,
                "message": f"Found {len(formatted_articles)} articles about '{query}'",
                "articles": formatted_articles,
                "total_results": data.get("totalResults", 0)
            }
            
    except Exception as e:
        logger.error(f"Failed to search news: {e}")
        return {
            "success": False,
            "message": f"Error searching news: {str(e)}",
            "articles": []
        }

def format_headlines_for_speech(articles: List[Dict[str, Any]], include_description: bool = False) -> str:
    """
    Format news headlines for text-to-speech output
    
    Args:
        articles: List of article dictionaries
        include_description: Whether to include article descriptions
    
    Returns:
        Formatted string ready for TTS
    """
    if not articles:
        return "No news headlines available at the moment."
    
    # Limit to prevent very long responses
    max_articles = min(5, len(articles))
    
    formatted_text = f"Here are the top {max_articles} headlines:\n\n"
    
    for i, article in enumerate(articles[:max_articles], 1):
        title = article.get("title", "No title")
        source = article.get("source", "Unknown source")
        
        formatted_text += f"Headline {i}: {title}. From {source}.\n"
        
        if include_description and article.get("description"):
            formatted_text += f"{article['description']}\n"
        
        formatted_text += "\n"
    
    return formatted_text.strip()

def format_headlines_detailed(articles: List[Dict[str, Any]]) -> str:
    """
    Format news headlines with details for display
    
    Args:
        articles: List of article dictionaries
    
    Returns:
        Detailed formatted string
    """
    if not articles:
        return "No news headlines available."
    
    formatted_text = "📰 Latest News Headlines:\n\n"
    
    for i, article in enumerate(articles, 1):
        title = article.get("title", "No title")
        source = article.get("source", "Unknown")
        description = article.get("description", "")
        published_at = article.get("published_at", "")
        
        # Format date if available
        if published_at:
            try:
                dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                time_diff = datetime.now() - dt.replace(tzinfo=None)
                hours_ago = int(time_diff.total_seconds() / 3600)
                if hours_ago < 1:
                    time_str = "Just now"
                elif hours_ago < 24:
                    time_str = f"{hours_ago} hours ago"
                else:
                    days_ago = hours_ago // 24
                    time_str = f"{days_ago} days ago"
            except:
                time_str = published_at
        else:
            time_str = ""
        
        formatted_text += f"{i}. **{title}**\n"
        formatted_text += f"   Source: {source}"
        if time_str:
            formatted_text += f" • {time_str}"
        formatted_text += "\n"
        if description:
            formatted_text += f"   {description[:200]}...\n" if len(description) > 200 else f"   {description}\n"
        formatted_text += "\n"
    
    return formatted_text.strip()

# Initialize news service
if NEWS_AVAILABLE:
    logger.info("News service initialized with NewsAPI")
else:
    logger.warning("News service not available - NEWS_API_KEY not set")
