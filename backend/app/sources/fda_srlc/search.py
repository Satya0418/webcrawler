"""
FDA SrLC Search client.
Handles targeted search-driven requests to the FDA SrLC database.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.sources.fda_srlc.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    FDA_SRLC_SEARCH_URL,
    MAX_RETRIES,
    BACKOFF_FACTOR,
)

logger = logging.getLogger(__name__)


class FDASrLCSearch:
    """Submits search requests to the official FDA SrLC database."""

    def __init__(
        self,
        search_url: str = FDA_SRLC_SEARCH_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.search_url = search_url
        self.timeout = timeout
        self.max_retries = max_retries

    async def search(self, drug_or_ingredient: str) -> Optional[str]:
        """
        Execute targeted product or active ingredient search on FDA SrLC.

        Args:
            drug_or_ingredient: Medicine brand name or active ingredient name.

        Returns:
            HTML string of the search result page, or None on failure.
        """
        query_term = (drug_or_ingredient or "").strip()
        if not query_term:
            logger.warning("FDA_SRLC_SEARCH_STARTED: Empty search term provided")
            return None

        logger.info("FDA_SRLC_SEARCH_STARTED: Querying FDA SrLC for '%s'", query_term)

        payload = {
            "drug_name": query_term,
            "TextSearch": "Search",
        }

        req_headers = dict(DEFAULT_HEADERS)

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    headers=req_headers,
                    timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                    follow_redirects=True,
                ) as client:
                    response = await client.post(self.search_url, data=payload)

                    if response.status_code == 200:
                        logger.info(
                            "FDA_SRLC_SEARCH_COMPLETED: Received %d bytes for '%s'",
                            len(response.text),
                            query_term,
                        )
                        return response.text

                    if response.status_code in (403, 429, 500, 502, 503):
                        logger.warning(
                            "FDA_SRLC_ERROR: HTTP %d received for '%s' (attempt %d/%d)",
                            response.status_code,
                            query_term,
                            attempt,
                            self.max_retries,
                        )
                    else:
                        logger.error(
                            "FDA_SRLC_ERROR: Unrecoverable HTTP %d for '%s'",
                            response.status_code,
                            query_term,
                        )
                        return None

            except (httpx.TimeoutException, httpx.RequestError) as exc:
                logger.warning(
                    "FDA_SRLC_ERROR: Network %s for '%s' (attempt %d/%d): %s",
                    type(exc).__name__,
                    query_term,
                    attempt,
                    self.max_retries,
                    exc,
                )

            if attempt < self.max_retries:
                wait_time = (BACKOFF_FACTOR ** attempt)
                logger.debug("Waiting %.1fs before retrying '%s'...", wait_time, query_term)
                await asyncio.sleep(wait_time)

        logger.error(
            "FDA_SRLC_ERROR: Failed to search FDA SrLC for '%s' after %d attempts",
            query_term,
            self.max_retries,
        )
        return None
