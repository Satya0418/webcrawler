"""
Integration tests for the Health Canada InfoWatch adapter.

Tests medicine matching, DB persistence, and change detection.
Uses in-memory SQLite (same as existing tests in conftest.py).
Does NOT make real network requests.
"""
from __future__ import annotations

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.sources.health_canada.infowatch.adapter import (
    HealthCanadaInfowatchAdapter,
    _medicine_matches,
    SOURCE_ID,
)
from app.sources.health_canada.infowatch.models import (
    ArticleType,
    HealthCanadaArticle,
    IndexEntry,
    ProductMention,
)
from app.services.normalization import NormalizationService


# ---------------------------------------------------------------------------
# Medicine matcher tests (no DB)
# ---------------------------------------------------------------------------

class TestMedicineMatcher:

    def _entry(self, product="", generic="", title="") -> IndexEntry:
        return IndexEntry(
            newsletter_type="Health Product InfoWatch",
            month="August", year=2026,
            product_name=product,
            generic_name=generic,
            article_title=title or product,
            article_url="https://www.canada.ca/test.html",
        )

    def test_exact_brand_match(self):
        e = self._entry(product="Tecfidera", generic="dimethyl fumarate")
        assert _medicine_matches("tecfidera", e)

    def test_exact_generic_match(self):
        e = self._entry(product="Tecfidera", generic="dimethyl fumarate")
        assert _medicine_matches("dimethyl fumarate", e)

    def test_partial_generic_match(self):
        e = self._entry(product="Tecfidera", generic="dimethyl fumarate")
        assert _medicine_matches("dimethyl", e)

    def test_case_insensitive(self):
        e = self._entry(product="Omnitrope", generic="somatropin for injection")
        assert _medicine_matches("OMNITROPE", e)
        assert _medicine_matches("Somatropin", e)

    def test_title_match(self):
        e = self._entry(
            product="",
            generic="",
            title="Dimethyl fumarate-containing products",
        )
        assert _medicine_matches("dimethyl fumarate", e)

    def test_no_match(self):
        e = self._entry(product="Humira", generic="adalimumab")
        assert not _medicine_matches("semaglutide", e)

    def test_empty_query_matches_all(self):
        e = self._entry(product="Anything", generic="anything")
        assert _medicine_matches("", e)

    def test_no_false_positive_short_match(self):
        # "mat" should NOT match "semaglutide" (length < 4)
        e = self._entry(product="Wegovy", generic="semaglutide")
        # Query "ma" (2 chars) is below minimum word length
        assert not _medicine_matches("ma", e)


# ---------------------------------------------------------------------------
# Adapter DB integration tests
# ---------------------------------------------------------------------------

class TestAdapterDBIntegration:
    """
    Tests that the adapter correctly persists data to the DB.
    Uses the existing in-memory test DB from conftest.py.
    """

    @pytest.fixture
    def hc_adapter(self):
        return HealthCanadaInfowatchAdapter()

    def _make_article(self) -> HealthCanadaArticle:
        return HealthCanadaArticle(
            article_url="https://www.canada.ca/en/health-canada/test-article.html",
            newsletter_month="August",
            newsletter_year=2026,
            newsletter_type="Health Product InfoWatch",
            article_type=ArticleType.PRODUCT_MONOGRAPH_UPDATE,
            publication_date=date(2026, 8, 1),
            full_text="Tecfidera (dimethyl fumarate) product monograph update.",
            product_mentions=[
                ProductMention(
                    product_name="Tecfidera",
                    generic_name="dimethyl fumarate",
                    normalized_product="tecfidera",
                    normalized_generic="dimethyl fumarate",
                    section_heading="Product monograph update",
                    context_text="Health Canada has updated the Tecfidera product monograph.",
                    article_type=ArticleType.PRODUCT_MONOGRAPH_UPDATE,
                )
            ],
        )

    def test_save_mention_creates_drug(self, hc_adapter, db):
        article = self._make_article()
        mention = article.product_mentions[0]

        added, changed = hc_adapter._save_mention(
            db=db, article=article, mention=mention, pdf_result=None
        )
        db.commit()

        from app.services.database_service import DatabaseService
        drugs = DatabaseService.search_drugs(db, "tecfidera")
        assert len(drugs) >= 1
        assert any(d.display_name == "Tecfidera" for d in drugs)

    def test_save_mention_creates_safety_change(self, hc_adapter, db):
        article = self._make_article()
        mention = article.product_mentions[0]

        hc_adapter._save_mention(db=db, article=article, mention=mention, pdf_result=None)
        db.commit()

        from app.services.database_service import DatabaseService
        drugs = DatabaseService.search_drugs(db, "tecfidera")
        assert len(drugs) >= 1
        drug = drugs[0]
        changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        assert len(changes) >= 1
        assert changes[0].source == SOURCE_ID

    def test_save_mention_change_detection_unchanged(self, hc_adapter, db):
        """Saving the same data twice should not create a new version."""
        article = self._make_article()
        mention = article.product_mentions[0]

        hc_adapter._save_mention(db=db, article=article, mention=mention, pdf_result=None)
        db.commit()

        from app.services.database_service import DatabaseService
        drugs = DatabaseService.search_drugs(db, "tecfidera")
        drug = drugs[0]
        changes_before = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        versions_before = DatabaseService.get_versions_by_change_id(db, changes_before[0].id)

        # Save again (same content → should detect as unchanged)
        hc_adapter._save_mention(db=db, article=article, mention=mention, pdf_result=None)
        db.commit()

        versions_after = DatabaseService.get_versions_by_change_id(db, changes_before[0].id)
        assert len(versions_after) == len(versions_before), (
            "Identical content should not create a new version"
        )

    def test_save_mention_change_detection_changed(self, hc_adapter, db):
        """Saving different content for the same article should create a new version."""
        article = self._make_article()
        mention = article.product_mentions[0]

        hc_adapter._save_mention(db=db, article=article, mention=mention, pdf_result=None)
        db.commit()

        from app.services.database_service import DatabaseService
        drugs = DatabaseService.search_drugs(db, "tecfidera")
        drug = drugs[0]
        changes_before = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        versions_before = DatabaseService.get_versions_by_change_id(db, changes_before[0].id)

        # Mutate context text → different hash
        mention2 = ProductMention(
            product_name=mention.product_name,
            generic_name=mention.generic_name,
            normalized_product=mention.normalized_product,
            normalized_generic=mention.normalized_generic,
            section_heading=mention.section_heading,
            context_text="UPDATED: New safety information about PML risk added.",
            article_type=mention.article_type,
        )
        hc_adapter._save_mention(db=db, article=article, mention=mention2, pdf_result=None)
        db.commit()

        versions_after = DatabaseService.get_versions_by_change_id(db, changes_before[0].id)
        assert len(versions_after) > len(versions_before), (
            "Changed content should create a new archived version"
        )

    def test_source_traceability(self, hc_adapter, db):
        """Safety changes must be traceable to Health Canada."""
        article = self._make_article()
        mention = article.product_mentions[0]
        hc_adapter._save_mention(db=db, article=article, mention=mention, pdf_result=None)
        db.commit()

        from app.services.database_service import DatabaseService
        drugs = DatabaseService.search_drugs(db, "tecfidera")
        drug = drugs[0]
        changes = DatabaseService.get_safety_changes_by_drug_id(db, drug.id)
        assert changes[0].source == "HEALTH_CANADA_INFOWATCH"
        assert changes[0].source_url  # must have a URL


# ---------------------------------------------------------------------------
# Medicine normalization tests (HC-specific)
# ---------------------------------------------------------------------------

class TestHCNormalization:

    def test_normalize_brand(self):
        assert NormalizationService.normalize_drug_name("Tecfidera") == "tecfidera"

    def test_normalize_generic_with_spaces(self):
        n = NormalizationService.normalize_drug_name("dimethyl fumarate")
        assert n == "dimethyl fumarate"

    def test_normalize_complex_generic(self):
        n = NormalizationService.normalize_drug_name("somatropin for injection")
        assert n == "somatropin for injection"
