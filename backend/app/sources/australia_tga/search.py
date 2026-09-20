"""
Search engine for querying the official Australia TGA website:
https://www.tga.gov.au/search?keywords=
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
import httpx

from app.sources.australia_tga.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    HUMAN_VERIFICATION_REQUIRED,
    SECURITY_CHALLENGE_SIGNATURES,
    TGA_BASE_URL,
    TGA_EBS_SEARCH_URL,
    TGA_EBS_VIEW_URL,
    TGA_SEARCH_URL,
)
from app.sources.australia_tga.date_parser import TGADateParser
from app.sources.australia_tga.models import TGASearchResult

logger = logging.getLogger(__name__)


class TGASearchEngine:
    """Executes searches against the TGA website and parses result listings."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self.headers = headers or DEFAULT_HEADERS

    async def search(self, query: str) -> List[TGASearchResult]:
        """
        Executes a search for the specified query on TGA.
        1. Queries official TGA eBS Product Information search (PISearch) for real-time structured data.
        2. Falls back to public HTML search on tga.gov.au/search?keywords= if eBS yields no results.
        Returns a list of structured TGASearchResult objects.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        # 1. Primary: Official TGA eBS Product Information register
        ebs_results = await self.search_ebs(q)
        if ebs_results:
            logger.info("Found %d results from TGA eBS Product Information register for '%s'", len(ebs_results), q)
            return ebs_results

        # 2. Secondary: Public HTML search
        html = await self.fetch_search_html(q)
        if not html:
            return []

        if html == HUMAN_VERIFICATION_REQUIRED:
            logger.warning("Search aborted: %s detected on TGA", HUMAN_VERIFICATION_REQUIRED)
            return []

        return self.parse_search_results(html, query=q)

    async def search_ebs(self, query: str) -> List[TGASearchResult]:
        """
        Queries official TGA eBS Product Information register (PISearch).
        Returns structured search results directly linking to the PI documents.
        """
        target_url = f"{TGA_EBS_SEARCH_URL}{quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(target_url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                entries = data.get("viewentry", [])
                results: List[TGASearchResult] = []
                for e in entries:
                    unid = e.get("@unid")
                    if not unid:
                        continue
                    edata = {item.get("@name"): item for item in e.get("entrydata", [])}
                    trade_name = edata.get("Trade name", {}).get("text", {}).get("0", "").strip()
                    active_ingr = edata.get("Active ingredients", {}).get("text", {}).get("0", "").strip()
                    artg_raw = edata.get("ARTG", {})
                    if "text" in artg_raw:
                        artg = artg_raw["text"].get("0", "").strip()
                    elif "textlist" in artg_raw:
                        artg = " ".join(t.get("0", "") for t in artg_raw["textlist"].get("text", [])).strip()
                    else:
                        artg = ""
                    sponsor = edata.get("Sponsor name", {}).get("text", {}).get("0", "").strip()
                    date_val = edata.get("Published date", {}).get("datetime", {}).get("0", "")

                    doc_url = f"{TGA_EBS_VIEW_URL}{unid}"
                    dt = TGADateParser.parse_date(date_val)
                    snippet = f"Australian Register of Therapeutic Goods (ARTG) Product Information for {trade_name} ({artg}). Sponsor: {sponsor}"

                    results.append(
                        TGASearchResult(
                            title=trade_name or query.upper(),
                            url=doc_url,
                            snippet=snippet,
                            date_str=date_val,
                            source_date=dt,
                            artg_number=artg or None,
                            active_ingredient=active_ingr or None,
                        )
                    )
                return results
        except Exception as exc:
            logger.warning("Failed to query TGA eBS search for '%s': %s", query, exc)
            return []

    async def fetch_search_html(self, query: str) -> Optional[str]:
        """
        Fetches the HTML response for a TGA search query.
        Returns HTML string, or HUMAN_VERIFICATION_REQUIRED if anti-bot detected, or None on error.
        """
        target_url = f"{TGA_SEARCH_URL}{quote_plus(query)}"
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                http2=False,
            ) as client:
                resp = await client.get(target_url)

                # Check for anti-bot or challenge verification
                if self.is_security_challenge(resp.status_code, resp.text):
                    logger.warning("Anti-bot or security challenge encountered for query '%s'", query)
                    return HUMAN_VERIFICATION_REQUIRED

                if resp.status_code == 200 and resp.text:
                    logger.info("Fetched TGA search page for '%s' (%d bytes)", query, len(resp.text))
                    return resp.text

                logger.warning("TGA search returned HTTP %d for query '%s'", resp.status_code, query)
                return None

        except httpx.TimeoutException:
            logger.warning("TGA search request timed out for '%s'", query)
            return None
        except Exception as exc:
            logger.warning("Failed to reach TGA search URL (%s): %s", target_url, exc)
            return None

    def is_security_challenge(self, status_code: int, html_text: str) -> bool:
        """Determines if the response is a CAPTCHA or anti-bot verification challenge."""
        if status_code in (403, 429):
            return True
        if not html_text:
            return False
        lower_html = html_text.lower()
        return any(sig in lower_html for sig in SECURITY_CHALLENGE_SIGNATURES)

    def parse_search_results(self, html: str, query: str = "") -> List[TGASearchResult]:
        """
        Parses search result entries from TGA search HTML.
        Extracts title, URL, snippet, published date, and candidate ARTG / active ingredients.
        """
        if not html or html == HUMAN_VERIFICATION_REQUIRED:
            return []

        soup = BeautifulSoup(html, "html.parser")
        results: List[TGASearchResult] = []

        candidate_nodes = soup.select(
            "article, .views-row, .search-result, li.search-result, .field--name-node-title, .search-item"
        )
        if not candidate_nodes:
            main_content = soup.find("main") or soup.find("div", {"id": "main-content"}) or soup
            candidate_nodes = main_content.find_all(
                ["article", "div", "li"],
                class_=re.compile(r"result|row|item", re.I),
            )

        for node in candidate_nodes:
            title_tag = node.find(["h2", "h3", "h4", "a"], href=True) or node.find("a")
            if not title_tag:
                continue

            title_text = title_tag.get_text(strip=True)
            href = title_tag.get("href") or ""
            abs_url = urljoin(TGA_BASE_URL, href)

            if len(title_text) < 3 or abs_url == TGA_BASE_URL:
                continue

            snippet_tag = node.find(["p", "div"], class_=re.compile(r"snippet|summary|description|body", re.I))
            snippet_text = snippet_tag.get_text(strip=True) if snippet_tag else ""

            date_tag = node.find(["time", "span"], class_=re.compile(r"date|published|time", re.I))
            date_str = date_tag.get_text(strip=True) if date_tag else None
            source_dt = TGADateParser.parse_date(date_str)

            # ARTG candidate (AUST R / AUST L)
            artg_match = re.search(r"\b(AUST\s*[RL]\s*\d{5,7})\b", f"{title_text} {snippet_text}", re.IGNORECASE)
            artg_num = artg_match.group(1).upper() if artg_match else None

            # Active ingredient candidate inside parentheses
            ingr_match = re.search(r"\(([^)]+)\)", title_text)
            candidate_ingr = None
            if ingr_match:
                cand = ingr_match.group(1).strip().upper()
                if cand not in ("PI", "CMI", "TGA", "TABLETS", "CAPSULES"):
                    candidate_ingr = cand

            results.append(
                TGASearchResult(
                    title=title_text,
                    url=abs_url,
                    snippet=snippet_text,
                    date_str=date_str,
                    source_date=source_dt,
                    artg_number=artg_num,
                    active_ingredient=candidate_ingr,
                    is_relevant=True,
                )
            )

        return results
