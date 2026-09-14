"""Pluggable web search (DuckDuckGo/Brave/Tavily/SearXNG) and page-text fetching."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..config import Settings

_UA = "Mozilla/5.0 (compatible; tanAI/1.0; +local)"


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchError(RuntimeError):
    """Raised when a web search cannot be completed."""


async def web_search(
    query: str, settings: Settings, max_results: int | None = None
) -> list[SearchResult]:
    limit = max_results or settings.web_results
    backend = settings.search_backend
    if backend == "brave":
        return await _brave(query, settings, limit)
    if backend == "tavily":
        return await _tavily(query, settings, limit)
    if backend == "searxng":
        return await _searxng(query, settings, limit)
    return await _duckduckgo(query, limit)


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
async def _duckduckgo(query: str, limit: int) -> list[SearchResult]:
    from bs4 import BeautifulSoup

    try:
        async with httpx.AsyncClient(
            timeout=15, trust_env=False, headers={"User-Agent": _UA}
        ) as client:
            resp = await client.post(
                "https://html.duckduckgo.com/html/", data={"q": query}
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SearchError(f"DuckDuckGo request failed: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[SearchResult] = []
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if not link:
            continue
        url = _decode_ddg_href(link.get("href", ""))
        snippet_el = node.select_one(".result__snippet")
        results.append(
            SearchResult(
                title=link.get_text(strip=True),
                url=url,
                snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
            )
        )
        if len(results) >= limit:
            break
    return results


def _decode_ddg_href(href: str) -> str:
    # DuckDuckGo wraps results in a redirect: //duckduckgo.com/l/?uddg=<url>&...
    if "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    if href.startswith("//"):
        return "https:" + href
    return href


async def _brave(query: str, settings: Settings, limit: int) -> list[SearchResult]:
    if not settings.search_api_key:
        raise SearchError("Brave search requires an API key.")
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit},
                headers={"X-Subscription-Token": settings.search_api_key},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SearchError(f"Brave request failed: {exc}") from exc
    items = (resp.json().get("web") or {}).get("results", [])
    return [
        SearchResult(
            title=i.get("title", ""),
            url=i.get("url", ""),
            snippet=i.get("description", ""),
        )
        for i in items[:limit]
    ]


async def _tavily(query: str, settings: Settings, limit: int) -> list[SearchResult]:
    if not settings.search_api_key:
        raise SearchError("Tavily search requires an API key.")
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.search_api_key,
                    "query": query,
                    "max_results": limit,
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SearchError(f"Tavily request failed: {exc}") from exc
    return [
        SearchResult(
            title=i.get("title", ""),
            url=i.get("url", ""),
            snippet=i.get("content", ""),
        )
        for i in resp.json().get("results", [])[:limit]
    ]


async def _searxng(query: str, settings: Settings, limit: int) -> list[SearchResult]:
    if not settings.searxng_url:
        raise SearchError("SearXNG requires 'searxng_url'.")
    base = settings.searxng_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            resp = await client.get(
                f"{base}/search", params={"q": query, "format": "json"}
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SearchError(f"SearXNG request failed: {exc}") from exc
    return [
        SearchResult(
            title=i.get("title", ""),
            url=i.get("url", ""),
            snippet=i.get("content", ""),
        )
        for i in resp.json().get("results", [])[:limit]
    ]


# --------------------------------------------------------------------------- #
# Page fetching (for grounding)
# --------------------------------------------------------------------------- #
def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except socket.gaierror:
        return False
    return True


async def fetch_url_text(url: str, limit: int = 4000) -> str:
    """Fetch a page and return readable text, truncated. Never raises."""

    if not _is_public_url(url):
        return ""
    from bs4 import BeautifulSoup

    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            trust_env=False,
            headers={"User-Agent": _UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )
    return text[:limit]
