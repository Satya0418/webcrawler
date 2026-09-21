"""
FDA MedWatch Validator.
Validates extracted results, checks required traceability metadata,
and generates cryptographic content hashes for change detection.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict

from app.sources.fda_medwatch.models import MedWatchStructuredResult

logger = logging.getLogger(__name__)


class FDAMedWatchValidator:
    """Validates FDA MedWatch structured extraction results."""

    @classmethod
    def calculate_content_hash(cls, result: MedWatchStructuredResult) -> str:
        """Computes deterministic SHA256 content hash for change detection."""
        sections = result.sections or {}
        ar = sections.get("adverse_reactions", {})
        wp = sections.get("warnings_and_precautions", {})
        preg = sections.get("pregnancy", {})
        pi = result.product_information or {}

        hash_payload = {
            "product": result.product.strip().lower(),
            "active_ingredient": (result.active_ingredient or "").strip().lower(),
            "pdf_url": (pi.get("pdf_url") or "").strip(),
            "document_date": (pi.get("document_date") or "").strip(),
            "adverse_reactions": (ar.get("content") or "").strip(),
            "warnings_and_precautions": (wp.get("content") or "").strip(),
            "pregnancy": (preg.get("content") or "").strip(),
        }
        serialized = json.dumps(hash_payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def validate_and_hash_result(cls, result: MedWatchStructuredResult) -> MedWatchStructuredResult:
        """
        Validates the extracted result and injects content hash.
        Checks for traceability: when a section is marked found, verifies that content is non-empty.
        """
        if not result.product:
            raise ValueError("MedWatchStructuredResult must contain a valid product name")

        sections = result.sections or {}
        for sec_name, sec_data in sections.items():
            if isinstance(sec_data, dict) and sec_data.get("found"):
                content = sec_data.get("content", "").strip()
                if not content:
                    logger.warning("FDA_MEDWATCH_VALIDATION_WARNING: Found %s with empty content for %s", sec_name, result.product)

        result.content_hash = cls.calculate_content_hash(result)

        ar = sections.get("adverse_reactions", {})
        if isinstance(ar, dict) and ar.get("found"):
            logger.info(
                "FDA_MEDWATCH_ADVERSE_REACTIONS_VALIDATION_COMPLETED: Validated Adverse Reactions for product '%s' (status: %s, found: %s, pages: %s, subsections: %d, tables: %d)",
                result.product,
                result.status,
                ar.get("found"),
                ar.get("pages") or ar.get("page"),
                len(ar.get("subsections", [])),
                len(ar.get("tables", [])),
            )
        elif result.status == "PRODUCT_MISMATCH_REJECTED":
            logger.warning(
                "FDA_MEDWATCH_ERROR: Validation failure - PDF product mismatch for requested product '%s'",
                result.product,
            )
        else:
            logger.info(
                "FDA_MEDWATCH_ADVERSE_REACTIONS_VALIDATION_COMPLETED: Validated safety result for product '%s' (status: %s)",
                result.product,
                result.status,
            )

        logger.info("FDA_MEDWATCH_VALIDATION_COMPLETED: Product '%s', status '%s', hash %s", result.product, result.status, result.content_hash[:12])
        return result

