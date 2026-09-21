"""
FDA SrLC Web Crawler.
Coordinates targeted search, detail page fetching, and structured extraction.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

import httpx

from app.sources.fda_srlc.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    FDA_SRLC_BASE_URL,
    MAX_RETRIES,
    BACKOFF_FACTOR,
)
from app.sources.fda_srlc.extractor import FDASrLCExtractor
from app.sources.fda_srlc.models import FDASearchCandidate, FDASrLCStructuredResult
from app.sources.fda_srlc.result_parser import FDASrLCResultParser
from app.sources.fda_srlc.search import FDASrLCSearch

logger = logging.getLogger(__name__)


class FDASrLCCrawler:
    """Crawler for FDA SrLC database using Hybrid Crawler Architecture."""

    def __init__(
        self,
        search_client: Optional[FDASrLCSearch] = None,
        result_parser: Optional[FDASrLCResultParser] = None,
        extractor: Optional[FDASrLCExtractor] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.search_client = search_client or FDASrLCSearch(timeout=timeout)
        self.result_parser = result_parser or FDASrLCResultParser()
        self.extractor = extractor or FDASrLCExtractor()
        self.timeout = timeout
        self.visited_urls: Set[str] = set()

    async def get_page(self, url: str) -> Optional[str]:
        """Fetch a single page with retries and browser headers."""
        if not url:
            return None

        req_headers = dict(DEFAULT_HEADERS)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    headers=req_headers,
                    timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        self.visited_urls.add(url)
                        return resp.text
                    if resp.status_code in (403, 429, 500, 502, 503):
                        logger.warning("FDA_SRLC_ERROR: HTTP %d fetching %s (attempt %d/%d)", resp.status_code, url, attempt, MAX_RETRIES)
                    else:
                        logger.error("FDA_SRLC_ERROR: HTTP %d fetching %s", resp.status_code, url)
                        return None
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                logger.warning("FDA_SRLC_ERROR: Network %s fetching %s: %s", type(exc).__name__, url, exc)

            if attempt < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_FACTOR ** attempt)

        return None

    async def search_medicine(self, query: str) -> List[Dict[str, Any]]:
        """
        Executes end-to-end FDA SrLC medicine discovery:
        1. Submit query.
        2. Retrieve & parse matching results.
        3. Fetch detail pages.
        4. Apply Date-First selection & Section Priority.
        5. Return list of candidate dictionaries ready for DB persistence.
        """
        q = (query or "").strip()
        if not q:
            return []

        # 1. Targeted search
        html = await self.search_client.search(q)
        if not html:
            logger.info("FDA_SRLC_NO_MATCH: No search response for '%s'", q)
            return []

        # 2. Parse candidates matching query
        candidates = self.result_parser.parse_search_results(html, target_query=q)
        if not candidates:
            return []

        results: List[Dict[str, Any]] = []

        # Process top candidates (e.g. up to 3 distinct matching applications)
        seen_apps = set()
        unique_candidates = []
        for c in candidates:
            app_key = c.application_number or c.drug_name
            if app_key not in seen_apps:
                seen_apps.add(app_key)
                unique_candidates.append(c)
            if len(unique_candidates) >= 3:
                break

        for cand in unique_candidates:
            if not cand.detail_url:
                continue

            detail_html = await self.get_page(cand.detail_url)
            if not detail_html:
                continue

            # Parse detail page into supplement records
            d_name, a_ingr, app_num, supp_records = (
                self.extractor.parse_supplement_records_from_detail_html(
                    detail_html, source_url=cand.detail_url
                )
            )

            final_drug_name = d_name or cand.drug_name
            final_active_ingr = a_ingr or cand.active_ingredient
            final_app_num = app_num or cand.application_number

            # Extract latest update strictly with Date-First and Section Priority
            structured_res = await self.extractor.extract_latest_update(
                drug_name=final_drug_name,
                active_ingredient=final_active_ingr,
                application_number=final_app_num,
                all_supplement_records=supp_records,
                source_url=cand.detail_url,
            )

            # Map to database candidate dictionary
            safety_changes_list = []
            if structured_res.sections:
                sec_dict = structured_res.sections
                # Adverse Reactions
                if sec_dict.adverse_reactions.found and sec_dict.adverse_reactions.content:
                    ar = sec_dict.adverse_reactions
                    safety_changes_list.append({
                        "section": "Adverse Reactions",
                        "change_type": "Labeling Revision",
                        "source_date": ar.date,
                        "updated_text": ar.content,
                        "source_url": ar.source_url or cand.detail_url,
                        "fda_comment": f"Approved Label PDF: {ar.document_url}" if ar.document_url else None,
                        "source_record_id": structured_res.supplement_number or f"{final_drug_name}-{ar.date}",
                    })
                # Warnings and Precautions
                if sec_dict.warnings_and_precautions.found and sec_dict.warnings_and_precautions.content:
                    wp = sec_dict.warnings_and_precautions
                    safety_changes_list.append({
                        "section": "Warnings and Precautions",
                        "change_type": "Labeling Revision",
                        "source_date": wp.date,
                        "updated_text": wp.content,
                        "source_url": wp.source_url or cand.detail_url,
                        "fda_comment": f"Approved Label PDF: {wp.document_url}" if wp.document_url else None,
                        "source_record_id": structured_res.supplement_number or f"{final_drug_name}-{wp.date}",
                    })
                # Pregnancy / Use in Specific Populations
                if sec_dict.pregnancy.found and sec_dict.pregnancy.content:
                    preg = sec_dict.pregnancy
                    safety_changes_list.append({
                        "section": "Use in Specific Populations",
                        "change_type": "Labeling Revision",
                        "source_date": preg.date,
                        "updated_text": preg.content,
                        "source_url": preg.source_url or cand.detail_url,
                        "fda_comment": f"Approved Label PDF: {preg.document_url}" if preg.document_url else None,
                        "source_record_id": structured_res.supplement_number or f"{final_drug_name}-{preg.date}",
                    })

            # Also capture historical updates from other supplement records
            for supp_rec in supp_records:
                if supp_rec.date_str == structured_res.latest_labeling_change_date:
                    continue
                for sec in supp_rec.sections:
                    raw_sec = sec.get("raw_section", "")
                    if self.extractor.section_detector.is_adverse_reactions(raw_sec):
                        norm_sec = "Adverse Reactions"
                    elif self.extractor.section_detector.is_warnings_and_precautions(raw_sec):
                        norm_sec = "Warnings and Precautions"
                    elif self.extractor.section_detector.is_use_in_specific_populations(raw_sec):
                        norm_sec = "Use in Specific Populations"
                    else:
                        continue

                    safety_changes_list.append({
                        "section": norm_sec,
                        "change_type": "Labeling Revision",
                        "source_date": supp_rec.date_str,
                        "updated_text": sec.get("text", ""),
                        "source_url": cand.detail_url,
                        "fda_comment": f"Approved Label PDF: {supp_rec.document_url}" if supp_rec.document_url else None,
                        "source_record_id": supp_rec.supplement_id or f"{final_drug_name}-{supp_rec.date_str}",
                    })

            candidate_dict = {
                "display_name": final_drug_name,
                "drug_name": final_drug_name,
                "active_ingredient": final_active_ingr,
                "application_number": final_app_num,
                "source": "FDA_SRLC",
                "source_url": cand.detail_url,
                "source_date": structured_res.latest_labeling_change_date,
                "detail_url": cand.detail_url,
                "safety_changes": safety_changes_list,
                "structured_result": structured_res.to_dict(),
            }
            results.append(candidate_dict)

        return results


fda_srlc_crawler = FDASrLCCrawler()
