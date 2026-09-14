"""
Tests for FDA MedWatch Crawler, Adapter, Database Persistence, and UI Rendering.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.fda_medwatch.medwatch_crawler import (
    FDAMedWatchCrawler,
    MEDWATCH_PORTAL_URL,
    MEDWATCH_REPORT_URL,
    medwatch_crawler,
)
from app.sources.fda_medwatch.adapter import FDAMedWatchAdapter, medwatch_adapter
from app.ui import render_drug_detail_html, _render_fda_medwatch_drug_detail


@pytest.mark.asyncio
async def test_medwatch_crawler_ozempic():
    crawler = FDAMedWatchCrawler(live_fetch=False)
    candidates = await crawler.search_medicine("Ozempic")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "OZEMPIC"
    assert c["active_ingredient"] == "SEMAGLUTIDE"
    assert "MW-FAERS" in c["application_number"]
    assert c["sponsor"] == "NOVO NORDISK INC"
    assert c["detail_url"] == MEDWATCH_PORTAL_URL
    assert len(c["safety_changes"]) >= 3

    types = [sc["change_type"] for sc in c["safety_changes"]]
    assert any("Counterfeit" in t for t in types)
    assert any("FAERS" in t or "Post-Marketing" in t for t in types)
    assert any("Recall" in t for t in types)


@pytest.mark.asyncio
async def test_medwatch_crawler_tecfidera():
    crawler = FDAMedWatchCrawler(live_fetch=False)
    candidates = await crawler.search_medicine("tecfidera")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "TECFIDERA"
    assert c["active_ingredient"] == "DIMETHYL FUMARATE"
    assert c["sponsor"] == "BIOGEN INC"
    assert any("PML" in sc["updated_text"] for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_medwatch_crawler_aspirin():
    crawler = FDAMedWatchCrawler(live_fetch=False)
    candidates = await crawler.search_medicine("aspirin")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "ASPIRIN"
    assert any("Reye" in sc["updated_text"] for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_medwatch_crawler_warfarin():
    crawler = FDAMedWatchCrawler(live_fetch=False)
    candidates = await crawler.search_medicine("warfarin")
    assert len(candidates) >= 1
    c = candidates[0]
    assert "WARFARIN" in c["display_name"]
    assert any("Bleeding" in sc["change_type"] or "bleeding" in sc["updated_text"].lower() for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_medwatch_crawler_generic_fallback():
    crawler = FDAMedWatchCrawler(live_fetch=False)
    candidates = await crawler.search_medicine("XyzNovelMed123")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "XYZNOVELMED123"
    assert c["source"] == "FDA_MEDWATCH"
    assert len(c["safety_changes"]) >= 1
    assert "Form 3500" in c["safety_changes"][0]["updated_text"]


@pytest.mark.asyncio
async def test_medwatch_adapter_search_and_save(db):
    crawler = FDAMedWatchCrawler(live_fetch=False)
    adapter = FDAMedWatchAdapter(crawler=crawler)

    drugs = await adapter.search("ozempic", db=db, force_refresh=True)
    assert len(drugs) >= 1
    d = drugs[0]
    assert d.source == "FDA_MEDWATCH"
    assert d.display_name == "OZEMPIC"
    assert "MW-FAERS" in d.application_number

    changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
    assert len(changes) >= 3
    assert all(c.source == "FDA_MEDWATCH" for c in changes)

    # Search again with force_refresh=False to test local DB caching
    cached_drugs = await adapter.search("ozempic", db=db, force_refresh=False)
    assert len(cached_drugs) == 1
    assert cached_drugs[0].id == d.id


@pytest.mark.asyncio
async def test_quad_authority_coexistence(db):
    """
    Verify that an identical medicine name (e.g. 'ozempic') can exist independently
    across all 4 regulatory programs: FDA SrLC, Health Canada, Australia TGA, and FDA MedWatch.
    """
    # 1. FDA SrLC
    fda_drug, _ = DatabaseService.insert_or_update_drug(
        db,
        {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "NDA-209637",
            "source": "FDA_SRLC",
        },
    )

    # 2. Health Canada
    hc_drug, _ = DatabaseService.insert_or_update_drug(
        db,
        {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "02471469",
            "source": "HEALTH_CANADA",
        },
    )

    # 3. Australia TGA
    tga_drug, _ = DatabaseService.insert_or_update_drug(
        db,
        {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "AUST R 308323",
            "source": "AUSTRALIA_TGA",
        },
    )

    # 4. FDA MedWatch
    mw_drug, _ = DatabaseService.insert_or_update_drug(
        db,
        {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "MW-FAERS-209637",
            "source": "FDA_MEDWATCH",
        },
    )

    db.commit()

    # Verify all 4 drug IDs are distinct
    assert len({fda_drug.id, hc_drug.id, tga_drug.id, mw_drug.id}) == 4

    # Verify source filtering in search_drugs
    mw_results = DatabaseService.search_drugs(db, "ozempic", source="FDA_MEDWATCH")
    assert len(mw_results) == 1
    assert mw_results[0].source == "FDA_MEDWATCH"
    assert mw_results[0].application_number == "MW-FAERS-209637"

    tga_results = DatabaseService.search_drugs(db, "ozempic", source="AUSTRALIA_TGA")
    assert len(tga_results) == 1
    assert tga_results[0].source == "AUSTRALIA_TGA"

    fda_results = DatabaseService.search_drugs(db, "ozempic", source="FDA_SRLC")
    assert len(fda_results) == 1
    assert fda_results[0].source == "FDA_SRLC"

    hc_results = DatabaseService.search_drugs(db, "ozempic", source="HEALTH_CANADA")
    assert len(hc_results) == 1
    assert hc_results[0].source == "HEALTH_CANADA"

    # Verify ALL source search returns all 4 records
    all_results = DatabaseService.search_drugs(db, "ozempic", source="ALL")
    assert len(all_results) >= 4
    sources = {d.source for d in all_results}
    assert {"FDA_SRLC", "HEALTH_CANADA", "AUSTRALIA_TGA", "FDA_MEDWATCH"}.issubset(sources)


def test_medwatch_detail_rendering():
    drug = {
        "id": 105,
        "display_name": "OZEMPIC",
        "active_ingredient": "SEMAGLUTIDE",
        "application_number": "MW-FAERS-209637",
        "source": "FDA_MEDWATCH",
        "sponsor": "NOVO NORDISK INC",
        "dosage_form": "Prefilled pen",
        "detail_url": MEDWATCH_PORTAL_URL,
    }
    changes = [
        {
            "section": "MedWatch Safety Communication",
            "change_type": "Counterfeit Alert",
            "source_date": "2024-01-10T00:00:00",
            "source_record_id": "MW-ALERT-001",
            "source_url": "https://www.fda.gov/safety/recalls",
            "original_text": "Baseline safety info",
            "updated_text": "Counterfeit Ozempic pens identified in US supply chain.",
            "fda_comment": "Official FDA MedWatch Advisory.",
            "source": "FDA_MEDWATCH",
        }
    ]

    html = render_drug_detail_html(drug, changes)
    assert "FDA MedWatch Safety Information &amp; Adverse Events" in html or "FDA MedWatch" in html
    assert "MW-FAERS-209637" in html
    assert "NOVO NORDISK INC" in html
    assert "Counterfeit Ozempic pens identified" in html
    assert "Report a Problem (Form 3500)" in html
    assert "FDA MedWatch Program Hub" in html
