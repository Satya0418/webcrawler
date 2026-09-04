"""
Service for detecting changes in FDA records using content hashing.
"""
import hashlib
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ChangeDetectionService:
    """Service for detecting changes in FDA records using SHA-256 hashing."""

    @staticmethod
    def generate_content_hash(record: Dict[str, Any]) -> str:
        """
        Generate SHA-256 hash for a normalized record.

        Hash is based on key fields that determine uniqueness.

        Args:
            record: Normalized record

        Returns:
            SHA-256 hash as hex string
        """
        # Fields to include in hash
        # Order matters for consistency
        hash_fields = [
            record.get("display_name", ""),
            record.get("active_ingredient", ""),
            record.get("section", ""),
            str(record.get("source_date", "")),
            record.get("original_text", ""),
            record.get("updated_text", ""),
            record.get("fda_comment", ""),
        ]

        # Join fields with a delimiter
        content = "|".join(str(field) for field in hash_fields)

        # Generate SHA-256 hash
        content_bytes = content.encode("utf-8")
        hash_value = hashlib.sha256(content_bytes).hexdigest()

        return hash_value

    @staticmethod
    def detect_change(
        new_record: Dict[str, Any], existing_hash: Optional[str]
    ) -> bool:
        """
        Detect if a record has changed based on hash.

        Args:
            new_record: Normalized new record
            existing_hash: Existing content hash, if any

        Returns:
            True if record is new or changed, False if unchanged
        """
        if existing_hash is None:
            # New record
            return True

        new_hash = ChangeDetectionService.generate_content_hash(new_record)

        if new_hash != existing_hash:
            logger.info(
                f"Change detected: {new_record.get('display_name')} / {new_record.get('section')}"
            )
            return True

        logger.debug(
            f"No change: {new_record.get('display_name')} / {new_record.get('section')}"
        )
        return False

    @staticmethod
    def compare_hashes(hash1: str, hash2: str) -> bool:
        """
        Compare two content hashes.

        Returns:
            True if hashes match (no change), False if different
        """
        return hash1 == hash2
