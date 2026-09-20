"""
Unit tests for Australia TGA search engine (search.py).
"""
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.sources.australia_tga.config import HUMAN_VERIFICATION_REQUIRED
from app.sources.australia_tga.search import TGASearchEngine


class TestTGASearch:
    """Tests for TGASearchEngine."""

    @pytest.mark.asyncio
    async def test_search_empty_or_short_query(self):
        engine = TGASearchEngine()
        assert await engine.search("") == []
        assert await engine.search("a") == []
        assert await engine.search("   ") == []

    def test_parse_search_results_mock_html(self):
        engine = TGASearchEngine()
        mock_html = """
        <html>
        <body>
            <main id="main-content">
                <article class="search-result">
                    <h3><a href="/resources/prescription-medicines-registrations/ocuflox-ofloxacin">OCUFLOX (ofloxacin) eye drops</a></h3>
                    <span class="date">12 June 2024</span>
                    <p class="snippet">Australian Register of Therapeutic Goods AUST R 47485 for OCUFLOX sterile ophthalmic solution.</p>
                </article>
                <article class="search-result">
                    <h3><a href="/resources/prescription-medicines-registrations/ozempic-semaglutide">OZEMPIC (semaglutide) solution for injection</a></h3>
                    <time class="published">15 February 2024</time>
                    <div class="description">Registration details for AUST R 308323 Semaglutide pre-filled pen.</div>
                </article>
            </main>
        </body>
        </html>
        """
        results = engine.parse_search_results(mock_html, query="Ofloxacin")
        assert len(results) == 2

        r1 = results[0]
        assert "OCUFLOX" in r1.title
        assert "ocuflox-ofloxacin" in r1.url
        assert r1.artg_number == "AUST R 47485"
        assert r1.active_ingredient == "OFLOXACIN"
        assert r1.source_date is not None
        assert r1.source_date.year == 2024
        assert r1.source_date.month == 6

        r2 = results[1]
        assert "OZEMPIC" in r2.title
        assert r2.artg_number == "AUST R 308323"
        assert r2.active_ingredient == "SEMAGLUTIDE"

    def test_is_security_challenge(self):
        engine = TGASearchEngine()
        assert engine.is_security_challenge(403, "Forbidden") is True
        assert engine.is_security_challenge(429, "Too Many Requests") is True
        assert engine.is_security_challenge(200, "<html>Just a moment... cf-challenge</html>") is True
        assert engine.is_security_challenge(200, "<html>Please verify you are human to continue.</html>") is True
        assert engine.is_security_challenge(200, "<html>Normal TGA Search Results Page</html>") is False

    @pytest.mark.asyncio
    async def test_search_anti_bot_detection(self):
        engine = TGASearchEngine()
        with patch.object(engine, "search_ebs", return_value=[]), \
             patch.object(engine, "fetch_search_html", return_value=HUMAN_VERIFICATION_REQUIRED):
            results = await engine.search("Ofloxacin")
            assert results == []

    @pytest.mark.asyncio
    async def test_fetch_search_html_timeout(self):
        engine = TGASearchEngine(timeout=0.01)
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
            html = await engine.fetch_search_html("Ofloxacin")
            assert html is None

    def test_parse_empty_html(self):
        engine = TGASearchEngine()
        assert engine.parse_search_results("") == []
        assert engine.parse_search_results("<html><body>No results</body></html>") == []
