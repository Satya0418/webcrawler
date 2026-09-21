"""
Validation and integrity checks for FDA SrLC extracted data.
Computes stable content hashes for deduplication and versioning.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict

from app.sources.fda_srlc.models import FDASrLCStructuredResult

logger = logging.getLogger(__name__)


class FDASrLCValidator:
    """Validates FDA SrLC structured outputs and generates deterministic content hashes."""

    @staticmethod
    def generate_section_hash(
        drug_name: str,
        section_name: str,
        content: str,
        date_str: str,
    ) -> str:
        """
        Generate a deterministic SHA-256 hash for a specific safety change section.
        """
        raw_key = f"{drug_name.strip().lower()}|{section_name.strip().lower()}|{date_str.strip()}|{content.strip()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_and_hash_result(result: FDASrLCStructuredResult) -> FDASrLCStructuredResult:
        """
        Validates completeness and sets content hashes on all found sections.
        """
        if not result.product:
            raise ValueError("FDA SrLC validation failed: Missing product name")

        if result.sections:
            drug = result.product
            date_val = result.latest_labeling_change_date or "unknown"

            # Adverse Reactions
            ar = result.sections.adverse_reactions
            if ar.found and ar.content:
                ar.content_hash = FDASrLCValidator.generate_section_hash(
                    drug, "Adverse Reactions", ar.content, ar.date or date_val
                )

            # Warnings and Precautions
            wp = result.sections.warnings_and_precautions
            if wp.found and wp.content:
                wp.content_hash = FDASrLCValidator.generate_section_hash(
                    drug, "Warnings and Precautions", wp.content, wp.date or date_val
                )

            # Pregnancy
            preg = result.sections.pregnancy
            if preg.found and preg.content:
                preg.content_hash = FDASrLCValidator.generate_section_hash(
                    drug, "Use in Specific Populations", preg.content, preg.date or date_val
                )

        logger.info("FDA_SRLC_VALIDATION_COMPLETED: Successfully validated result for '%s'", result.product)
        return result
