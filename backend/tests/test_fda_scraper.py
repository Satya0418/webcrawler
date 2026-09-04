"""Tests for FDA SrLC Scraper."""
import pytest
from app.scrapers.fda_srlc_scraper import scraper


class TestFDASrLCScraper:
    """Tests for FDASrLCScraper."""

    def test_parse_search_results_empty_html(self):
        """Test parsing empty HTML returns empty list."""
        result = scraper.parse_search_results("")
        assert result == []

    def test_parse_search_results_none(self):
        """Test parsing None HTML returns empty list."""
        result = scraper.parse_search_results(None)
        assert result == []

    def test_parse_detail_page_empty_html(self):
        """Test parsing empty detail page returns None."""
        result = scraper.parse_detail_page("")
        assert result is None

    def test_parse_detail_page_none(self):
        """Test parsing None detail page returns None."""
        result = scraper.parse_detail_page(None)
        assert result is None

    def test_extract_drug_name(self, sample_drug_record):
        """Test drug name extraction."""
        result = scraper.extract_drug_name(sample_drug_record)
        assert result == "Warfarin"

    def test_extract_active_ingredient(self, sample_drug_record):
        """Test active ingredient extraction."""
        result = scraper.extract_active_ingredient(sample_drug_record)
        assert result == "Warfarin"

    def test_extract_application_number(self, sample_drug_record):
        """Test application number extraction."""
        result = scraper.extract_application_number(sample_drug_record)
        assert result == "NDA-017388"

    def test_extract_safety_section(self, sample_drug_record):
        """Test safety section extraction."""
        result = scraper.extract_safety_section(sample_drug_record)
        assert result == "Warnings and Precautions"

    def test_extract_dates(self, sample_drug_record):
        """Test date extraction."""
        result = scraper.extract_dates(sample_drug_record)
        assert isinstance(result, dict)
        assert "source_date" in result
        assert "approval_date" in result
        assert "effective_date" in result

    def test_extract_text_fields(self, sample_drug_record):
        """Test text field extraction."""
        result = scraper.extract_text_fields(sample_drug_record)
        assert isinstance(result, dict)
        assert "original_text" in result
        assert "updated_text" in result
        assert "fda_comment" in result
        assert result["original_text"] == "Original warning text here."
        assert result["updated_text"] == "Updated warning text here."

    def test_extract_source_url(self, sample_drug_record):
        """Test source URL extraction."""
        result = scraper.extract_source_url(sample_drug_record)
        assert result is not None
        assert "fda.gov" in result

    def test_parse_search_results_with_real_fixture(self):
        """Test parsing real FDA search results fixture."""
        with open("tests/fixtures/fda/search_results_warfarin.html") as f:
            html = f.read()
        results = scraper.parse_search_results(html)
        assert len(results) >= 1
        record = results[0]
        assert record["drug_name"] == "COUMADIN"
        assert record["active_ingredient"] == "WARFARIN SODIUM"
        assert "NDA" in record["application_number"]
        assert record["source"] == "FDA_SRLC"

    def test_parse_detail_page_with_real_fixture(self):
        """Test parsing real FDA detail page fixture."""
        with open("tests/fixtures/fda/detail_warfarin.html") as f:
            html = f.read()
        detail = scraper.parse_detail_page(html)
        assert detail is not None
        assert detail["drug_name"] == "COUMADIN"
        assert detail["active_ingredient"] == "WARFARIN SODIUM"
        assert len(detail["safety_changes"]) > 0
        first_change = detail["safety_changes"][0]
        assert first_change["section"] is not None
        assert first_change["source_date"] is not None
        assert first_change["updated_text"] is not None

