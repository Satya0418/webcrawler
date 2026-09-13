"""
Tests for Health Canada InfoWatch index discovery.

Uses static HTML fixtures that mirror the real page structure.
No network access required.
"""
from __future__ import annotations

import pytest
from app.sources.health_canada.infowatch.discovery import IndexDiscovery
from app.sources.health_canada.infowatch.models import ArticleType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_INDEX_HTML = """
<!DOCTYPE html>
<html>
<body>
<main>
  <h2 id="a1">The Health Product InfoWatch</h2>

  <h3>August 2026</h3>
  <ul>
    <li><a href="/en/health-canada/.../august-2026.html#a1">Monthly recap of health product safety information</a>
      <ul>
        <li><a href="/en/health-canada/.../august-2026.html#a1.1">Ashwagandha for oral use</a></li>
        <li><a href="/en/health-canada/.../august-2026.html#a1.2">Omnitrope (somatropin for injection)</a></li>
        <li><a href="/en/health-canada/.../august-2026.html#a1.3">Tavneos (avacopan)</a></li>
      </ul>
    </li>
    <li><a href="/en/health-canada/.../august-2026.html#a2">New health product safety information</a>
      <ul>
        <li><a href="/en/health-canada/.../august-2026.html#a2.1">Product monograph update</a>
          <ul>
            <li><a href="/en/health-canada/.../august-2026.html#a2.2.1">Tecfidera (dimethyl fumarate)</a></li>
          </ul>
        </li>
        <li><a href="/en/health-canada/.../august-2026.html#a2.2">Notice of market authorization with conditions</a>
          <ul>
            <li><a href="/en/health-canada/.../august-2026.html#a2.2.2">Ojemda (tovorafenib): Authorization with conditions</a></li>
          </ul>
        </li>
      </ul>
    </li>
    <li><a href="/en/health-canada/.../august-2026.html#a3">Scope</a></li>
    <li><a href="/en/health-canada/.../august-2026.html#a4">Reporting adverse reactions</a></li>
    <li><a href="/en/health-canada/.../august-2026.html#a5">Helpful links</a></li>
    <li><a href="/en/health-canada/.../august-2026.html#a6">Contact us</a></li>
  </ul>

  <h3>January 2026</h3>
  <ul>
    <li><a href="/en/health-canada/.../january-2026.html#mo">Monthly recap of health product safety information</a>
      <ul>
        <li><a href="/en/health-canada/.../january-2026.html#di">Dimethyl fumarate-containing products</a></li>
        <li><a href="/en/health-canada/.../january-2026.html#ye">Yescarta (axicabtagene ciloleucel)</a></li>
      </ul>
    </li>
    <li><a href="/en/health-canada/.../january-2026.html#ne">New health product safety information</a>
      <ul>
        <li><a href="/en/health-canada/.../january-2026.html#sa">Safety briefs</a>
          <ul>
            <li><a href="/en/health-canada/.../january-2026.html#th">The use of some natural health products and the potential risk of hepatotoxicity</a></li>
          </ul>
        </li>
        <li><a href="/en/health-canada/.../january-2026.html#not">Notice of market authorization with conditions</a>
          <ul>
            <li><a href="/en/health-canada/.../january-2026.html#we">Wegovy (semaglutide): Authorization with conditions</a></li>
          </ul>
        </li>
      </ul>
    </li>
    <li><a href="/en/health-canada/.../january-2026.html#sc">Scope</a></li>
  </ul>

  <h2 id="a2">Canadian Adverse Reaction Newsletters</h2>

  <h3>October 2011</h3>
  <ul>
    <li><a href="/en/health-canada/.../carn-2011.html#a1">Clopidogrel (Plavix) and drug interactions</a></li>
  </ul>
</main>
</body>
</html>
"""


@pytest.fixture
def disc() -> IndexDiscovery:
    return IndexDiscovery()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIndexDiscovery:

    def test_parse_returns_list(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_skips_structural_entries(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        titles = [e.article_title.lower() for e in entries]
        assert "scope" not in titles
        assert "reporting adverse reactions" not in titles
        assert "helpful links" not in titles
        assert "contact us" not in titles

    def test_detects_month_year(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        months = {e.month for e in entries}
        years = {e.year for e in entries}
        assert "August" in months
        assert "January" in months
        assert 2026 in years

    def test_extracts_product_names(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        by_title = {e.article_title: e for e in entries}

        # "Omnitrope (somatropin for injection)"
        omni = by_title.get("Omnitrope (somatropin for injection)")
        assert omni is not None
        assert omni.product_name == "Omnitrope"
        assert "somatropin" in omni.generic_name.lower()

        # "Tecfidera (dimethyl fumarate)"
        tec = by_title.get("Tecfidera (dimethyl fumarate)")
        assert tec is not None
        assert tec.product_name == "Tecfidera"
        assert "dimethyl fumarate" in tec.generic_name.lower()

    def test_classifies_product_monograph_update(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        tecfidera = next(
            (e for e in entries if "tecfidera" in e.article_title.lower()), None
        )
        assert tecfidera is not None
        assert tecfidera.article_type == ArticleType.PRODUCT_MONOGRAPH_UPDATE

    def test_classifies_market_authorization(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        wegovy = next(
            (e for e in entries if "wegovy" in e.article_title.lower()), None
        )
        assert wegovy is not None
        assert wegovy.article_type == ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS

    def test_classifies_monthly_recap_products(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        tavneos = next(
            (e for e in entries if "tavneos" in e.article_title.lower()), None
        )
        assert tavneos is not None
        assert tavneos.article_type == ArticleType.MONTHLY_RECAP

    def test_classifies_safety_brief(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        hepato = next(
            (e for e in entries if "hepatotoxicity" in e.article_title.lower()), None
        )
        assert hepato is not None
        assert hepato.article_type == ArticleType.SAFETY_BRIEF

    def test_newsletter_type_detection(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        carn = next(
            (e for e in entries if "clopidogrel" in e.article_title.lower()), None
        )
        assert carn is not None
        assert "adverse reaction" in carn.newsletter_type.lower()

    def test_urls_are_absolute(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        for e in entries:
            assert e.article_url.startswith("https://"), (
                f"Expected absolute URL, got: {e.article_url}"
            )

    def test_publication_date_set(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        aug_entries = [e for e in entries if e.month == "August" and e.year == 2026]
        assert len(aug_entries) > 0
        for e in aug_entries:
            assert e.publication_date is not None
            assert e.publication_date.year == 2026
            assert e.publication_date.month == 8

    def test_empty_html(self, disc):
        entries = disc.parse_index("<html><body></body></html>")
        assert entries == []

    def test_no_duplicate_urls_per_product(self, disc):
        entries = disc.parse_index(_MINIMAL_INDEX_HTML)
        urls = [e.article_url for e in entries]
        # URLs with different anchors are allowed, but same URL+anchor should not repeat
        assert len(urls) == len(set(urls)), "Duplicate article URLs found"
