"""Web search & fetch.

Gives the assistant access to current information. The search backend is
pluggable: DuckDuckGo (no API key, HTML scrape) by default, with Brave, Tavily,
and SearXNG available for more reliable results when configured.
"""

from .search import SearchResult, fetch_url_text, web_search

__all__ = ["SearchResult", "fetch_url_text", "web_search"]
