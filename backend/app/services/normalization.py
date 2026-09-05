"""
Service for normalization of extracted FDA data.
"""
import logging
from typing import Dict, Any, Optional
import re

logger = logging.getLogger(__name__)


class NormalizationService:
    """Service for normalizing FDA data."""

    @staticmethod
    def normalize_drug_name(name: str) -> str:
        """
        Normalize drug name for consistent matching.

        - Remove extra whitespace
        - Convert to lowercase
        - Remove special characters
        """
        if not name:
            return ""

        # Strip whitespace
        name = name.strip()
        # Remove extra spaces
        name = re.sub(r'\s+', ' ', name)
        # Convert to lowercase
        name = name.lower()

        return name

    @staticmethod
    def normalize_active_ingredient(ingredient: str) -> str:
        """Normalize active ingredient name."""
        if not ingredient:
            return ""

        return NormalizationService.normalize_drug_name(ingredient)

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize FDA text for comparison.

        - Remove excess whitespace
        - Normalize line breaks
        """
        if not text:
            return ""

        # Remove excess whitespace
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    @staticmethod
    def normalize_section_name(section: str) -> str:
        """Normalize labeling section name."""
        if not section:
            return ""

        clean = re.sub(r"^\d+[\s\.\-]+", "", section).strip().lower()
        clean_no_parens = re.sub(r"\(.*?\)", "", clean).strip()

        # Map common variations to standard names
        section_mapping = {
            "boxed warning": "Boxed Warning",
            "contraindications": "Contraindications",
            "warnings": "Warnings and Precautions",
            "warnings and precautions": "Warnings and Precautions",
            "adverse reactions": "Adverse Reactions",
            "adverse events": "Adverse Reactions",
            "drug interactions": "Drug Interactions",
            "use in specific populations": "Use in Specific Populations",
            "patient counseling": "Patient Counseling Information",
            "patient counseling information": "Patient Counseling Information",
            "patient information": "Patient Information",
            "medication guide": "Medication Guide",
            "pci/pi/mg": "Patient Counseling Information",
        }

        for key, standard in section_mapping.items():
            if key in clean_no_parens or clean_no_parens in key:
                return standard

        return section_mapping.get(clean_no_parens, section.strip().title())

    @staticmethod
    def build_normalized_record(raw_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a normalized record from raw FDA data.

        Args:
            raw_record: Raw extracted record

        Returns:
            Normalized record with consistent field structure
        """
        normalized = {
            "display_name": raw_record.get("drug_name", ""),
            "normalized_name": NormalizationService.normalize_drug_name(
                raw_record.get("drug_name", "")
            ),
            "active_ingredient": NormalizationService.normalize_active_ingredient(
                raw_record.get("active_ingredient", "")
            ),
            "application_number": raw_record.get("application_number"),
            "section": NormalizationService.normalize_section_name(
                raw_record.get("section", "")
            ),
            "source_date": raw_record.get("source_date"),
            "approval_date": raw_record.get("approval_date"),
            "effective_date": raw_record.get("effective_date"),
            "original_text": NormalizationService.normalize_text(
                raw_record.get("original_text", "")
            ),
            "updated_text": NormalizationService.normalize_text(
                raw_record.get("updated_text", "")
            ),
            "fda_comment": NormalizationService.normalize_text(
                raw_record.get("fda_comment", "")
            ),
            "source_url": raw_record.get("source_url"),
            "source_record_id": raw_record.get("source_record_id"),
        }

        return normalized
