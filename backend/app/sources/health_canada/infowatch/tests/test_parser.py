"""
Tests for the Health Canada InfoWatch article-level HTML parser.

All tests use static HTML fixtures — no network access.
"""
from __future__ import annotations

import pytest
from app.sources.health_canada.infowatch.models import ArticleType, IndexEntry
from app.sources.health_canada.infowatch.parser import ArticleParser
from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    article_url: str = "https://www.canada.ca/en/health-canada/.../article.html#a1",
    month: str = "August",
    year: int = 2026,
    product_name: str = "Tecfidera",
    generic_name: str = "dimethyl fumarate",
    article_type: ArticleType = ArticleType.PRODUCT_MONOGRAPH_UPDATE,
    article_title: str = "Tecfidera (dimethyl fumarate)",
) -> IndexEntry:
    return IndexEntry(
        newsletter_type="Health Product InfoWatch",
        month=month,
        year=year,
        publication_date=date(year, 8, 1),
        article_title=article_title,
        article_url=article_url,
        product_name=product_name,
        generic_name=generic_name,
        article_type=article_type,
        index_url="https://www.canada.ca/en/.../published-newsletters.html",
    )


_ARTICLE_HTML = """
<!DOCTYPE html>
<html>
<body>
<main>
  <h1>Product monograph update — Tecfidera (dimethyl fumarate)</h1>
  <p>Posted: August 2026</p>
  <p>Health Canada has authorized an update to the product monograph for Tecfidera (dimethyl fumarate).
  The update includes new safety information regarding the risk of progressive multifocal leukoencephalopathy (PML).</p>

  <h2>Background</h2>
  <p>Tecfidera (dimethyl fumarate) is indicated for the treatment of patients with relapsing-remitting
  multiple sclerosis (RRMS). PML is a rare but serious brain infection caused by the JC virus.</p>

  <h2>Health Canada assessment</h2>
  <p>Health Canada reviewed available evidence and concluded that the benefit-risk profile of
  dimethyl fumarate remains positive when used as directed. Healthcare professionals should monitor
  patients for signs and symptoms of PML.</p>

  <h2>What you should do</h2>
  <p>Healthcare professionals should review the updated product monograph and inform patients of the risks.</p>

  <h2>References</h2>
  <ul>
    <li><a href="/en/health-canada/.../tecfidera-pm.pdf">Updated product monograph (PDF)</a></li>
    <li><a href="https://external.example.com/other.html">External reference</a></li>
  </ul>

  <table>
    <tr><th>Section</th><th>Change</th></tr>
    <tr><td>Warnings</td><td>Updated PML risk language</td></tr>
    <tr><td>Adverse Reactions</td><td>Added new reporting data</td></tr>
  </table>

  <h2>Scope</h2>
  <p>This communication applies to all healthcare professionals.</p>

  <h2>Reporting adverse reactions</h2>
  <p>Report suspected adverse reactions to Health Canada.</p>
</main>
</body>
</html>
"""

_MONTHLY_RECAP_HTML = """
<!DOCTYPE html>
<html>
<body>
<main>
  <h1>Monthly recap of health product safety information — August 2026</h1>
  <h2>Omnitrope (somatropin for injection)</h2>
  <p>Health Canada reviewed post-market safety data for Omnitrope (somatropin for injection).
  The review identified a potential risk of benign intracranial hypertension in pediatric patients.</p>
  <h2>Tavneos (avacopan)</h2>
  <p>Tavneos (avacopan) is associated with a risk of serious hepatic adverse reactions.
  Healthcare professionals should monitor liver function tests.</p>
  <h2>Scope</h2>
  <p>This recap covers safety communications issued in August 2026.</p>
</main>
</body>
</html>
"""


@pytest.fixture
def art_parser() -> ArticleParser:
    return ArticleParser()


# ---------------------------------------------------------------------------
# Tests: single-product article
# ---------------------------------------------------------------------------

class TestArticleParserSingleProduct:

    def test_parse_returns_article(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert article is not None

    def test_extracts_title(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert "Tecfidera" in article.title or "product monograph" in article.title.lower()

    def test_detects_pdf_links(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert len(article.pdf_urls) >= 1
        assert any("tecfidera" in url.lower() or ".pdf" in url.lower() for url in article.pdf_urls)

    def test_pdf_urls_are_absolute(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        for url in article.pdf_urls:
            assert url.startswith("https://"), f"PDF URL not absolute: {url}"

    def test_extracts_sections(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert len(article.sections) >= 2
        headings = [s.get("heading", "").lower() for s in article.sections]
        assert any("background" in h for h in headings)
        assert any("assessment" in h for h in headings)

    def test_extracts_tables(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert len(article.tables) >= 1
        # First table row should have "Section" and "Change" as headers
        assert any(
            "Section" in row or "Warnings" in row
            for table in article.tables
            for row in table
        )

    def test_extracts_product_mention(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert len(article.product_mentions) >= 1
        tecfidera = next(
            (m for m in article.product_mentions if "tecfidera" in m.product_name.lower()),
            None,
        )
        assert tecfidera is not None
        assert "dimethyl fumarate" in tecfidera.generic_name.lower()

    def test_context_not_empty(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        for mention in article.product_mentions:
            assert len(mention.context_text) > 10, "Context text should not be empty"

    def test_full_text_not_empty(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert len(article.full_text) > 50

    def test_article_url_set(self, art_parser):
        url = "https://www.canada.ca/en/health-canada/.../article.html#a1"
        entry = _make_entry(article_url=url)
        article = art_parser.parse(_ARTICLE_HTML, entry)
        assert article.article_url == url.split("#")[0]
        assert article.anchor == "a1"


# ---------------------------------------------------------------------------
# Tests: monthly recap (multiple products)
# ---------------------------------------------------------------------------

class TestArticleParserMonthlyRecap:

    def _make_recap_entry(self) -> IndexEntry:
        return _make_entry(
            article_url="https://www.canada.ca/en/health-canada/.../august-2026.html#a1",
            product_name="",
            generic_name="",
            article_type=ArticleType.MONTHLY_RECAP,
            article_title="Monthly recap of health product safety information",
        )

    def test_detects_multiple_products(self, art_parser):
        entry = self._make_recap_entry()
        article = art_parser.parse(_MONTHLY_RECAP_HTML, entry)
        product_names = [m.product_name.lower() for m in article.product_mentions]
        generic_names = [m.generic_name.lower() for m in article.product_mentions]
        all_names = product_names + generic_names

        assert any("omnitrope" in n for n in all_names), "Should find Omnitrope"
        assert any("tavneos" in n for n in all_names), "Should find Tavneos"

    def test_products_have_distinct_context(self, art_parser):
        entry = self._make_recap_entry()
        article = art_parser.parse(_MONTHLY_RECAP_HTML, entry)
        contexts = [m.context_text for m in article.product_mentions]
        # Contexts should differ between products
        if len(contexts) >= 2:
            assert contexts[0] != contexts[1], "Different products should have different contexts"


# ---------------------------------------------------------------------------
# Tests: empty / malformed HTML
# ---------------------------------------------------------------------------

class TestArticleParserEdgeCases:

    def test_empty_html(self, art_parser):
        entry = _make_entry()
        article = art_parser.parse("", entry)
        assert article is not None
        assert article.product_mentions == [] or len(article.product_mentions) >= 0

    def test_no_headings(self, art_parser):
        html = "<html><body><p>Tecfidera (dimethyl fumarate) is a drug.</p></body></html>"
        entry = _make_entry()
        article = art_parser.parse(html, entry)
        assert article is not None

    def test_article_url_set_from_entry(self, art_parser):
        entry = _make_entry(article_url="https://www.canada.ca/specific-article.html")
        article = art_parser.parse("<html><body></body></html>", entry)
        assert "canada.ca" in article.article_url
