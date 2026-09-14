"""
Unit and integration tests for Health Canada DPD Crawler and search adapter integration.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.sources.health_canada.dpd_crawler import HealthCanadaDPDCrawler, dpd_crawler
from app.services.database_service import DatabaseService
from app.sources.health_canada.infowatch.adapter import adapter as hc_adapter
from app.models.drug import Drug, SafetyLabelingChange


class TestDPDCrawler:
    """Test HealthCanadaDPDCrawler methods."""

    @pytest.mark.asyncio
    async def test_search_medicine_short_query(self):
        """Short query returns empty list without making requests."""
        crawler = HealthCanadaDPDCrawler()
        res = await crawler.search_medicine("a")
        assert res == []

    @pytest.mark.asyncio
    async def test_search_medicine_mocked_success(self):
        """Test successful DPD product search and detail assembly."""
        mock_products = [
            {
                "drug_code": 96058,
                "drug_identification_number": "02471469",
                "brand_name": "OZEMPIC",
                "company_name": "NOVO NORDISK CANADA INC",
                "last_update_date": "2026-08-13",
            }
        ]
        mock_details = {
            "active_ingredient": "SEMAGLUTIDE 1.34 MG/ML",
            "status": "Marketed",
            "status_date": "2018-02-22",
            "form": "Solution",
            "route": "Subcutaneous",
            "monograph_url": "https://pdf.hres.ca/dpd_pm/00085314.PDF",
        }
        mock_recalls = [
            {
                "title": "Ozempic Recall Notice",
                "url": "https://recalls-rappels.canada.ca/en/alert-recall/ozempic-test",
                "date": "2026-01-15",
                "desc": "Test recall summary",
            }
        ]

        crawler = HealthCanadaDPDCrawler()
        with patch.object(crawler, "_query_dpd_products", new_callable=AsyncMock) as mock_q, \
             patch.object(crawler, "_fetch_product_details", new_callable=AsyncMock) as mock_d, \
             patch.object(crawler, "_query_safety_recalls", new_callable=AsyncMock) as mock_r:
            
            mock_q.return_value = mock_products
            mock_d.return_value = mock_details
            mock_r.return_value = mock_recalls

            results = await crawler.search_medicine("Ozempic")

            assert len(results) == 1
            drug = results[0]
            assert drug["display_name"] == "OZEMPIC"
            assert drug["application_number"] == "02471469"
            assert drug["active_ingredient"] == "SEMAGLUTIDE 1.34 MG/ML"
            assert drug["company_name"] == "NOVO NORDISK CANADA INC"
            assert drug["source"] == "HEALTH_CANADA"

            # Should contain monograph update and safety recall
            changes = drug["safety_changes"]
            assert len(changes) == 2
            sections = [c["section"] for c in changes]
            assert "Product Monograph Update" in sections
            assert "Adverse Reaction Information" in sections

    @pytest.mark.asyncio
    async def test_search_medicine_network_error_handled(self):
        """Crawler handles HTTP errors gracefully."""
        crawler = HealthCanadaDPDCrawler()
        with patch.object(crawler, "_query_dpd_products", side_effect=Exception("Connection refused")):
            res = await crawler.search_medicine("UnknownDrug")
            assert res == []


class TestCrossSourceCollisionPrevention:
    """Test that FDA and Health Canada drugs with identical names do not collide."""

    def test_fda_and_hc_drugs_coexist(self, db):
        """FDA and Health Canada drug records for 'Tecfidera' can coexist with different metadata."""
        # 1. Insert FDA drug
        fda_data = {
            "display_name": "TECFIDERA",
            "active_ingredient": "DIMETHYL FUMARATE",
            "application_number": "NDA-204063",
            "source": "FDA_SRLC",
        }
        fda_drug, is_new_fda = DatabaseService.insert_or_update_drug(db, fda_data)
        assert is_new_fda is True
        assert fda_drug.source == "FDA_SRLC"

        # 2. Insert Health Canada drug with same normalized name
        hc_data = {
            "display_name": "TECFIDERA",
            "active_ingredient": "DIMETHYL FUMARATE 120 MG",
            "application_number": "02404508",  # Canadian DIN
            "source": "HEALTH_CANADA",
        }
        hc_drug, is_new_hc = DatabaseService.insert_or_update_drug(db, hc_data)
        assert is_new_hc is True
        assert hc_drug.id != fda_drug.id
        assert hc_drug.source == "HEALTH_CANADA"
        assert hc_drug.application_number == "02404508"

        # 3. Search filtered by FDA
        fda_results = DatabaseService.search_drugs(db, "Tecfidera", source="FDA")
        assert len(fda_results) == 1
        assert fda_results[0].source == "FDA_SRLC"
        assert fda_results[0].application_number == "NDA-204063"

        # 4. Search filtered by Health Canada
        hc_results = DatabaseService.search_drugs(db, "Tecfidera", source="HEALTH_CANADA")
        assert len(hc_results) == 1
        assert hc_results[0].source == "HEALTH_CANADA"
        assert hc_results[0].application_number == "02404508"

        # 5. Search ALL returns both
        all_results = DatabaseService.search_drugs(db, "Tecfidera", source="ALL")
        assert len(all_results) == 2
        sources = {d.source for d in all_results}
        assert "FDA_SRLC" in sources
        assert "HEALTH_CANADA" in sources

    def test_search_by_din(self, db):
        """Searching by Canadian DIN finds the drug."""
        hc_data = {
            "display_name": "OZEMPIC",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "02471469",
            "source": "HEALTH_CANADA",
        }
        DatabaseService.insert_or_update_drug(db, hc_data)

        results = DatabaseService.search_drugs(db, "02471469")
        assert len(results) == 1
        assert results[0].display_name == "OZEMPIC"
