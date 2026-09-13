"""
Async HTTP crawler for Health Canada Health Product InfoWatch.

Responsibilities:
  - Fetch the published-newsletters index page
  - Fetch individual article pages
  - Enforce polite request rate (configurable delay)
  - Retry with exponential backoff on transient errors
  - Track visited URLs to avoid duplicate fetches
  - Log all failures without stopping the overall crawl

Does NOT parse HTML — that is handled by discovery.py and parser.py.
Does NOT bypass any access controls, authentication, or rate limits.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Set
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HC_INDEX_URL = (
    "https://www.canada.ca/en/health-canada/services/drugs-health-products"
    "/medeffect-canada/health-product-infowatch/published-newsletters.html"
)
HC_BASE_URL = "https://www.canada.ca"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MedicineSafetyBot/1.0; "
        "+https://github.com/your-org/webcrawler)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Politeness delay between requests (seconds)
REQUEST_DELAY = 1.5

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0   # seconds; delay = base ** attempt

# HTTP timeout (seconds)
HTTP_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Crawler class
# ---------------------------------------------------------------------------

class HealthCanadaCrawler:
    """
    Async HTTP crawler for Health Canada InfoWatch pages.

    Usage:
        async with HealthCanadaCrawler() as crawler:
            html = await crawler.fetch_index()
            article_html = await crawler.fetch_article(url)
    """

    def __init__(
        self,
        request_delay: float = REQUEST_DELAY,
        max_retries: int = MAX_RETRIES,
        timeout: float = HTTP_TIMEOUT,
    ) -> None:
        self._request_delay = request_delay
        self._max_retries = max_retries
        self._timeout = timeout
        self._visited: Set[str] = set()
        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "HealthCanadaCrawler":
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=self._timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch_index(self) -> Optional[str]:
        """
        Fetch the published-newsletters index page.

        Returns:
            HTML string, or None on permanent failure.
        """
        return await self._get(HC_INDEX_URL)

    async def fetch_article(self, url: str) -> Optional[str]:
        """
        Fetch a single InfoWatch article page.

        Args:
            url: Absolute or root-relative URL. Root-relative paths are
                 resolved against HC_BASE_URL.

        Returns:
            HTML string, or None on permanent failure.
        """
        absolute = self._resolve_url(url)
        # Normalise: strip fragment so we only fetch each page once
        page_url = absolute.split("#")[0]

        if page_url in self._visited:
            logger.debug("Skipping already-fetched URL: %s", page_url)
            return None

        html = await self._get(page_url)
        if html:
            self._visited.add(page_url)
        return html

    def reset_visited(self) -> None:
        """Clear the visited-URL tracking set (useful between crawl runs)."""
        self._visited.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, url: str) -> Optional[str]:
        """HTTP GET with retry and polite delay."""
        if self._client is None:
            raise RuntimeError(
                "HealthCanadaCrawler must be used as an async context manager."
            )

        for attempt in range(self._max_retries + 1):
            await self._polite_sleep()

            try:
                logger.debug("GET %s (attempt %d)", url, attempt + 1)
                response = await self._client.get(url)
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.text

                if response.status_code in (404, 410):
                    logger.warning("Permanent failure (HTTP %d): %s", response.status_code, url)
                    return None

                if response.status_code in (429, 503):
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Rate limited (HTTP %d) on %s — waiting %.1fs before retry",
                        response.status_code, url, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                logger.warning("HTTP %d for %s", response.status_code, url)

            except httpx.TimeoutException:
                wait = self._backoff(attempt)
                logger.warning("Timeout on %s — retrying in %.1fs", url, wait)
                await asyncio.sleep(wait)

            except httpx.RequestError as exc:
                wait = self._backoff(attempt)
                logger.warning("Request error on %s: %s — retrying in %.1fs", url, exc, wait)
                await asyncio.sleep(wait)

            except Exception as exc:
                logger.error("Unexpected error fetching %s: %s", url, exc, exc_info=True)
                return None

        logger.error("Gave up fetching %s after %d attempts", url, self._max_retries + 1)
        return None

    async def _polite_sleep(self) -> None:
        """Ensure at least REQUEST_DELAY seconds between consecutive requests."""
        elapsed = time.monotonic() - self._last_request_time
        wait = self._request_delay - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

    @staticmethod
    def _backoff(attempt: int) -> float:
        return RETRY_BACKOFF_BASE ** attempt

    @staticmethod
    def _resolve_url(url: str) -> str:
        """Resolve root-relative or protocol-relative URLs."""
        if url.startswith("http"):
            return url
        return urljoin(HC_BASE_URL, url)


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors pattern used by fda_crawler.py)
# ---------------------------------------------------------------------------

crawler = HealthCanadaCrawler()
