"""
Service for validating extracted and normalized FDA data.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


class ValidationService:
    """Service for validating FDA records."""

    # Supported labeling sections
    SUPPORTED_SECTIONS = {
        "Boxed Warning",
        "Contraindications",
        "Warnings and Precautions",
        "Adverse Reactions",
        "Drug Interactions",
        "Use in Specific Populations",
        "Patient Counseling Information",
        "Patient Information",
        "Medication Guide",
    }

    @staticmethod
    def validate_record(record: Dict[str, Any]) -> bool:
        """
        Validate a normalized FDA record.

        Args:
            record: Normalized record to validate

        Returns:
            True if record is valid, raises ValidationError otherwise
        """
        errors: List[str] = []

        # Validate required fields
        if not record.get("display_name"):
            errors.append("display_name is required and cannot be empty")

        if not record.get("source_url"):
            errors.append("source_url is required")

        # Validate dates
        date_fields = ["source_date", "approval_date", "effective_date"]
        for field in date_fields:
            value = record.get(field)
            if value and not isinstance(value, datetime):
                errors.append(f"{field} must be a datetime object")

        # Validate section
        section = record.get("section")
        if section:
            clean_sec = re.sub(r"^\d+[\s\.\-]+", "", section).strip().lower()
            clean_sec = re.sub(r"\(.*?\)", "", clean_sec).strip()
            is_recognized = any(
                s.lower() in clean_sec or clean_sec in s.lower()
                for s in ValidationService.SUPPORTED_SECTIONS
            )
            if not is_recognized:
                logger.warning(
                    f"Unknown section '{section}', but allowing it. "
                    f"Supported sections: {ValidationService.SUPPORTED_SECTIONS}"
                )

        # Validate text fields are not obviously corrupted
        text_fields = ["original_text", "updated_text", "fda_comment"]
        for field in text_fields:
            text = record.get(field)
            if text and len(text) > 0:
                # Basic sanity check: text should not be mostly special characters
                if ValidationService._is_corrupted_text(text):
                    errors.append(f"{field} appears to be corrupted or malformed")

        if errors:
            error_msg = "; ".join(errors)
            logger.error(f"Validation failed: {error_msg}")
            raise ValidationError(error_msg)

        return True

    @staticmethod
    def _is_corrupted_text(text: str) -> bool:
        """
        Check if text appears to be corrupted or malformed.

        Returns True if text looks suspicious.
        """
        if not text or len(text) < 5:
            return False

        # Check for excessive HTML tags
        if text.count("<") > text.count(" "):
            return True

        # Check for excessive special characters relative to letters
        special_count = sum(1 for c in text if not c.isalnum() and not c.isspace())
        alpha_count = sum(1 for c in text if c.isalpha())

        if alpha_count > 0 and special_count / alpha_count > 1:
            return True

        return False

    @staticmethod
    def validate_no_duplicates(
        new_record: Dict[str, Any], existing_records: List[Dict[str, Any]]
    ) -> bool:
        """
        Check if record is a duplicate of an existing record.

        Uses key fields to detect duplicates.
        """
        for existing in existing_records:
            if (
                existing.get("display_name") == new_record.get("display_name")
                and existing.get("section") == new_record.get("section")
                and existing.get("source_date") == new_record.get("source_date")
            ):
                # Same drug, same section, same date = likely duplicate
                return False

        return True
