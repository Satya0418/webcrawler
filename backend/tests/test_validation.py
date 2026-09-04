"""Tests for data validation service."""
import pytest
from app.services.validation import ValidationService, ValidationError


class TestValidationService:
    """Tests for ValidationService."""

    def test_validate_record_valid(self, sample_drug_record):
        """Test validating a valid record."""
        # Ensure required fields are present
        sample_drug_record["display_name"] = "Warfarin"
        sample_drug_record["source_url"] = "https://fda.gov/test"
        
        result = ValidationService.validate_record(sample_drug_record)
        assert result is True

    def test_validate_record_missing_display_name(self, sample_drug_record):
        """Test validation fails without display_name."""
        sample_drug_record["display_name"] = ""
        sample_drug_record["source_url"] = "https://fda.gov/test"
        
        with pytest.raises(ValidationError):
            ValidationService.validate_record(sample_drug_record)

    def test_validate_record_missing_source_url(self, sample_drug_record):
        """Test validation fails without source_url."""
        sample_drug_record["display_name"] = "Warfarin"
        sample_drug_record["source_url"] = None
        
        with pytest.raises(ValidationError):
            ValidationService.validate_record(sample_drug_record)

    def test_validate_record_unknown_section(self, sample_drug_record):
        """Test validation allows unknown sections (with warning)."""
        sample_drug_record["display_name"] = "Warfarin"
        sample_drug_record["source_url"] = "https://fda.gov/test"
        sample_drug_record["section"] = "Unknown Section Type"
        
        # Should not raise error, just log warning
        result = ValidationService.validate_record(sample_drug_record)
        assert result is True

    def test_validate_record_corrupted_text(self, sample_drug_record):
        """Test validation detects corrupted text."""
        sample_drug_record["display_name"] = "Warfarin"
        sample_drug_record["source_url"] = "https://fda.gov/test"
        # Text with excessive special characters
        sample_drug_record["original_text"] = "<<<<<>>>>>|||||***###@@@"
        
        with pytest.raises(ValidationError):
            ValidationService.validate_record(sample_drug_record)

    def test_validate_no_duplicates_new_record(self, sample_drug_record):
        """Test no duplicates detection for new record."""
        result = ValidationService.validate_no_duplicates(sample_drug_record, [])
        assert result is True

    def test_validate_no_duplicates_exact_match(self, sample_drug_record):
        """Test duplicate detection for exact match."""
        existing_records = [sample_drug_record]
        
        result = ValidationService.validate_no_duplicates(sample_drug_record, existing_records)
        assert result is False

    def test_validate_no_duplicates_different_drug(self, sample_drug_record):
        """Test no duplicates for different drug."""
        different_record = sample_drug_record.copy()
        different_record["display_name"] = "Different Drug"
        
        existing_records = [sample_drug_record]
        
        result = ValidationService.validate_no_duplicates(different_record, existing_records)
        assert result is True

    def test_validate_no_duplicates_different_section(self, sample_drug_record):
        """Test no duplicates for same drug, different section."""
        different_section = sample_drug_record.copy()
        different_section["section"] = "Adverse Reactions"
        
        existing_records = [sample_drug_record]
        
        result = ValidationService.validate_no_duplicates(different_section, existing_records)
        assert result is True

    def test_is_corrupted_text_excessive_special_chars(self):
        """Test corrupted text detection with excessive special characters."""
        corrupted = "<<<<<>>>|||@@##$$$%"
        result = ValidationService._is_corrupted_text(corrupted)
        assert result is True

    def test_is_corrupted_text_excessive_html(self):
        """Test corrupted text detection with excessive HTML."""
        corrupted = "<div><p><span><a><b><i><u><em>"
        result = ValidationService._is_corrupted_text(corrupted)
        assert result is True

    def test_is_corrupted_text_normal(self):
        """Test normal text is not marked as corrupted."""
        normal = "This is normal drug safety information with some punctuation!"
        result = ValidationService._is_corrupted_text(normal)
        assert result is False

    def test_is_corrupted_text_short(self):
        """Test short text is not marked as corrupted."""
        short = "ABC"
        result = ValidationService._is_corrupted_text(short)
        assert result is False
