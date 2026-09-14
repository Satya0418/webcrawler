"""
Unit and integration tests for Australia TGA Crawler, Adapter, and DB integration.
"""
import pytest
from app.models.drug import Drug, SafetyLabelingChange
from app.services.database_service import DatabaseService
from app.sources.australia_tga.tga_crawler import AustraliaTGACrawler, tga_crawler
from app.sources.australia_tga.adapter import AustraliaTGAAdapter, tga_adapter


class TestTGACrawler:
    """Unit tests for AustraliaTGACrawler."""

    @pytest.mark.asyncio
    async def test_search_medicine_empty(self):
        crawler = AustraliaTGACrawler(live_fetch=False)
        res = await crawler.search_medicine("")
        assert res == []

        res2 = await crawler.search_medicine("a")
        assert res2 == []

    @pytest.mark.asyncio
    async def test_search_medicine_curated_ozempic(self):
        crawler = AustraliaTGACrawler(live_fetch=False)
        results = await crawler.search_medicine("Ozempic")
        assert len(results) >= 1
        item = results[0]
        assert item["display_name"] == "OZEMPIC"
        assert item["active_ingredient"] == "SEMAGLUTIDE"
        assert "AUST R 308323" in item["application_number"]
        assert item["source"] == "AUSTRALIA_TGA"
        assert len(item["safety_changes"]) >= 2

    @pytest.mark.asyncio
    async def test_search_medicine_curated_tecfidera(self):
        crawler = AustraliaTGACrawler(live_fetch=False)
        results = await crawler.search_medicine("Tecfidera")
        assert len(results) >= 1
        item = results[0]
        assert item["display_name"] == "TECFIDERA"
        assert item["active_ingredient"] == "DIMETHYL FUMARATE"
        assert "AUST R 197475" in item["application_number"]
        assert item["source"] == "AUSTRALIA_TGA"

    @pytest.mark.asyncio
    async def test_search_medicine_generic(self):
        crawler = AustraliaTGACrawler(live_fetch=False)
        results = await crawler.search_medicine("Atorvastatin")
        assert len(results) >= 1
        item = results[0]
        assert "ATORVASTATIN" in item["display_name"]
        assert item["source"] == "AUSTRALIA_TGA"
        assert len(item["safety_changes"]) >= 1

    def test_parse_search_results_mock_html(self):
        crawler = AustraliaTGACrawler(live_fetch=False)
        mock_html = """
        <html>
        <body>
            <main>
                <div class="search-result">
                    <h3><a href="/safety/alerts/medicines/ozempic-alert">Ozempic (semaglutide) safety update</a></h3>
                    <span class="date">15 February 2024</span>
                    <p class="snippet">TGA warning regarding AUST R 308323 supply issues and counterfeit pens.</p>
                </div>
                <div class="search-result">
                    <h3><a href="/resources/prescription-medicines-registrations/ozempic-pi">Product Information: Ozempic</a></h3>
                    <span class="date">20 November 2023</span>
                    <p class="snippet">Australian Product Information document for Ozempic semaglutide.</p>
                </div>
            </main>
        </body>
        </html>
        """
        parsed = crawler.parse_search_results(mock_html, query="Ozempic")
        assert len(parsed) == 1
        drug = parsed[0]
        assert drug["display_name"] == "OZEMPIC"
        assert drug["active_ingredient"] == "SEMAGLUTIDE"
        assert drug["application_number"] == "AUST R 308323"
        assert drug["source"] == "AUSTRALIA_TGA"
        assert len(drug["safety_changes"]) == 2


class TestTGAAdapter:
    """Integration tests for AustraliaTGAAdapter."""

    @pytest.mark.asyncio
    async def test_adapter_search_and_persistence(self, db):
        crawler = AustraliaTGACrawler(live_fetch=False)
        adapter = AustraliaTGAAdapter(crawler=crawler)
        drugs = await adapter.search("Tecfidera", db=db, force_refresh=True)
        assert len(drugs) >= 1
        drug = drugs[0]
        assert drug.display_name == "TECFIDERA"
        assert drug.source == "AUSTRALIA_TGA"
        assert drug.application_number == "AUST R 197475"

        # Verify safety changes persisted
        changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        assert len(changes) >= 1
        assert any("PML" in (c.updated_text or "") for c in changes)

    @pytest.mark.asyncio
    async def test_adapter_caching(self, db):
        crawler = AustraliaTGACrawler(live_fetch=False)
        adapter = AustraliaTGAAdapter(crawler=crawler)
        # First call inserts
        await adapter.search("Aspirin", db=db, force_refresh=True)
        # Second call returns cached from DB
        cached = await adapter.search("Aspirin", db=db, force_refresh=False)
        assert len(cached) >= 1
        assert cached[0].source == "AUSTRALIA_TGA"


class TestTriSourceCoexistence:
    """Verify FDA, Health Canada, and Australia TGA coexist in the DB."""

    @pytest.mark.asyncio
    async def test_tri_source_drugs_coexist(self, db):
        # 1. Insert FDA drug
        fda_data = {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "NDA-209637",
            "source": "FDA_SRLC",
        }
        fda_drug, _ = DatabaseService.insert_or_update_drug(db, fda_data)

        # 2. Insert Health Canada drug
        hc_data = {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE 1.34 MG/ML",
            "application_number": "02471469",
            "source": "HEALTH_CANADA",
        }
        hc_drug, _ = DatabaseService.insert_or_update_drug(db, hc_data)

        # 3. Insert Australia TGA drug
        tga_data = {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "AUST R 308323",
            "source": "AUSTRALIA_TGA",
        }
        tga_drug, _ = DatabaseService.insert_or_update_drug(db, tga_data)
        db.commit()

        # Verify all 3 have distinct IDs
        assert fda_drug.id != hc_drug.id
        assert hc_drug.id != tga_drug.id
        assert fda_drug.id != tga_drug.id

        # Search ALL sources
        all_drugs = DatabaseService.search_drugs(db, "ozempic", source="ALL")
        assert len(all_drugs) == 3

        # Search Australia TGA only
        tga_only = DatabaseService.search_drugs(db, "ozempic", source="AUSTRALIA_TGA")
        assert len(tga_only) == 1
        assert tga_only[0].source == "AUSTRALIA_TGA"
        assert tga_only[0].application_number == "AUST R 308323"

        # Search Health Canada only
        hc_only = DatabaseService.search_drugs(db, "ozempic", source="HEALTH_CANADA")
        assert len(hc_only) == 1
        assert hc_only[0].source == "HEALTH_CANADA"

        # Search FDA only
        fda_only = DatabaseService.search_drugs(db, "ozempic", source="FDA_SRLC")
        assert len(fda_only) == 1
        assert fda_only[0].source == "FDA_SRLC"

    def test_search_by_aust_r(self, db):
        tga_data = {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "AUST R 308323",
            "source": "AUSTRALIA_TGA",
        }
        DatabaseService.insert_or_update_drug(db, tga_data)
        db.commit()

        found = DatabaseService.search_drugs(db, "308323")
        assert len(found) >= 1
        assert found[0].application_number == "AUST R 308323"
