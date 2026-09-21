"""
FDA MedWatch Section Extractor.
Coordinates section extraction priority (Adverse Reactions -> Warnings -> Pregnancy),
preserves auditability and page traceability, and builds the structured result.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.sources.fda_medwatch.config import (
    NO_OFFICIAL_PRODUCT_LABEL_FOUND,
    NOT_FOUND_IN_DOC_MSG,
)
from app.sources.fda_medwatch.models import (
    MedWatchArticle,
    MedWatchDocumentInfo,
    MedWatchSectionItem,
    MedWatchStructuredResult,
)
from app.sources.fda_medwatch.pdf_handler import FDAMedWatchPDFHandler
from app.sources.fda_medwatch.validator import FDAMedWatchValidator

logger = logging.getLogger(__name__)


class FDAMedWatchSectionExtractor:
    """Orchestrates structured safety extraction from discovered FDA label PDFs."""

    def __init__(self, pdf_handler: Optional[FDAMedWatchPDFHandler] = None) -> None:
        self.pdf_handler = pdf_handler or FDAMedWatchPDFHandler()

    async def extract_from_document(
        self,
        product: str,
        active_ingredient: Optional[str],
        application_number: Optional[str],
        article: Optional[MedWatchArticle],
        document: Optional[MedWatchDocumentInfo],
    ) -> MedWatchStructuredResult:
        """
        Extracts required safety sections from the authoritative document.
        If no document is available, returns a result marked PRODUCT_INFORMATION_DOCUMENT_NOT_FOUND
        preserving article metadata without fabricating labeling content.
        """
        article_dict = article.to_dict() if article else {}
        doc_dict = document.to_dict() if document else {}

        if not document or not document.found or not document.pdf_url:
            logger.info("FDA_MEDWATCH_NO_PRODUCT_DOCUMENT: No official label PDF available for '%s'", product)
            sections_dict = {
                "adverse_reactions": MedWatchSectionItem(
                    found=False,
                    content=NO_OFFICIAL_PRODUCT_LABEL_FOUND,
                    section="6. ADVERSE REACTIONS",
                ).to_dict(),
                "warnings_and_precautions": MedWatchSectionItem(
                    found=False,
                    content=NO_OFFICIAL_PRODUCT_LABEL_FOUND,
                    section="5. WARNINGS AND PRECAUTIONS",
                ).to_dict(),
                "pregnancy": MedWatchSectionItem(
                    found=False,
                    content=NO_OFFICIAL_PRODUCT_LABEL_FOUND,
                    section="8.1 PREGNANCY",
                ).to_dict(),
            }
            result = MedWatchStructuredResult(
                source="FDA MedWatch",
                product=product,
                active_ingredient=active_ingredient,
                application_number=application_number,
                status=NO_OFFICIAL_PRODUCT_LABEL_FOUND,
                medwatch_article=article_dict,
                product_information=doc_dict,
                sections=sections_dict,
            )
            return FDAMedWatchValidator.validate_and_hash_result(result)

        # Extract sections from PDF
        pdf_name = f"{product}_{document.version or 'label'}.pdf"
        sections_map = await self.pdf_handler.extract_sections(
            pdf_source=document.pdf_url,
            doc_name=pdf_name,
            pdf_url=document.pdf_url,
            document_date=document.document_date,
            version=document.version,
            target_product=product,
            active_ingredient=active_ingredient,
        )

        ar_dict = sections_map["adverse_reactions"].to_dict()
        wp_dict = sections_map["warnings_and_precautions"].to_dict()
        preg_dict = sections_map["pregnancy"].to_dict()

        sections_dict = {
            "adverse_reactions": ar_dict,
            "warnings_and_precautions": wp_dict,
            "pregnancy": preg_dict,
        }

        overall_status = sections_map["adverse_reactions"].status or ("SUCCESS" if sections_map["adverse_reactions"].found else "ADVERSE_REACTIONS_SECTION_NOT_FOUND")

        result = MedWatchStructuredResult(
            source="FDA MedWatch",
            product=product,
            active_ingredient=active_ingredient,
            application_number=application_number,
            status=overall_status,
            medwatch_article=article_dict,
            product_information=doc_dict,
            adverse_reactions=ar_dict,
            sections=sections_dict,
        )

        return FDAMedWatchValidator.validate_and_hash_result(result)

