"""
FDA MedWatch Article Discovery.
Searches and identifies relevant MedWatch safety articles, Drug Safety Communications,
and Recalls for a target medicine while avoiding false partial matches.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
import httpx

from app.services.normalization import NormalizationService
from app.sources.fda_medwatch.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    DRUG_SAFETY_COMMUNICATIONS_URL,
    MAX_RETRIES,
    MEDWATCH_PORTAL_URL,
    MEDWATCH_RSS_URL,
    RECALLS_URL,
)
from app.sources.fda_medwatch.models import MedWatchArticle

logger = logging.getLogger(__name__)


class FDAMedWatchArticleDiscovery:
    """Discovers MedWatch safety articles across official FDA channels."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    @staticmethod
    def is_product_match(query: str, text: str) -> bool:
        """
        Performs precise word-boundary and normalized product matching to avoid
        incorrect substring collisions (e.g. 'Akeega' vs random word).
        """
        if not query or not text:
            return False

        q_clean = NormalizationService.normalize_drug_name(query)
        if not q_clean or len(q_clean) < 2:
            return False

        t_clean = NormalizationService.normalize_drug_name(text)

        # Word boundary match on normalized text
        pattern = rf"\b{re.escape(q_clean)}\b"
        if re.search(pattern, t_clean):
            return True

        # Check token match
        q_tokens = set(q_clean.split())
        t_tokens = set(t_clean.split())
        if q_tokens and q_tokens.issubset(t_tokens):
            return True

        return False

    async def fetch_rss_articles(self, client: httpx.AsyncClient, query: str) -> List[MedWatchArticle]:
        """Fetches and filters live MedWatch RSS alerts."""
        articles: List[MedWatchArticle] = []
        try:
            resp = await client.get(MEDWATCH_RSS_URL, headers=DEFAULT_HEADERS)
            if resp.status_code == 200 and resp.text:
                root = ET.fromstring(resp.text)
                channel = root.find("channel")
                if channel is not None:
                    for item in channel.findall("item"):
                        t_elem = item.find("title")
                        l_elem = item.find("link")
                        d_elem = item.find("description")
                        p_elem = item.find("pubDate")

                        title = t_elem.text.strip() if t_elem is not None and t_elem.text else ""
                        link = l_elem.text.strip() if l_elem is not None and l_elem.text else MEDWATCH_PORTAL_URL
                        desc = d_elem.text.strip() if d_elem is not None and d_elem.text else ""
                        pub_date = p_elem.text.strip() if p_elem is not None and p_elem.text else ""

                        combined = f"{title} {desc}"
                        if self.is_product_match(query, combined):
                            articles.append(
                                MedWatchArticle(
                                    title=title,
                                    url=link,
                                    publication_date=pub_date,
                                    product_name=query.upper(),
                                    safety_topic=title,
                                    summary=desc,
                                )
                            )
                            logger.info("FDA_MEDWATCH_ARTICLE_FOUND: RSS alert '%s'", title)
        except Exception as exc:
            logger.debug("Live MedWatch RSS fetch error: %s", exc)

        return articles

    async def fetch_drug_safety_communications(self, client: httpx.AsyncClient, query: str) -> List[MedWatchArticle]:
        """Scans the FDA Drug Safety Communications directory for matching articles."""
        articles: List[MedWatchArticle] = []
        try:
            resp = await client.get(DRUG_SAFETY_COMMUNICATIONS_URL, headers=DEFAULT_HEADERS)
            if resp.status_code == 200 and resp.text:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    title = " ".join(a.get_text().strip().split())
                    if not title or len(title) < 10:
                        continue

                    full_url = urljoin(DRUG_SAFETY_COMMUNICATIONS_URL, href)
                    if self.is_product_match(query, title) or self.is_product_match(query, href):
                        articles.append(
                            MedWatchArticle(
                                title=title,
                                url=full_url,
                                product_name=query.upper(),
                                safety_topic=title,
                            )
                        )
                        logger.info("FDA_MEDWATCH_ARTICLE_FOUND: Drug Safety Communication '%s' -> %s", title, full_url)
        except Exception as exc:
            logger.debug("Drug Safety Communications fetch error: %s", exc)

        return articles

    async def discover_articles(self, query: str) -> List[MedWatchArticle]:
        """
        Coordinates discovery across RSS feed and Drug Safety Communications index.
        Returns deduplicated list of MedWatchArticle instances.
        """
        q = (query or "").strip()
        if not q:
            return []

        logger.info("FDA_MEDWATCH_SEARCH_STARTED: Discovering MedWatch articles for '%s'", q)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
            follow_redirects=True,
        ) as client:
            rss_articles = await self.fetch_rss_articles(client, q)
            dsc_articles = await self.fetch_drug_safety_communications(client, q)

        combined = rss_articles + dsc_articles
        seen_urls = set()
        unique_articles: List[MedWatchArticle] = []
        for art in combined:
            if art.url not in seen_urls:
                seen_urls.add(art.url)
                unique_articles.append(art)

        logger.info("FDA_MEDWATCH_DISCOVERY_COMPLETED: Discovered %d articles for '%s'", len(unique_articles), q)
        return unique_articles
