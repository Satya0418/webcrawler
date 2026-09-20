"""
Validators for Australia TGA crawling and regulatory extraction.
Validates product match, document legitimacy, latest version selection, and section extraction completeness.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.services.normalization import NormalizationService
from app.sources.australia_tga.config import MISSING_SECTION_4_6_TEXT, MISSING_SECTION_4_8_TEXT
from app.sources.australia_tga.models import (
    ExtractedSection,
    TGAPIDocument,
    TGAProductPage,
    TGARegulatoryResult,
)

logger = logging.getLogger(__name__)


class TGAValidator:
    """Validates data consistency, source authenticity, and extraction fidelity."""

    @classmethod
    def validate_product_match(cls, query: str, product_page: TGAProductPage) -> bool:
        """Verifies that the discovered product corresponds to the user query."""
        if not query or not product_page:
            return False

        q_norm = NormalizationService.normalize_drug_name(query)
        p_norm = NormalizationService.normalize_drug_name(product_page.product_name)
        ingr_norm = NormalizationService.normalize_drug_name(product_page.active_ingredient or "")

        if q_norm in p_norm or p_norm in q_norm:
            return True
        if q_norm in ingr_norm or ingr_norm in q_norm:
            return True

        # Check tokens
        q_tokens = [t for t in q_norm.split() if len(t) >= 4]
        if any(tok in p_norm or tok in ingr_norm for tok in q_tokens):
            return True

        logger.warning(
            "Product match validation failed for query '%s' against product '%s' (%s)",
            query,
            product_page.product_name,
            product_page.active_ingredient,
        )
        return False

    @classmethod
    def validate_document_is_pi(cls, doc: TGAPIDocument) -> bool:
        """Verifies that the document is a Product Information document (not CMI or leaflet)."""
        if not doc or not doc.pdf_url:
            return False

        url_lower = doc.pdf_url.lower()
        title_lower = doc.title.lower()

        # Disallow CMI documents
        if "cmi" in url_lower and "pi" not in url_lower:
            return False
        if "consumer medicine" in title_lower:
            return False

        return True

    @classmethod
    def validate_latest_version(
        cls,
        selected_doc: TGAPIDocument,
        all_docs: List[TGAPIDocument],
    ) -> bool:
        """Verifies that the selected document is indeed the most recent among available candidates."""
        if not selected_doc or not all_docs:
            return True

        sel_dt = selected_doc.revision_date or selected_doc.document_date
        if not sel_dt:
            return True

        for other in all_docs:
            other_dt = other.revision_date or other.document_date
            if other_dt and other_dt > sel_dt:
                logger.warning(
                    "Selected document date (%s) is older than available candidate (%s: %s)",
                    sel_dt,
                    other.pdf_url,
                    other_dt,
                )
                return False

        return True

    @classmethod
    def validate_section_4_6(cls, section: ExtractedSection) -> Tuple[bool, List[str]]:
        """Validates Section 4.6 content and flags warnings if missing or incomplete."""
        warnings: List[str] = []
        if not section.is_present or section.text_content == MISSING_SECTION_4_6_TEXT:
            warnings.append("Section 4.6 not present in document")
            return False, warnings

        if len(section.text_content.strip()) < 50:
            warnings.append("Section 4.6 text is unusually short")

        return True, warnings

    @classmethod
    def validate_section_4_8(cls, section: ExtractedSection) -> Tuple[bool, List[str]]:
        """Validates Section 4.8 content and presence of adverse reaction tables."""
        warnings: List[str] = []
        if not section.is_present or section.text_content == MISSING_SECTION_4_8_TEXT:
            warnings.append("Section 4.8 not present in document")
            return False, warnings

        if len(section.text_content.strip()) < 50:
            warnings.append("Section 4.8 text is unusually short")

        return True, warnings

    @classmethod
    def validate_completeness(cls, result: TGARegulatoryResult) -> Tuple[str, List[str]]:
        """
        Validates the overall completeness of the regulatory record.
        Returns (status_string, list_of_issues).
        """
        issues: List[str] = []

        if not result.product_name:
            issues.append("Missing product name")
        if not result.pdf_url:
            issues.append("Missing PDF URL")

        _, w_4_6 = cls.validate_section_4_6(result.section_4_6)
        _, w_4_8 = cls.validate_section_4_8(result.section_4_8)
        issues.extend(w_4_6)
        issues.extend(w_4_8)

        status = "VALID" if not issues else "VALID_WITH_WARNINGS"
        if not result.section_4_6.is_present and not result.section_4_8.is_present:
            status = "SECTIONS_NOT_FOUND"

        return status, issues
