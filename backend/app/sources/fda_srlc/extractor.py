"""
FDA SrLC Extractor.
Orchestrates Date-First selection, Section Prioritization (AR -> WP -> Pregnancy/USP),
historical date isolation, and PDF section extraction integration.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, Tag

from app.sources.fda_srlc.date_parser import (
    extract_supplement_id,
    format_fda_date_to_report,
    parse_fda_date,
    select_latest_date_and_records,
)
from app.sources.fda_srlc.document_discovery import FDASrLCDocumentDiscovery
from app.sources.fda_srlc.models import (
    FDASafetySections,
    FDASectionResult,
    FDASrLCStructuredResult,
    FDASupplementRecord,
)
from app.sources.fda_srlc.pdf_handler import FDASrLCPDFHandler
from app.sources.fda_srlc.section_detector import (
    FDASrLCSectionDetector,
    clean_adverse_reaction_text,
    clean_fda_element_text,
    clean_general_section_text,
    sanitize_fda_section_html,
)
from app.sources.fda_srlc.validator import FDASrLCValidator

logger = logging.getLogger(__name__)

NOT_FOUND_MSG = "NOT FOUND IN THE LATEST APPLICABLE FDA LABELING UPDATE"


class FDASrLCExtractor:
    """Extracts safety labeling information strictly enforcing Date-First and Section Priority rules."""

    def __init__(
        self,
        pdf_handler: Optional[FDASrLCPDFHandler] = None,
        doc_discovery: Optional[FDASrLCDocumentDiscovery] = None,
    ) -> None:
        self.pdf_handler = pdf_handler or FDASrLCPDFHandler()
        self.doc_discovery = doc_discovery or FDASrLCDocumentDiscovery()
        self.section_detector = FDASrLCSectionDetector()

    def parse_supplement_records_from_detail_html(
        self,
        html_content: str,
        source_url: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], List[FDASupplementRecord]]:
        """
        Parses all supplement updates from an FDA SrLC detail page.

        Returns:
            Tuple of (drug_name, active_ingredient, application_number, list of FDASupplementRecord)
        """
        if not html_content:
            return None, None, None, []

        soup = BeautifulSoup(html_content, "lxml")

        # 1. Extract Drug Name & Application Number
        drug_name = None
        application_number = None

        for h in soup.find_all(["h2", "h3"]):
            text = h.get_text(strip=True)
            match = re.search(r"^([^\(]+?)\s*\(\s*([A-Za-z]+[\s\-]?\d+)\s*\)", text)
            if match:
                drug_name = match.group(1).strip()
                application_number = match.group(2).strip()
                break

        if not drug_name:
            title_elem = soup.find(["h1", "h2", "h3"])
            if title_elem:
                raw_t = title_elem.get_text(strip=True)
                drug_name = re.sub(r"\s*\(.*?\)", "", raw_t).strip()

        # 2. Extract Active Ingredient (e.g. (LINEZOLID))
        active_ingredient = None
        for h in soup.find_all(["h4", "h5"]):
            text = h.get_text(strip=True)
            if text.startswith("(") and text.endswith(")"):
                active_ingredient = text.strip("() \t\n\r")
                break

        # 3. Parse Accordion items
        accordion = soup.find("div", id="accordion") or soup.find(
            "div", class_=lambda c: c and "accordion" in str(c)
        )
        if not accordion:
            return drug_name, active_ingredient, application_number, []

        supplement_records: List[FDASupplementRecord] = []

        for h3 in accordion.find_all("h3"):
            header_text = h3.get_text(strip=True)
            dt_obj = parse_fda_date(header_text)
            if not dt_obj:
                continue

            suppl_id = extract_supplement_id(header_text)
            panel = h3.find_next_sibling("div")
            if not panel:
                continue

            # Discover official label PDF
            doc_url = self.doc_discovery.discover_label_pdf_url(panel)

            # Extract sections from HTML panel
            sections_data = []
            h4_tags = panel.find_all("h4")
            for h4 in h4_tags:
                raw_sec_name = re.sub(r"\s+", " ", h4.get_text()).strip()

                # Collect sibling elements up to the next h4
                section_elements = []
                for sib in h4.next_siblings:
                    if getattr(sib, "name", None) == "h4":
                        break
                    if getattr(sib, "name", None):
                        section_elements.append(sib)

                elem_texts = [clean_fda_element_text(elem) for elem in section_elements]
                formatted_text = "\n\n".join([t for t in elem_texts if t]).strip()

                raw_html_snippets = "".join(str(elem) for elem in section_elements)
                sanitized_html = sanitize_fda_section_html(raw_html_snippets)

                sections_data.append({
                    "raw_section": raw_sec_name,
                    "text": formatted_text,
                    "html": sanitized_html,
                })

            supp_rec = FDASupplementRecord(
                header_text=header_text,
                date_str=dt_obj.strftime("%m/%d/%Y"),
                date_obj=dt_obj,
                supplement_id=suppl_id,
                document_url=doc_url,
                sections=sections_data,
            )
            supplement_records.append(supp_rec)

        return drug_name, active_ingredient, application_number, supplement_records

    async def extract_latest_update(
        self,
        drug_name: str,
        active_ingredient: Optional[str],
        application_number: Optional[str],
        all_supplement_records: List[FDASupplementRecord],
        source_url: Optional[str] = None,
    ) -> FDASrLCStructuredResult:
        """
        DATE-FIRST WORKFLOW:
        1. Select the latest date and all records belonging to that date.
        2. Inspect sections with priority:
           - 1. Adverse Reactions
           - 2. Warnings and Precautions
           - 3. Use in Specific Populations / Pregnancy
        3. Never backfill missing sections from older dates.
        """
        if not all_supplement_records:
            logger.info("FDA_SRLC_NO_MATCH: No supplement records available for '%s'", drug_name)
            sections_container = FDASafetySections(
                adverse_reactions=FDASectionResult(found=False, content=NOT_FOUND_MSG),
                warnings_and_precautions=FDASectionResult(found=False, content=NOT_FOUND_MSG),
                pregnancy=FDASectionResult(found=False, content=NOT_FOUND_MSG),
            )
            res = FDASrLCStructuredResult(
                source="FDA SrLC",
                product=drug_name,
                active_ingredient=active_ingredient,
                application_number=application_number,
                sections=sections_container,
            )
            return FDASrLCValidator.validate_and_hash_result(res)

        # 1. DATE-FIRST LOGIC: Select strictly the latest date
        latest_dt, latest_records = select_latest_date_and_records(
            all_supplement_records,
            date_extractor_func=lambda r: r.date_obj,
        )

        if not latest_dt or not latest_records:
            sections_container = FDASafetySections(
                adverse_reactions=FDASectionResult(found=False, content=NOT_FOUND_MSG),
                warnings_and_precautions=FDASectionResult(found=False, content=NOT_FOUND_MSG),
                pregnancy=FDASectionResult(found=False, content=NOT_FOUND_MSG),
            )
            res = FDASrLCStructuredResult(
                product=drug_name,
                active_ingredient=active_ingredient,
                application_number=application_number,
                sections=sections_container,
            )
            return FDASrLCValidator.validate_and_hash_result(res)

        latest_date_str = latest_dt.strftime("%m/%d/%Y")
        formatted_report_date = format_fda_date_to_report(latest_dt)

        # Aggregate supplement IDs and document URLs from all records belonging to this latest date
        all_suppl_ids = list(dict.fromkeys([
            r.supplement_id for r in latest_records if r.supplement_id
        ]))
        combined_suppl_id = ", ".join(all_suppl_ids) if all_suppl_ids else None

        # Find official label PDF if present on any record for this latest date
        doc_url = None
        for r in latest_records:
            if r.document_url:
                doc_url = r.document_url
                break

        # PDF extraction if document is available
        pdf_extractions = None
        if doc_url:
            try:
                pdf_extractions = await self.pdf_handler.extract_fda_sections_from_pdf(
                    doc_url, doc_name=f"{drug_name}_{latest_date_str.replace('/', '_')}.pdf"
                )
            except Exception as e:
                logger.warning("Error running PDF extraction on %s: %s", doc_url, e)

        # Aggregate all HTML sections present across the latest date's records
        all_sections: List[Dict[str, Any]] = []
        for r in latest_records:
            all_sections.extend(r.sections)

        # SECTION PRIORITY 1: ADVERSE REACTIONS
        ar_result = self._extract_adverse_reactions(
            all_sections=all_sections,
            pdf_data=pdf_extractions.get("section_6") if pdf_extractions else None,
            date_str=latest_date_str,
            source_url=source_url,
            doc_url=doc_url,
        )
        if ar_result.found:
            logger.info("FDA_SRLC_ADVERSE_REACTIONS_FOUND: Found for %s on %s", drug_name, latest_date_str)
        else:
            logger.info("FDA_SRLC_ADVERSE_REACTIONS_NOT_FOUND: Absent for %s on %s", drug_name, latest_date_str)

        # SECTION PRIORITY 2: WARNINGS AND PRECAUTIONS
        wp_result = self._extract_warnings_and_precautions(
            all_sections=all_sections,
            pdf_data=pdf_extractions.get("section_5") if pdf_extractions else None,
            date_str=latest_date_str,
            source_url=source_url,
            doc_url=doc_url,
        )
        if wp_result.found:
            logger.info("FDA_SRLC_WARNINGS_FOUND: Found for %s on %s", drug_name, latest_date_str)
        else:
            logger.info("FDA_SRLC_WARNINGS_NOT_FOUND: Absent for %s on %s", drug_name, latest_date_str)

        # SECTION PRIORITY 3: PREGNANCY / USE IN SPECIFIC POPULATIONS
        preg_result = self._extract_pregnancy(
            all_sections=all_sections,
            pdf_data=pdf_extractions.get("section_8") if pdf_extractions else None,
            date_str=latest_date_str,
            source_url=source_url,
            doc_url=doc_url,
        )
        if preg_result.found:
            logger.info("FDA_SRLC_PREGNANCY_FOUND: Found for %s on %s", drug_name, latest_date_str)
        else:
            logger.info("FDA_SRLC_PREGNANCY_NOT_FOUND: Absent for %s on %s", drug_name, latest_date_str)

        sections_container = FDASafetySections(
            adverse_reactions=ar_result,
            warnings_and_precautions=wp_result,
            pregnancy=preg_result,
        )

        structured = FDASrLCStructuredResult(
            source="FDA SrLC",
            product=drug_name,
            active_ingredient=active_ingredient,
            latest_labeling_change_date=latest_date_str,
            supplement_number=combined_suppl_id,
            application_number=application_number,
            sections=sections_container,
        )

        return FDASrLCValidator.validate_and_hash_result(structured)

    def _extract_adverse_reactions(
        self,
        all_sections: List[Dict[str, Any]],
        pdf_data: Optional[Dict[str, Any]],
        date_str: str,
        source_url: Optional[str],
        doc_url: Optional[str],
    ) -> FDASectionResult:
        """Extract Adverse Reactions section for the latest date only."""
        # Find matching sections in HTML
        matching_text = [
            s["text"] for s in all_sections
            if self.section_detector.is_adverse_reactions(s["raw_section"]) and s.get("text")
        ]
        matching_html = [
            s["html"] for s in all_sections
            if self.section_detector.is_adverse_reactions(s["raw_section"]) and s.get("html")
        ]

        if matching_text or matching_html:
            cleaned_text = clean_adverse_reaction_text("\n\n".join(matching_text))
            html_snippet = "".join(matching_html) if matching_html else None
            page_str = None
            if pdf_data:
                sp = pdf_data.get("start_page")
                ep = pdf_data.get("end_page")
                page_str = f"{sp}-{ep}" if sp and ep and sp != ep else str(sp or ep or "")

            return FDASectionResult(
                found=True,
                content=cleaned_text,
                html_content=html_snippet,
                section="Adverse Reactions",
                date=date_str,
                source_url=source_url,
                document_url=doc_url,
                page=page_str if page_str else None,
            )

        # If not present in HTML change table, do NOT invent or pull older dates
        return FDASectionResult(
            found=False,
            content=NOT_FOUND_MSG,
            html_content=None,
            section=None,
            date=None,
            source_url=source_url,
            document_url=doc_url,
            page=None,
        )

    def _extract_warnings_and_precautions(
        self,
        all_sections: List[Dict[str, Any]],
        pdf_data: Optional[Dict[str, Any]],
        date_str: str,
        source_url: Optional[str],
        doc_url: Optional[str],
    ) -> FDASectionResult:
        """Extract Warnings and Precautions section for the latest date only."""
        matching_text = [
            s["text"] for s in all_sections
            if self.section_detector.is_warnings_and_precautions(s["raw_section"]) and s.get("text")
        ]
        matching_html = [
            s["html"] for s in all_sections
            if self.section_detector.is_warnings_and_precautions(s["raw_section"]) and s.get("html")
        ]

        if matching_text or matching_html:
            cleaned_text = clean_general_section_text("\n\n".join(matching_text))
            html_snippet = "".join(matching_html) if matching_html else None
            page_str = None
            if pdf_data:
                sp = pdf_data.get("start_page")
                ep = pdf_data.get("end_page")
                page_str = f"{sp}-{ep}" if sp and ep and sp != ep else str(sp or ep or "")

            return FDASectionResult(
                found=True,
                content=cleaned_text,
                html_content=html_snippet,
                section="Warnings and Precautions",
                date=date_str,
                source_url=source_url,
                document_url=doc_url,
                page=page_str if page_str else None,
            )

        return FDASectionResult(
            found=False,
            content=NOT_FOUND_MSG,
            html_content=None,
            section=None,
            date=None,
            source_url=source_url,
            document_url=doc_url,
            page=None,
        )

    def _extract_pregnancy(
        self,
        all_sections: List[Dict[str, Any]],
        pdf_data: Optional[Dict[str, Any]],
        date_str: str,
        source_url: Optional[str],
        doc_url: Optional[str],
    ) -> FDASectionResult:
        """Extract Pregnancy / Use in Specific Populations section for the latest date only."""
        matching_text = [
            s["text"] for s in all_sections
            if self.section_detector.is_use_in_specific_populations(s["raw_section"]) and s.get("text")
        ]
        matching_html = [
            s["html"] for s in all_sections
            if self.section_detector.is_use_in_specific_populations(s["raw_section"]) and s.get("html")
        ]

        if matching_text or matching_html:
            raw_usp = "\n\n".join(matching_text)
            preg_content = self.section_detector.extract_pregnancy_subsections(raw_usp)

            if preg_content:
                page_str = None
                if pdf_data:
                    sp = pdf_data.get("start_page")
                    ep = pdf_data.get("end_page")
                    page_str = f"{sp}-{ep}" if sp and ep and sp != ep else str(sp or ep or "")

                return FDASectionResult(
                    found=True,
                    content=preg_content,
                    html_content="".join(matching_html) if matching_html else None,
                    section="Use in Specific Populations",
                    date=date_str,
                    source_url=source_url,
                    document_url=doc_url,
                    page=page_str if page_str else None,
                )

        return FDASectionResult(
            found=False,
            content=NOT_FOUND_MSG,
            html_content=None,
            section=None,
            date=None,
            source_url=source_url,
            document_url=doc_url,
            page=None,
        )
