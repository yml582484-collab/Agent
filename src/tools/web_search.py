"""
Web Search Tool
Searches the web for information using DuckDuckGo or other search engines
"""
import json
from typing import Any, Dict, List, Optional

from .base import BaseTool, tool_decorator
from ..utils.logger import get_logger

logger = get_logger(__name__)


class WebSearchTool(BaseTool):
    """
    Web Search Tool using DuckDuckGo
    
    Searches the internet and returns relevant results with snippets.
    """
    
    name = "web_search"
    description = (
        "Search the web for current information, news, facts, and other data. "
        "Useful when you need up-to-date information or specific details not in your training data."
    )
    
    def __init__(self):
        super().__init__()
        self._search_engine = None
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string (what to search for)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }
    
    async def execute(
        self,
        query: str,
        max_results: int = 5,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute web search
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            Dictionary with search results
        """
        logger.info(f"Searching web for: {query}")
        
        try:
            # Try to use duckduckgo-search package
            results = await self._duckduckgo_search(query, max_results)
            
            if results:
                return {
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results),
                }
            else:
                return {
                    "success": False,
                    "query": query,
                    "error": "No results found",
                    "results": [],
                }
                
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            
            # Fallback to mock results if search fails
            return await self._fallback_search(query)
    
    async def _duckduckgo_search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[Dict]:
        """Perform actual DuckDuckGo search"""
        try:
            from duckduckgo_search import DDGS
            
            with DDGS() as ddgs:
                results = [
                    {
                        "title": r["title"],
                        "url": r["href"],
                        "snippet": r["body"],
                        "source": "duckduckgo",
                    }
                    for r in ddgs.text(query, max_results=max_results)
                ]
                
            return results
            
        except ImportError:
            logger.warning(
                "duckduckgo-search not installed. "
                "Install with: pip install duckduckgo-search"
            )
            raise
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise
    
    async def _fallback_search(self, query: str) -> Dict[str, Any]:
        """
        Fallback when search engine unavailable
        Returns a helpful message suggesting alternatives
        """
        return {
            "success": False,
            "query": query,
            "error": "Search service temporarily unavailable",
            "suggestion": (
                f"I couldn't search for '{query}' right now. "
                "You might want to:\n"
                "1. Try searching manually\n"
                "2. Provide me with the information directly\n"
                "3. Try again later"
            ),
            "results": [],
        }
