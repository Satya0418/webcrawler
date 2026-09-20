"""
Unit tests for Product Page inspection and Product Information discovery (product_page.py & product_information.py).
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.sources.australia_tga.models import TGASearchResult, TGAProductPage
from app.sources.australia_tga.product_page import TGAProductPageHandler
from app.sources.australia_tga.product_information import TGAProductInformationDiscoverer


class TestProductPageAndDiscovery:
    """Tests for TGAProductPageHandler and TGAProductInformationDiscoverer."""

    def test_is_relevant_result(self):
        handler = TGAProductPageHandler()

        res_oflox = TGASearchResult(
            title="OCUFLOX ofloxacin 3mg/mL ophthalmic solution",
            url="https://www.tga.gov.au/resources/prescription-medicines-registrations/ocuflox-ofloxacin",
            snippet="AUST R 47485 for OCUFLOX sterile eye drops.",
            artg_number="AUST R 47485",
            active_ingredient="OFLOXACIN",
        )
        assert handler.is_relevant_result(res_oflox, "Ofloxacin") is True
        assert handler.is_relevant_result(res_oflox, "ocuflox") is True
        assert handler.is_relevant_result(res_oflox, "47485") is True
        assert handler.is_relevant_result(res_oflox, "Paracetamol") is False

    def test_parse_product_page_html(self):
        handler = TGAProductPageHandler()
        mock_html = """
        <html>
        <head><title>OCUFLOX | Therapeutic Goods Administration (TGA)</title></head>
        <body>
            <h1>OCUFLOX</h1>
            <div class="field--name-field-active-ingredients">Active ingredient: OFLOXACIN 3mg/mL</div>
            <div class="field--name-field-sponsor">Sponsor: ALLERGAN AUSTRALIA PTY LTD</div>
            <div class="field--name-field-artg-id">AUST R 47485</div>
            <div class="field--name-field-dosage-form">Dosage form: Eye drops solution</div>
            <div class="links">
                <a href="/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3">Product Information (PI)</a>
                <a href="/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-CMI-02947-3">Consumer Medicine Information (CMI)</a>
            </div>
        </body>
        </html>
        """
        page = handler.parse_product_page(
            mock_html,
            url="https://www.tga.gov.au/resources/prescription-medicines-registrations/ocuflox-ofloxacin",
            query="Ofloxacin",
        )
        assert page.product_name == "OCUFLOX"
        assert page.active_ingredient == "OFLOXACIN 3MG/ML"
        assert page.sponsor == "ALLERGAN AUSTRALIA PTY LTD"
        assert page.application_number == "AUST R 47485"
        assert len(page.pi_links) >= 1
        assert "picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3" in page.pi_links[0]
        assert len(page.cmi_links) >= 1
        assert "picmirepository.nsf/pdf?OpenAgent&id=CP-2010-CMI-02947-3" in page.cmi_links[0]

    @pytest.mark.asyncio
    async def test_discover_pi_documents_direct_pdf(self):
        discoverer = TGAProductInformationDiscoverer()
        product_page = TGAProductPage(
            product_name="OCUFLOX",
            active_ingredient="OFLOXACIN",
            source_url="https://www.tga.gov.au/ocuflox",
            pi_links=[
                "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3",
            ],
            html_content="""
            <tr>
                <td>Product Information (PI)</td>
                <td><a href="https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3">Download PDF</a></td>
                <td>Date of most recent amendment: 12 June 2024 (Version 4.0)</td>
            </tr>
            """,
        )

        docs = await discoverer.discover_pi_documents(product_page)
        assert len(docs) >= 1
        d = docs[0]
        assert d.pdf_url == "https://www.ebs.tga.gov.au/ebs/picmi/picmirepository.nsf/pdf?OpenAgent&id=CP-2010-PI-02947-3"
        assert d.document_date is not None
        assert d.document_date.year == 2024
        assert d.document_date.month == 6
        assert d.document_date.day == 12
        assert d.version_number == 4.0
