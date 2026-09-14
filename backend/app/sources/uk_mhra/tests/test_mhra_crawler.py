"""
Tests for UK MHRA Drug Safety Update Crawler, Adapter, Database Persistence, and UI Rendering.
"""
import pytest

from app.models.drug import Drug
from app.services.database_service import DatabaseService
from app.sources.uk_mhra.mhra_crawler import (
    UKMHRACrawler,
    MHRA_PORTAL_URL,
    MHRA_YELLOW_CARD_URL,
    mhra_crawler,
)
from app.sources.uk_mhra.adapter import UKMHRAAdapter, mhra_adapter
from app.ui import render_drug_detail_html, _render_uk_mhra_drug_detail


@pytest.mark.asyncio
async def test_mhra_crawler_ozempic():
    crawler = UKMHRACrawler(live_fetch=False)
    candidates = await crawler.search_medicine("Ozempic")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "OZEMPIC"
    assert c["active_ingredient"] == "SEMAGLUTIDE"
    assert "PLGB" in c["application_number"]
    assert "NOVO NORDISK" in c["sponsor"]
    assert c["detail_url"] == MHRA_PORTAL_URL
    assert len(c["safety_changes"]) >= 3

    types = [sc["change_type"] for sc in c["safety_changes"]]
    assert any("Falsified" in t for t in types)
    assert any("NAION" in t for t in types)


@pytest.mark.asyncio
async def test_mhra_crawler_tecfidera():
    crawler = UKMHRACrawler(live_fetch=False)
    candidates = await crawler.search_medicine("tecfidera")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "TECFIDERA"
    assert c["active_ingredient"] == "DIMETHYL FUMARATE"
    assert "BIOGEN" in c["sponsor"]
    assert any("PML" in sc["change_type"] or "PML" in sc["updated_text"] for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_mhra_crawler_aspirin():
    crawler = UKMHRACrawler(live_fetch=False)
    candidates = await crawler.search_medicine("aspirin")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "ASPIRIN"
    assert any("Primary Prevention" in sc["change_type"] or "primary prevention" in sc["updated_text"].lower() for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_mhra_crawler_warfarin():
    crawler = UKMHRACrawler(live_fetch=False)
    candidates = await crawler.search_medicine("warfarin")
    assert len(candidates) >= 1
    c = candidates[0]
    assert "WARFARIN" in c["display_name"]
    assert any("tramadol" in sc["updated_text"].lower() for sc in c["safety_changes"])
    assert any("calciphylaxis" in sc["updated_text"].lower() for sc in c["safety_changes"])


@pytest.mark.asyncio
async def test_mhra_crawler_generic_fallback():
    crawler = UKMHRACrawler(live_fetch=False)
    candidates = await crawler.search_medicine("ZzzNovelMed999")
    assert len(candidates) >= 1
    c = candidates[0]
    assert c["display_name"] == "ZZZNOVELMED999"
    assert c["source"] == "UK_MHRA"
    assert len(c["safety_changes"]) >= 1
    assert "Yellow Card" in c["safety_changes"][0]["updated_text"]


@pytest.mark.asyncio
async def test_mhra_adapter_search_and_save(db):
    crawler = UKMHRACrawler(live_fetch=False)
    adapter = UKMHRAAdapter(crawler=crawler)

    drugs = await adapter.search("ozempic", db=db, force_refresh=True)
    assert len(drugs) >= 1
    d = drugs[0]
    assert d.source == "UK_MHRA"
    assert d.display_name == "OZEMPIC"
    assert "PLGB" in d.application_number

    changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
    assert len(changes) >= 3
    assert all(c.source == "UK_MHRA" for c in changes)

    # Search again with force_refresh=False to verify caching
    cached_drugs = await adapter.search("ozempic", db=db, force_refresh=False)
    assert len(cached_drugs) == 1
    assert cached_drugs[0].id == d.id


@pytest.mark.asyncio
async def test_penta_authority_coexistence(db):
    """
    Verify that an identical medicine name (e.g. 'ozempic') can exist independently
    across all 5 regulatory programs: FDA SrLC, Health Canada, Australia TGA, FDA MedWatch, and UK MHRA.
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

    # 5. UK MHRA
    mhra_drug, _ = DatabaseService.insert_or_update_drug(
        db,
        {
            "display_name": "OZEMPIC",
            "normalized_name": "ozempic",
            "active_ingredient": "SEMAGLUTIDE",
            "application_number": "PLGB 16950/0333",
            "source": "UK_MHRA",
        },
    )

    db.commit()

    # Verify all 5 drug IDs are distinct
    assert len({fda_drug.id, hc_drug.id, tga_drug.id, mw_drug.id, mhra_drug.id}) == 5

    # Verify source filtering in search_drugs
    mhra_results = DatabaseService.search_drugs(db, "ozempic", source="UK_MHRA")
    assert len(mhra_results) == 1
    assert mhra_results[0].source == "UK_MHRA"
    assert mhra_results[0].application_number == "PLGB 16950/0333"

    mw_results = DatabaseService.search_drugs(db, "ozempic", source="FDA_MEDWATCH")
    assert len(mw_results) == 1
    assert mw_results[0].source == "FDA_MEDWATCH"

    tga_results = DatabaseService.search_drugs(db, "ozempic", source="AUSTRALIA_TGA")
    assert len(tga_results) == 1
    assert tga_results[0].source == "AUSTRALIA_TGA"

    fda_results = DatabaseService.search_drugs(db, "ozempic", source="FDA_SRLC")
    assert len(fda_results) == 1
    assert fda_results[0].source == "FDA_SRLC"

    hc_results = DatabaseService.search_drugs(db, "ozempic", source="HEALTH_CANADA")
    assert len(hc_results) == 1
    assert hc_results[0].source == "HEALTH_CANADA"

    # Verify ALL source search returns all 5 records
    all_results = DatabaseService.search_drugs(db, "ozempic", source="ALL")
    assert len(all_results) >= 5
    sources = {d.source for d in all_results}
    assert {"FDA_SRLC", "HEALTH_CANADA", "AUSTRALIA_TGA", "FDA_MEDWATCH", "UK_MHRA"}.issubset(sources)


def test_mhra_detail_rendering():
    drug = {
        "id": 201,
        "display_name": "OZEMPIC",
        "active_ingredient": "SEMAGLUTIDE",
        "application_number": "PLGB 16950/0333",
        "source": "UK_MHRA",
        "sponsor": "NOVO NORDISK LIMITED (UK)",
        "dosage_form": "Pre-filled pen",
        "detail_url": MHRA_PORTAL_URL,
    }
    changes = [
        {
            "section": "MHRA Drug Safety Update",
            "change_type": "Falsified Product Vigilance",
            "source_date": "2023-10-26T00:00:00",
            "source_record_id": "MHRA-DSU-001",
            "source_url": "https://www.gov.uk/drug-safety-update/sample",
            "original_text": "Standard prescribing info",
            "updated_text": "Falsified Ozempic pens identified in UK supply chain. Report suspected units via Yellow Card.",
            "fda_comment": "Official MHRA & CHM guidance.",
            "source": "UK_MHRA",
        }
    ]

    html = render_drug_detail_html(drug, changes)
    assert "UK MHRA Drug Safety Update" in html
    assert "PLGB 16950/0333" in html
    assert "NOVO NORDISK LIMITED" in html
    assert "Falsified Ozempic pens identified" in html
    assert "Report ADR (Yellow Card)" in html
    assert "GOV.UK Drug Safety Update" in html
