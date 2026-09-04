"""Tests for normalization and change detection services."""
import pytest
from app.services.normalization import NormalizationService
from app.services.change_detection import ChangeDetectionService


class TestNormalizationService:
    """Tests for NormalizationService."""

    def test_normalize_drug_name_basic(self):
        """Test basic drug name normalization."""
        result = NormalizationService.normalize_drug_name("Warfarin")
        assert result == "warfarin"

    def test_normalize_drug_name_with_spaces(self):
        """Test normalization with extra spaces."""
        result = NormalizationService.normalize_drug_name("  Warfarin   ")
        assert result == "warfarin"

    def test_normalize_drug_name_multiple_spaces(self):
        """Test normalization with multiple internal spaces."""
        result = NormalizationService.normalize_drug_name("Drug    Name    Test")
        assert result == "drug name test"

    def test_normalize_drug_name_empty(self):
        """Test normalization of empty string."""
        result = NormalizationService.normalize_drug_name("")
        assert result == ""

    def test_normalize_active_ingredient(self):
        """Test active ingredient normalization."""
        result = NormalizationService.normalize_active_ingredient("Warfarin Sodium")
        assert result == "warfarin sodium"

    def test_normalize_text(self):
        """Test text normalization."""
        text = "This  is   some    text  with   extra   spaces"
        result = NormalizationService.normalize_text(text)
        assert result == "This is some text with extra spaces"

    def test_normalize_text_empty(self):
        """Test normalization of empty text."""
        result = NormalizationService.normalize_text("")
        assert result == ""

    def test_normalize_section_name_exact_match(self):
        """Test section name normalization with exact match."""
        result = NormalizationService.normalize_section_name("Boxed Warning")
        assert result == "Boxed Warning"

    def test_normalize_section_name_lowercase(self):
        """Test section name normalization with lowercase input."""
        result = NormalizationService.normalize_section_name("boxed warning")
        assert result == "Boxed Warning"

    def test_normalize_section_name_warnings_variation(self):
        """Test section name normalization with warnings variation."""
        result = NormalizationService.normalize_section_name("warnings")
        assert result == "Warnings and Precautions"

    def test_build_normalized_record(self):
        """Test building a normalized record."""
        raw_record = {
            "drug_name": "Warfarin",
            "active_ingredient": "Warfarin Sodium",
            "application_number": "NDA-017388",
            "section": "Warnings and Precautions",
            "original_text": "Original text",
            "updated_text": "Updated text",
            "fda_comment": "FDA comment",
        }
        result = NormalizationService.build_normalized_record(raw_record)
        
        assert result["display_name"] == "Warfarin"
        assert result["normalized_name"] == "warfarin"
        assert isinstance(result, dict)
        assert "display_name" in result
        assert "normalized_name" in result
        assert "original_text" in result


class TestChangeDetectionService:
    """Tests for ChangeDetectionService."""

    def test_generate_content_hash(self, sample_drug_record):
        """Test content hash generation."""
        hash_value = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA-256 produces 64 hex characters
        assert hash_value.isalnum()

    def test_generate_content_hash_consistency(self, sample_drug_record):
        """Test that same record produces same hash."""
        hash1 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        hash2 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        assert hash1 == hash2

    def test_generate_content_hash_changes_with_content(self, sample_drug_record):
        """Test that different content produces different hash."""
        hash1 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        modified_record = sample_drug_record.copy()
        modified_record["original_text"] = "Different text"
        hash2 = ChangeDetectionService.generate_content_hash(modified_record)
        
        assert hash1 != hash2

    def test_detect_change_new_record(self, sample_drug_record):
        """Test detecting a new record (no existing hash)."""
        is_changed = ChangeDetectionService.detect_change(sample_drug_record, None)
        assert is_changed is True

    def test_detect_change_unchanged(self, sample_drug_record):
        """Test detecting an unchanged record."""
        existing_hash = ChangeDetectionService.generate_content_hash(sample_drug_record)
        is_changed = ChangeDetectionService.detect_change(sample_drug_record, existing_hash)
        assert is_changed is False

    def test_detect_change_changed(self, sample_drug_record):
        """Test detecting a changed record."""
        existing_hash = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        modified_record = sample_drug_record.copy()
        modified_record["updated_text"] = "Completely different text now"
        is_changed = ChangeDetectionService.detect_change(modified_record, existing_hash)
        
        assert is_changed is True

    def test_compare_hashes_matching(self, sample_drug_record):
        """Test comparing matching hashes."""
        hash1 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        hash2 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        result = ChangeDetectionService.compare_hashes(hash1, hash2)
        assert result is True

    def test_compare_hashes_different(self, sample_drug_record):
        """Test comparing different hashes."""
        hash1 = ChangeDetectionService.generate_content_hash(sample_drug_record)
        
        modified_record = sample_drug_record.copy()
        modified_record["original_text"] = "Modified"
        hash2 = ChangeDetectionService.generate_content_hash(modified_record)
        
        result = ChangeDetectionService.compare_hashes(hash1, hash2)
        assert result is False
