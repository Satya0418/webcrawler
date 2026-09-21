"""
Parser for FDA SrLC Search Results.
Identifies result tables, extracts drug metadata, and performs exact/normalized product matching.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.services.normalization import NormalizationService
from app.sources.fda_srlc.config import FDA_SRLC_BASE_URL
from app.sources.fda_srlc.date_parser import parse_fda_date
from app.sources.fda_srlc.models import FDASearchCandidate

logger = logging.getLogger(__name__)


class FDASrLCResultParser:
    """Parses FDA SrLC search result pages and extracts candidate records."""

    def __init__(self, base_url: str = FDA_SRLC_BASE_URL) -> None:
        self.base_url = base_url

    def parse_search_results(
        self,
        html_content: str,
        target_query: Optional[str] = None,
    ) -> List[FDASearchCandidate]:
        """
        Parse table rows from FDA search result HTML.

        Args:
            html_content: Raw HTML from searchResult.page.
            target_query: Optional search term to filter candidates.

        Returns:
            List of FDASearchCandidate objects.
        """
        if not html_content:
            logger.warning("FDA_SRLC_RESULTS_FOUND: Empty HTML content provided")
            return []

        soup = BeautifulSoup(html_content, "lxml")
        candidates: List[FDASearchCandidate] = []

        # Locate results table (usually <table id="example" class="display">)
        table = soup.find("table", id="example")
        if not table:
            # Fallback: any table with drug name header
            for candidate_table in soup.find_all("table"):
                headers = [th.get_text(strip=True).lower() for th in candidate_table.find_all("th")]
                if any("drug name" in h for h in headers) and any("application" in h or "ingredient" in h for h in headers):
                    table = candidate_table
                    break

        if not table:
            logger.info("FDA_SRLC_NO_MATCH: No results table found in FDA response")
            return []

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if not cells or len(cells) < 3:
                continue

            cell_texts = [c.get_text(strip=True) for c in cells]
            drug_name = cell_texts[0]
            if not drug_name or drug_name.lower() in ("drug name", "no data available in table"):
                continue

            active_ingredient = cell_texts[1] if len(cell_texts) > 1 else None
            app_num = cell_texts[2] if len(cell_texts) > 2 else None
            app_type = cell_texts[3] if len(cell_texts) > 3 else None
            supp_date = cell_texts[4] if len(cell_texts) > 4 else None
            db_updated = cell_texts[5] if len(cell_texts) > 5 else None

            # Extract detail link
            detail_url = None
            link_tag = cells[0].find("a")
            if link_tag and link_tag.get("href"):
                detail_url = urljoin(f"{self.base_url}/", link_tag["href"])
            elif len(cells) > 6:
                # Some versions display link in last column
                last_link = cells[6].find("a")
                if last_link and last_link.get("href"):
                    detail_url = urljoin(f"{self.base_url}/", last_link["href"])
                elif cells[6].get_text(strip=True).startswith("http"):
                    detail_url = cells[6].get_text(strip=True)

            # Format full application number: e.g. NDA-021130
            full_app_num = app_num
            if app_type and app_num:
                clean_type = app_type.strip()
                clean_num = app_num.strip()
                if not clean_num.upper().startswith(clean_type.upper()):
                    full_app_num = f"{clean_type}-{clean_num}"

            cand = FDASearchCandidate(
                drug_name=drug_name,
                active_ingredient=active_ingredient,
                application_number=full_app_num,
                application_type=app_type,
                supplement_date=supp_date,
                database_updated=db_updated,
                detail_url=detail_url,
                raw_date=parse_fda_date(supp_date),
            )
            candidates.append(cand)

        logger.info("FDA_SRLC_RESULTS_FOUND: Found %d total raw candidate rows in table", len(candidates))

        # Filter by target query if supplied
        if target_query:
            matched = [c for c in candidates if self.is_product_match(target_query, c)]
            logger.info(
                "FDA_SRLC_RESULTS_FOUND: %d candidates matched query '%s'",
                len(matched),
                target_query,
            )
            if not matched:
                logger.info("FDA_SRLC_NO_MATCH: No matching FDA SrLC record found for this product.")
            return matched

        return candidates

    def is_product_match(self, query: str, candidate: FDASearchCandidate) -> bool:
        """
        Normalized medicine/product matching.
        Matches brand name, active ingredient, or application number without accidental partial matches.
        """
        if not query:
            return True

        norm_query = NormalizationService.normalize_drug_name(query)
        norm_name = NormalizationService.normalize_drug_name(candidate.drug_name)
        norm_ingr = NormalizationService.normalize_active_ingredient(candidate.active_ingredient or "")

        # Exact normalized match on drug name or active ingredient
        if norm_query == norm_name or norm_query == norm_ingr:
            return True

        # Token-based word boundary match (avoids substring pollution like 'pro' matching 'ciprofloxacin')
        pattern = r"\b" + re.escape(norm_query) + r"\b"
        if re.search(pattern, norm_name) or re.search(pattern, norm_ingr):
            return True

        # Match application number if query looks like an application number (e.g. '021130' or 'NDA-021130')
        if candidate.application_number:
            clean_app = re.sub(r"[\s\-]", "", candidate.application_number.lower())
            clean_q = re.sub(r"[\s\-]", "", query.lower())
            if clean_q and clean_q in clean_app:
                return True

        return False
