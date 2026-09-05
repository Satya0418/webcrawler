"""
Database Service for managing drug records and version history.
Handles insert, update, and version creation with change detection.
"""
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc

from app.models.drug import Drug, SafetyLabelingChange, SafetyChangeVersion, CrawlRun
from app.services.normalization import NormalizationService
from app.services.validation import ValidationService
from app.services.change_detection import ChangeDetectionService

from app.scrapers.fda_srlc_scraper import parse_fda_date

logger = logging.getLogger(__name__)


def _parse_date(val: Any) -> Optional[datetime]:
    """Parse string or datetime into datetime using robust FDA date parser."""
    return parse_fda_date(val)


class DatabaseService:
    """Service for managing drug records in database."""

    @staticmethod
    def insert_or_update_drug(
        session: Session,
        drug_data: Dict[str, Any]
    ) -> Tuple[Drug, bool]:
        """
        Insert new drug or return existing.

        Args:
            session: Database session
            drug_data: Normalized drug data

        Returns:
            Tuple of (Drug record, is_new: bool)
        """
        try:
            display_name = drug_data.get("display_name") or drug_data.get("drug_name") or ""
            normalized_name = drug_data.get("normalized_name") or NormalizationService.normalize_drug_name(display_name)

            # Check if drug exists by normalized_name
            query = select(Drug).where(Drug.normalized_name == normalized_name)
            result = session.execute(query)
            existing_drug = result.scalars().first()

            if existing_drug:
                if not existing_drug.active_ingredient and drug_data.get("active_ingredient"):
                    existing_drug.active_ingredient = drug_data.get("active_ingredient")
                if not existing_drug.application_number and drug_data.get("application_number"):
                    existing_drug.application_number = drug_data.get("application_number")
                existing_drug.updated_at = datetime.utcnow()
                session.flush()
                return existing_drug, False

            # Create new drug
            drug = Drug(
                display_name=display_name,
                normalized_name=normalized_name,
                active_ingredient=drug_data.get("active_ingredient"),
                application_number=drug_data.get("application_number"),
                source=drug_data.get("source", "FDA_SRLC"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            session.add(drug)
            session.flush()

            logger.info(f"Created new drug: {normalized_name} (ID: {drug.id})")
            return drug, True

        except Exception as e:
            logger.error(f"Error inserting/updating drug: {e}", exc_info=True)
            raise

    @staticmethod
    def save_safety_change(
        session: Session,
        drug_id: int,
        change_data: Dict[str, Any]
    ) -> Tuple[SafetyLabelingChange, bool]:
        """
        Save safety change with version tracking.

        Args:
            session: Database session
            drug_id: ID of drug this change relates to
            change_data: Change information

        Returns:
            Tuple of (SafetyLabelingChange record, is_new: bool)
        """
        try:
            # Look up drug to get display name if missing
            drug = session.get(Drug, drug_id)
            if drug and not change_data.get("display_name"):
                change_data["display_name"] = drug.display_name

            if not change_data.get("source_url"):
                change_data["source_url"] = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges"

            # Parse dates into datetime objects before validation
            source_date = _parse_date(change_data.get("source_date"))
            approval_date = _parse_date(change_data.get("approval_date"))
            effective_date = _parse_date(change_data.get("effective_date"))

            change_data["source_date"] = source_date
            change_data["approval_date"] = approval_date
            change_data["effective_date"] = effective_date

            # Normalize and validate
            normalized_section = NormalizationService.normalize_section_name(
                change_data.get("section") or change_data.get("labeling_section") or ""
            )
            change_data["section"] = normalized_section
            ValidationService.validate_record(change_data)

            # Generate content hash
            content_hash = ChangeDetectionService.generate_content_hash(change_data)
            source_record_id = change_data.get("source_record_id")
            section_name = change_data.get("section") or "General Safety"

            # 1. Check if exact record exists with identical hash
            query_exact = select(SafetyLabelingChange).where(
                (SafetyLabelingChange.drug_id == drug_id) &
                (SafetyLabelingChange.section == section_name) &
                (SafetyLabelingChange.content_hash == content_hash)
            )
            if source_record_id:
                query_exact = query_exact.where(SafetyLabelingChange.source_record_id == source_record_id)

            result = session.execute(query_exact)
            existing_exact = result.scalars().first()

            if existing_exact:
                existing_exact.last_verified_at = datetime.utcnow()
                session.flush()
                logger.debug(f"Exact match found for drug {drug_id}, record {source_record_id}, section {section_name}")
                return existing_exact, False

            # 2. Check if record for same drug, supplement, and section exists with different content (change detected)
            query_prev = select(SafetyLabelingChange).where(
                (SafetyLabelingChange.drug_id == drug_id) &
                (SafetyLabelingChange.section == section_name)
            )
            if source_record_id:
                query_prev = query_prev.where(SafetyLabelingChange.source_record_id == source_record_id)

            result = session.execute(query_prev)
            previous_change = result.scalars().first()

            if previous_change:
                old_hash = previous_change.content_hash
                old_updated_text = previous_change.updated_text
                old_original_text = previous_change.original_text

                count_res = session.execute(
                    select(func.count(SafetyChangeVersion.id)).where(
                        SafetyChangeVersion.safety_change_id == previous_change.id
                    )
                )
                ver_count = count_res.scalar() or 0

                # Archive previous version
                version = SafetyChangeVersion(
                    safety_change_id=previous_change.id,
                    version_number=ver_count + 1,
                    content_hash=old_hash,
                    original_text=old_original_text,
                    updated_text=old_updated_text,
                    normalized_content=f"{previous_change.section}: {old_updated_text}",
                    retrieved_at=previous_change.last_verified_at or datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )
                session.add(version)

                # Update main record
                previous_change.content_hash = content_hash
                previous_change.original_text = change_data.get("original_text") or old_updated_text
                previous_change.updated_text = change_data.get("updated_text")
                previous_change.source_date = source_date or previous_change.source_date
                previous_change.approval_date = approval_date or previous_change.approval_date
                previous_change.effective_date = effective_date or previous_change.effective_date
                previous_change.fda_comment = change_data.get("fda_comment") or previous_change.fda_comment
                previous_change.source_url = change_data.get("source_url") or previous_change.source_url
                previous_change.source_record_id = source_record_id or previous_change.source_record_id
                previous_change.last_verified_at = datetime.utcnow()
                previous_change.updated_at = datetime.utcnow()

                session.flush()
                logger.info(f"Updated safety change for drug {drug_id}, record {source_record_id}, section {section_name} (v{ver_count + 1} archived)")
                return previous_change, True

            # 3. Create new safety change record
            safety_change = SafetyLabelingChange(
                drug_id=drug_id,
                source=change_data.get("source", "FDA_SRLC"),
                source_record_id=source_record_id,
                section=section_name,
                change_type=change_data.get("change_type", "Labeling Revision"),
                source_date=source_date,
                approval_date=approval_date,
                effective_date=effective_date,
                original_text=change_data.get("original_text"),
                updated_text=change_data.get("updated_text"),
                fda_comment=change_data.get("fda_comment"),
                source_url=change_data.get("source_url"),
                content_hash=content_hash,
                first_seen_at=datetime.utcnow(),
                last_verified_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

            session.add(safety_change)
            session.flush()
            logger.info(f"New safety change created: drug {drug_id}, record {source_record_id}, section {section_name}")
            return safety_change, True

        except Exception as e:
            logger.error(f"Error saving safety change: {e}", exc_info=True)
            raise

    @staticmethod
    def get_drug_by_id(session: Session, drug_id: int) -> Optional[Drug]:
        """Get drug by ID."""
        result = session.execute(
            select(Drug).where(Drug.id == drug_id)
        )
        return result.scalars().first()

    @staticmethod
    def get_drug_by_normalized_name(session: Session, name: str) -> Optional[Drug]:
        """Get drug by normalized name."""
        normalized = NormalizationService.normalize_drug_name(name)
        result = session.execute(
            select(Drug).where(Drug.normalized_name == normalized)
        )
        return result.scalars().first()

    @staticmethod
    def search_drugs(session: Session, query: str, limit: int = 50) -> List[Drug]:
        """Search for drugs by name or active ingredient."""
        normalized = NormalizationService.normalize_drug_name(query)
        result = session.execute(
            select(Drug)
            .where(
                (Drug.normalized_name.like(f"%{normalized}%")) |
                (Drug.active_ingredient.like(f"%{query}%")) |
                (Drug.display_name.like(f"%{query}%"))
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    def get_safety_changes_by_drug_id(session: Session, drug_id: int) -> List[SafetyLabelingChange]:
        """Get safety changes for a given drug, chronologically descending."""
        result = session.execute(
            select(SafetyLabelingChange)
            .where(SafetyLabelingChange.drug_id == drug_id)
            .order_by(desc(SafetyLabelingChange.source_date), desc(SafetyLabelingChange.id))
        )
        return list(result.scalars().all())

    @staticmethod
    def get_safety_change_by_id(session: Session, change_id: int) -> Optional[SafetyLabelingChange]:
        """Get safety change by ID."""
        result = session.execute(
            select(SafetyLabelingChange).where(SafetyLabelingChange.id == change_id)
        )
        return result.scalars().first()

    @staticmethod
    def get_versions_by_change_id(session: Session, change_id: int) -> List[SafetyChangeVersion]:
        """Get version history for a safety change."""
        result = session.execute(
            select(SafetyChangeVersion)
            .where(SafetyChangeVersion.safety_change_id == change_id)
            .order_by(desc(SafetyChangeVersion.version_number))
        )
        return list(result.scalars().all())
