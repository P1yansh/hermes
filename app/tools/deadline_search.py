import re
import html
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus
import httpx

from app.config import settings, to_utc
from app.db import db, slugify
from app.services.gemma_client import gemma_client

logger = logging.getLogger(__name__)

class SearchDeadlineTool:
    def __init__(self, serpapi_key: Optional[str] = None):
        self.serpapi_key = serpapi_key or settings.SERPAPI_API_KEY

    async def search_serpapi(self, query: str) -> list[str]:
        if not self.serpapi_key:
            return []

        url = "https://serpapi.com/search.json"
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "engine": "google",
            "num": 5
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    organic = data.get("organic_results", [])
                    snippets = []
                    for item in organic:
                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        if snippet:
                            snippets.append(f"{title}: {snippet}")
                        elif title:
                            snippets.append(title)
                    return snippets
                else:
                    logger.warning(f"SerpApi returned status {res.status_code}: {res.text[:120]}")
        except Exception as e:
            logger.warning(f"SerpApi request failed for query '{query}': {e}")
        return []

    async def search_duckduckgo(self, query: str) -> list[str]:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        data = {"q": query}

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                res = await client.post(url, data=data, headers=headers)
                if res.status_code == 200:
                    raw_html = res.text
                    # Extract snippets from class="result__snippet"
                    matches = re.findall(
                        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                        raw_html,
                        re.DOTALL | re.IGNORECASE
                    )
                    snippets = []
                    for m in matches[:5]:
                        clean = re.sub(r"<[^>]+>", "", m)
                        clean = html.unescape(clean).strip()
                        if clean:
                            snippets.append(clean)
                    return snippets
        except Exception as e:
            logger.warning(f"DuckDuckGo search fallback failed for query '{query}': {e}")
        return []

    async def search_snippets(self, query: str) -> list[str]:
        # 1. Primary: SerpApi
        snippets = await self.search_serpapi(query)
        if snippets:
            return snippets

        # 2. Fallback: DuckDuckGo
        return await self.search_duckduckgo(query)

    async def resolve_deadline(
        self,
        event_name: str,
        query: Optional[str] = None,
        anchor_ist: Optional[str] = None
    ) -> tuple[Optional[datetime], bool]:
        """
        Resolves deadline for an event or opportunity.
        Returns (deadline_datetime, has_explicit_deadline).
        Checks SQLite cache first. Caches unverified lookups to prevent quota burn.
        """
        event_key = slugify(event_name)

        # 1. Check persistent cache
        is_cached, cached_iso = db.get_cached_deadline(event_key)
        if is_cached:
            if cached_iso:
                try:
                    dt = datetime.fromisoformat(cached_iso)
                    return to_utc(dt), True
                except Exception:
                    return None, False
            return None, False

        # 2. Perform live search
        search_q = query or f"{event_name} 2026 deadline submission date"
        snippets = await self.search_snippets(search_q)

        if snippets:
            iso_result = await gemma_client.extract_deadline_from_search(
                search_q,
                snippets,
                anchor_ist=anchor_ist
            )
            if iso_result:
                try:
                    dt = datetime.fromisoformat(iso_result)
                    dt_utc = to_utc(dt)
                    now_utc = datetime.now(timezone.utc)
                    # Verify it's a future deadline
                    if dt_utc > now_utc:
                        db.save_cached_deadline(event_key, search_q, dt_utc.isoformat())
                        return dt_utc, True
                except Exception as e:
                    logger.debug(f"Failed parsing resolved ISO deadline: {e}")

        # If search yielded no verifiable future deadline, cache negative lookup
        db.save_cached_deadline(event_key, search_q, None)
        return None, False

deadline_search_tool = SearchDeadlineTool()
