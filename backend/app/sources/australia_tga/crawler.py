"""
Australia Therapeutic Goods Administration (TGA) Crawler Orchestrator.

Implements the end-to-end regulatory workflow:
1. Search TGA (https://www.tga.gov.au/search?keywords=...)
2. Open and identify relevant product page
3. Discover Product Information (PI) links and versions
4. Select latest valid PI PDF by revision date / version
5. Pass PDF to EXISTING PDF extractor pipeline
6. Extract complete Section 4.6 (Fertility, Pregnancy and Lactation)
7. Extract complete Section 4.8 (Adverse Effects / Undesirable Effects) and tables
8. Preserve page numbers, version, date, and as-is regulatory wording
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from app.services.normalization import NormalizationService
from app.sources.australia_tga.config import (
    DEFAULT_TIMEOUT,
    HUMAN_VERIFICATION_REQUIRED,
    MISSING_SECTION_4_6_TEXT,
    MISSING_SECTION_4_8_TEXT,
    PDF_DOWNLOAD_TIMEOUT,
    SECTION_4_6_CANONICAL,
    SECTION_4_8_CANONICAL,
    SOURCE_ID,
    TGA_CURATED_REGISTRY,
)
from app.sources.australia_tga.date_parser import TGADateParser
from app.sources.australia_tga.models import (
    ExtractedSection,
    TGAPIDocument,
    TGAProductPage,
    TGARegulatoryResult,
    TGASearchResult,
)
from app.sources.australia_tga.pdf_handler import TGAPDFHandler
from app.sources.australia_tga.product_information import TGAProductInformationDiscoverer
from app.sources.australia_tga.product_page import TGAProductPageHandler
from app.sources.australia_tga.search import TGASearchEngine
from app.sources.australia_tga.section_extractor import TGASectionExtractor
from app.sources.australia_tga.validators import TGAValidator
from app.sources.australia_tga.version_selector import TGAVersionSelector

logger = logging.getLogger(__name__)


class AustraliaTGACrawler:
    """Master orchestrator for Australian TGA regulatory medicine extraction, and harmonizing Australian TGA Product Information."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        live_fetch: bool = True,
    ) -> None:
        self.timeout = timeout
        self.live_fetch = live_fetch
        self.search_engine = TGASearchEngine(timeout=timeout)
        self.product_page_handler = TGAProductPageHandler(timeout=timeout)
        self.pi_discoverer = TGAProductInformationDiscoverer(timeout=timeout)
        self.pdf_handler = TGAPDFHandler(timeout=PDF_DOWNLOAD_TIMEOUT)

    async def search_medicine(self, query: str) -> List[Dict[str, Any]]:
        """
        Main entry point for medicine search.
        Executes full discovery, PDF retrieval, section extraction, and returns
        structured records formatted for DatabaseService persistence.
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        norm_query = NormalizationService.normalize_drug_name(q)
        results: List[Dict[str, Any]] = []

        # 1. Live Crawl & Extraction Pipeline
        if self.live_fetch:
            try:
                live_items = await self._run_live_workflow(q)
                if live_items:
                    results.extend(live_items)
            except Exception as exc:
                logger.error("Error during live TGA workflow for '%s': %s", q, exc, exc_info=True)

        # 2. Resilient Curated Fallback (when TGA is geo-blocked or unreachable)
        if not results:
            fallback = self._get_fallback_drug(norm_query, q)
            if fallback:
                results.append(fallback)

        return results

    async def _run_live_workflow(self, query: str) -> List[Dict[str, Any]]:
        """Executes the live discovery -> PDF -> section extraction sequence."""
        logger.info("Initiating live TGA search for '%s'", query)

        # Step 1: Search TGA
        search_results = await self.search_engine.search(query)
        if not search_results:
            return []

        # Step 2: Filter relevant product pages
        matching_results = [
            r for r in search_results if self.product_page_handler.is_relevant_result(r, query)
        ]
        # Sort candidates: exact brand match, then latest date
        matching_results.sort(
            key=lambda r: (
                1 if query.lower() in r.title.lower() else 0,
                r.source_date or datetime.min,
            ),
            reverse=True,
        )

        # Process up to 12 matching candidates concurrently with bounded concurrency
        sem = asyncio.Semaphore(3)

        async def _bounded_process(candidate: TGASearchResult) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    return await self._process_single_candidate(candidate, query)
                except Exception as exc:
                    logger.warning("Error processing TGA candidate '%s': %s", candidate.title, exc)
                    return None

        tasks = [_bounded_process(c) for c in matching_results[:12]]
        settled = await asyncio.gather(*tasks, return_exceptions=True)
        items = [item for item in settled if isinstance(item, dict)]
        return items

    async def _process_single_candidate(
        self, candidate: TGASearchResult, query: str
    ) -> Optional[Dict[str, Any]]:
        """Processes an individual TGA search candidate: page fetch -> PDF discovery -> section extraction."""
        clean_cand_url = candidate.url.split("#")[0].strip()

        # Step 3: Fetch and inspect product page
        html = await self.product_page_handler.fetch_product_page(clean_cand_url)
        if not html:
            # If candidate URL is already a direct document, create a lightweight page
            html = f"<html><body><h1>{candidate.title}</h1><a href='{clean_cand_url}'>Product Information</a></body></html>"

        if html == HUMAN_VERIFICATION_REQUIRED:
            logger.warning("Human verification required on TGA for %s", clean_cand_url)
            return None

        product_page = self.product_page_handler.parse_product_page(
            html, url=clean_cand_url, query=query
        )
        # Ensure candidate trade name and ARTG number are preserved
        if candidate.title:
            product_page.product_name = candidate.title
        if candidate.active_ingredient:
            product_page.active_ingredient = candidate.active_ingredient.upper()
        if candidate.artg_number:
            artg_clean = candidate.artg_number.strip()
            if not artg_clean.upper().startswith("AUST"):
                artg_clean = f"AUST R {artg_clean}"
            product_page.application_number = artg_clean

        # Step 4: Discover Product Information PDF documents
        pi_documents = await self.pi_discoverer.discover_pi_documents(product_page)
        if not pi_documents:
            # Only use clean_cand_url if it is an actual direct PDF or ViewPortalDoc link
            if self.pi_discoverer._is_direct_pdf_url(clean_cand_url):
                pi_documents.append(
                    TGAPIDocument(
                        title=candidate.title,
                        pdf_url=clean_cand_url,
                        source_url=clean_cand_url,
                        document_date=candidate.source_date,
                        retrieved_date=datetime.utcnow(),
                    )
                )
            else:
                logger.info("No direct PI PDFs found for '%s'; skipping", product_page.product_name)
                return None

        # Step 5: Select the latest valid PDF
        selected_doc = TGAVersionSelector.select_latest(pi_documents)
        if not selected_doc:
            return None

        # Step 6: Route PDF to existing PDF extractor
        logger.info(
            "Routing selected PDF (%s) for '%s' to existing PDF extractor",
            selected_doc.pdf_url,
            product_page.product_name,
        )
        extraction_data = await self.pdf_handler.extract_sections(
            pdf_source=selected_doc.pdf_url,
            doc_name=f"{product_page.product_name}_PI.pdf",
        )
        if not extraction_data or extraction_data.get("error"):
            logger.warning("PDF extraction failed or incomplete for '%s'; skipping", product_page.product_name)
            return None

        # Step 7: Isolate Section 4.6 and Section 4.8
        processed_sections = TGASectionExtractor.process_sections(extraction_data)
        sec_4_6 = processed_sections["section_4_6"]
        sec_4_8 = processed_sections["section_4_8"]

        # Only register valid medicines with actual extracted regulatory sections
        if (
            sec_4_6.text_content == MISSING_SECTION_4_6_TEXT
            and sec_4_8.text_content == MISSING_SECTION_4_8_TEXT
        ):
            logger.info("Neither section 4.6 nor 4.8 found in PDF for '%s'; skipping", product_page.product_name)
            return None

        # Step 8: Build Harmonized Regulatory Record
        return self._build_candidate_entry(
            product_page=product_page,
            doc=selected_doc,
            sec_4_6=sec_4_6,
            sec_4_8=sec_4_8,
        )

    def _build_candidate_entry(
        self,
        product_page: TGAProductPage,
        doc: TGAPIDocument,
        sec_4_6: ExtractedSection,
        sec_4_8: ExtractedSection,
    ) -> Dict[str, Any]:
        """Maps extracted regulatory data into the dictionary format expected by DatabaseService."""
        safety_changes: List[Dict[str, Any]] = []

        doc_date_iso = (
            doc.document_date.isoformat()
            if doc.document_date
            else datetime.utcnow().isoformat()
        )
        rev_date_iso = (
            doc.revision_date.isoformat()
            if doc.revision_date
            else doc_date_iso
        )

        # Section 4.6 Safety Change Record
        hash_4_6 = hashlib.sha256(
            f"{product_page.product_name}|4.6|{sec_4_6.text_content}".encode()
        ).hexdigest()

        safety_changes.append({
            "source": SOURCE_ID,
            "section": SECTION_4_6_CANONICAL,
            "change_type": "Product Information - Section 4.6",
            "source_date": rev_date_iso,
            "source_record_id": f"TGA-PI-4.6-{hash_4_6[:10].upper()}",
            "source_url": doc.pdf_url,
            "original_text": sec_4_6.text_content,
            "updated_text": (
                f"{sec_4_6.title}\n"
                f"Pages: {sec_4_6.pages_str or 'N/A'}\n"
                f"Document Date: {doc_date_iso[:10]}\n\n"
                f"{sec_4_6.text_content}"
            ),
            "fda_comment": (
                f"Australian TGA Product Information Section 4.6 (Pages: {sec_4_6.pages_str or 'N/A'}). "
                f"PDF: {doc.pdf_url}"
            ),
            "content_hash": hash_4_6,
        })

        # Section 4.8 Safety Change Record (with Adverse Reaction Tables)
        tables_summary = ""
        if sec_4_8.tables:
            # Only append tables if not already embedded cleanly in text_content
            already_embedded = any(
                t.markdown and (t.markdown[:60] in sec_4_8.text_content)
                for t in sec_4_8.tables
            )
            if not already_embedded:
                tables_summary = "\n\n" + "\n\n".join(
                    f"### {t.caption} (Page {t.page})\n{t.markdown}" for t in sec_4_8.tables
                )

        full_4_8_text = f"{sec_4_8.text_content}{tables_summary}".strip()
        hash_4_8 = hashlib.sha256(
            f"{product_page.product_name}|4.8|{full_4_8_text}".encode()
        ).hexdigest()

        safety_changes.append({
            "source": SOURCE_ID,
            "section": SECTION_4_8_CANONICAL,
            "change_type": "Product Information - Section 4.8",
            "source_date": rev_date_iso,
            "source_record_id": f"TGA-PI-4.8-{hash_4_8[:10].upper()}",
            "source_url": doc.pdf_url,
            "original_text": full_4_8_text,
            "updated_text": (
                f"{sec_4_8.title}\n"
                f"Pages: {sec_4_8.pages_str or 'N/A'}\n"
                f"Document Date: {doc_date_iso[:10]}\n\n"
                f"{full_4_8_text}"
            ),
            "fda_comment": (
                f"Australian TGA Product Information Section 4.8 (Pages: {sec_4_8.pages_str or 'N/A'}, "
                f"Tables extracted: {len(sec_4_8.tables)}). PDF: {doc.pdf_url}"
            ),
            "content_hash": hash_4_8,
        })

        return {
            "display_name": product_page.product_name.upper(),
            "drug_name": product_page.product_name.upper(),
            "normalized_name": NormalizationService.normalize_drug_name(product_page.product_name),
            "active_ingredient": product_page.active_ingredient or product_page.product_name.upper(),
            "application_number": product_page.application_number or "AUST R / Listed",
            "source": SOURCE_ID,
            "sponsor": product_page.sponsor or "Australian Sponsor (TGA Registered)",
            "dosage_form": product_page.dosage_form or "Therapeutic Good (Australia)",
            "pi_url": doc.pdf_url,
            "cmi_url": product_page.cmi_links[0] if product_page.cmi_links else None,
            "safety_changes": safety_changes,
        }

    def _get_fallback_drug(self, norm_query: str, raw_query: str) -> Optional[Dict[str, Any]]:
        """Returns curated benchmark data for resilient operation during CDN blocks."""
        for key, drug in TGA_CURATED_REGISTRY.items():
            if key in norm_query or norm_query in key:
                copied = dict(drug)
                copied["source"] = SOURCE_ID

                safety_changes: List[Dict[str, Any]] = []
                # Build 4.6
                sec_4_6 = drug.get("section_4_6", {})
                txt_4_6 = sec_4_6.get("content", MISSING_SECTION_4_6_TEXT)
                h_4_6 = hashlib.sha256(f"{key}|4.6|{txt_4_6}".encode()).hexdigest()
                safety_changes.append({
                    "source": SOURCE_ID,
                    "section": SECTION_4_6_CANONICAL,
                    "change_type": "Product Information - Section 4.6",
                    "source_date": drug.get("revision_date", "2024-01-01") + "T00:00:00",
                    "source_record_id": f"TGA-PI-4.6-{h_4_6[:10].upper()}",
                    "source_url": drug.get("pdf_url"),
                    "original_text": txt_4_6,
                    "updated_text": f"{sec_4_6.get('title', '')}\nPages: {sec_4_6.get('pages', 'N/A')}\n\n{txt_4_6}",
                    "fda_comment": f"Australian TGA Product Information Section 4.6 (Pages: {sec_4_6.get('pages', 'N/A')})",
                    "content_hash": h_4_6,
                })

                # Build 4.8
                sec_4_8 = drug.get("section_4_8", {})
                txt_4_8 = sec_4_8.get("content", MISSING_SECTION_4_8_TEXT)
                h_4_8 = hashlib.sha256(f"{key}|4.8|{txt_4_8}".encode()).hexdigest()
                safety_changes.append({
                    "source": SOURCE_ID,
                    "section": SECTION_4_8_CANONICAL,
                    "change_type": "Product Information - Section 4.8",
                    "source_date": drug.get("revision_date", "2024-01-01") + "T00:00:00",
                    "source_record_id": f"TGA-PI-4.8-{h_4_8[:10].upper()}",
                    "source_url": drug.get("pdf_url"),
                    "original_text": txt_4_8,
                    "updated_text": f"{sec_4_8.get('title', '')}\nPages: {sec_4_8.get('pages', 'N/A')}\n\n{txt_4_8}",
                    "fda_comment": f"Australian TGA Product Information Section 4.8 (Pages: {sec_4_8.get('pages', 'N/A')})",
                    "content_hash": h_4_8,
                })

                copied["safety_changes"] = safety_changes
                return copied

        return None

    def parse_search_results(self, html: str, query: str = "") -> List[Dict[str, Any]]:
        """
        Backward compatibility helper matching original crawler interface.
        Extracts basic search items from HTML.
        """
        raw_items = self.search_engine.parse_search_results(html, query=query)
        if not raw_items:
            return []

        best_drug_name = query.upper()
        best_artg = raw_items[0].artg_number or "AUST R / Listed"
        best_active_ingredient = raw_items[0].active_ingredient or query.upper()
        best_sponsor = "Australian Sponsor (TGA Registered)"

        extracted_changes = []
        for r in raw_items:
            rec_id = f"TGA-{hashlib.sha256(r.url.encode()).hexdigest()[:12].upper()}"
            extracted_changes.append({
                "source": SOURCE_ID,
                "section": "Product Information (PI)",
                "change_type": "TGA Regulatory Action",
                "source_date": r.source_date.isoformat() if r.source_date else datetime.utcnow().isoformat(),
                "source_record_id": rec_id,
                "source_url": r.url,
                "original_text": r.title,
                "updated_text": f"{r.title}\n\n{r.snippet}".strip(),
                "fda_comment": f"Sourced from Australia TGA: {r.url}",
            })

        return [{
            "display_name": best_drug_name,
            "normalized_name": NormalizationService.normalize_drug_name(best_drug_name),
            "active_ingredient": best_active_ingredient,
            "application_number": best_artg,
            "source": SOURCE_ID,
            "sponsor": best_sponsor,
            "dosage_form": "Therapeutic Good (Australia)",
            "pi_url": raw_items[0].url if raw_items else None,
            "cmi_url": None,
            "safety_changes": extracted_changes,
        }]


# Global crawler instance
tga_crawler = AustraliaTGACrawler()
TGACrawler = AustraliaTGACrawler
