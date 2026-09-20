"""
Product page processor for Australia TGA.
Inspects individual product results, determines product relevance, and discovers
Product Information (PI) links and document metadata.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.services.normalization import NormalizationService
from app.sources.australia_tga.config import (
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    HUMAN_VERIFICATION_REQUIRED,
    SECURITY_CHALLENGE_SIGNATURES,
    TGA_BASE_URL,
)
from app.sources.australia_tga.models import TGAProductPage, TGASearchResult

logger = logging.getLogger(__name__)


class TGAProductPageHandler:
    """Handles fetching and inspecting TGA product result pages."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self.headers = headers or DEFAULT_HEADERS

    def is_relevant_result(self, result: TGASearchResult, query: str) -> bool:
        """
        Determines whether a search result corresponds to the requested medicine.
        Compares query tokens with title, snippet, URL, and active ingredient.
        """
        q = (query or "").strip().lower()
        if not q:
            return False

        q_norm = NormalizationService.normalize_drug_name(q)
        q_tokens = [t for t in q.split() if len(t) >= 3]

        targets = [
            result.title.lower(),
            result.snippet.lower(),
            result.url.lower(),
            (result.active_ingredient or "").lower(),
            NormalizationService.normalize_drug_name(result.title),
        ]

        # Direct normalized match
        for target in targets:
            if not target:
                continue
            if q in target or q_norm in target or target in q_norm:
                return True
            if any(token in target for token in q_tokens):
                return True

        # Check ARTG number match if query is numeric / AUST R
        if result.artg_number:
            if q in result.artg_number.lower():
                return True
            q_digits = re.sub(r"\D", "", q)
            if len(q_digits) >= 4 and q_digits in result.artg_number:
                return True

        return False

    async def fetch_product_page(self, url: str) -> Optional[str]:
        """Fetches the HTML of a product page, checking for anti-bot barriers."""
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                http2=False,
            ) as client:
                resp = await client.get(url)

                if resp.status_code in (403, 429) or any(
                    sig in resp.text.lower() for sig in SECURITY_CHALLENGE_SIGNATURES
                ):
                    logger.warning("Anti-bot verification required for product page: %s", url)
                    return HUMAN_VERIFICATION_REQUIRED

                if resp.status_code == 200:
                    return resp.text

                logger.warning("Product page returned HTTP %d for %s", resp.status_code, url)
                return None
        except Exception as exc:
            logger.warning("Failed to fetch product page (%s): %s", url, exc)
            return None

    def parse_product_page(self, html: str, url: str, query: str = "") -> TGAProductPage:
        """
        Parses product detail page HTML.
        Identifies product metadata, sponsor, ARTG number, and Product Information links.
        """
        soup = BeautifulSoup(html, "html.parser")

        # 1. Product Name
        h1 = soup.find("h1")
        title_tag = soup.find("title")
        product_name = ""
        if h1:
            product_name = h1.get_text(strip=True)
        elif title_tag:
            product_name = title_tag.get_text(strip=True).split("|")[0].strip()

        if not product_name or len(product_name) < 2:
            product_name = query.upper()

        # 2. Extract Active Ingredient
        active_ingr = None
        ingr_match = re.search(
            r"(?:active\s+ingredient(?:s)?|active\s+substance)\s*[:\-]?\s*([^\n\<\,\;]+)",
            soup.text,
            re.IGNORECASE,
        )
        if ingr_match:
            active_ingr = ingr_match.group(1).strip().upper()

        # 3. Extract ARTG Number
        artg_match = re.search(r"\b(AUST\s*[RL]\s*\d{5,7})\b", soup.text, re.IGNORECASE)
        artg_num = artg_match.group(1).upper() if artg_match else None

        # 4. Extract Sponsor
        sponsor = "Australian Sponsor (TGA Registered)"
        sponsor_match = re.search(
            r"(?:sponsor|applicant|manufacturer)\s*[:\-]?\s*([^\n\<\;]{3,80})",
            soup.text,
            re.IGNORECASE,
        )
        if sponsor_match:
            sponsor = sponsor_match.group(1).strip().upper()

        # 5. Extract Dosage Form
        dosage_form = "Therapeutic Good (Australia)"
        dosage_match = re.search(
            r"(?:dosage\s+form|formulation|presentation)\s*[:\-]?\s*([^\n\<\;]{3,80})",
            soup.text,
            re.IGNORECASE,
        )
        if dosage_match:
            dosage_form = dosage_match.group(1).strip()

        # 6. Discover Product Information (PI) and CMI links
        pi_links: List[str] = []
        cmi_links: List[str] = []

        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            link_text = a.get_text(strip=True).lower()
            abs_link = urljoin(url or TGA_BASE_URL, href)
            href_lower = href.lower()

            # Identify Product Information
            is_pi = (
                "product information" in link_text
                or "download pi" in link_text
                or "/pi/" in href_lower
                or "-pi-" in href_lower
                or "picmi" in href_lower
                or (href_lower.endswith(".pdf") and "pi" in href_lower)
            )

            # Identify CMI
            is_cmi = (
                "consumer medicine" in link_text
                or "cmi" in link_text
                or "/cmi/" in href_lower
                or "-cmi-" in href_lower
            )

            if is_pi and not is_cmi:
                if abs_link not in pi_links:
                    pi_links.append(abs_link)
            elif is_cmi:
                if abs_link not in cmi_links:
                    cmi_links.append(abs_link)

        # If page itself is a direct PI document view
        if (
            "/prescription-medicines-registrations/" in url
            or "/resources/artg/" in url
            or "ViewPortalDoc" in url
            or "picmirepository" in url
        ):
            if url not in pi_links and not any(c in url.lower() for c in ("/cmi/", "-cmi-")):
                pi_links.append(url)

        return TGAProductPage(
            product_name=product_name,
            active_ingredient=active_ingr or query.upper(),
            sponsor=sponsor,
            application_number=artg_num or "AUST R / Listed",
            dosage_form=dosage_form,
            source_url=url,
            pi_links=pi_links,
            cmi_links=cmi_links,
            html_content=html,
        )
