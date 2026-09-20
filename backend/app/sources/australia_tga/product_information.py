"""
Product Information (PI) document and PDF discovery for Australia TGA.
Collects PDF URLs, document metadata, amendment dates, and versions.
"""
from __future__ import annotations

from datetime import datetime
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.sources.australia_tga.config import (
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    HUMAN_VERIFICATION_REQUIRED,
    SECURITY_CHALLENGE_SIGNATURES,
    TGA_BASE_URL,
)
from app.sources.australia_tga.date_parser import TGADateParser
from app.sources.australia_tga.models import TGAPIDocument, TGAProductPage

logger = logging.getLogger(__name__)


class TGAProductInformationDiscoverer:
    """Discovers Product Information PDF documents and extracts document-level version metadata."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.timeout = timeout
        self.headers = headers or DEFAULT_HEADERS

    async def discover_pi_documents(self, product_page: TGAProductPage) -> List[TGAPIDocument]:
        """
        Discovers all available Product Information PDF documents from product page and linked PI resources.
        Returns a list of TGAPIDocument candidates with parsed date/version metadata.
        """
        discovered_docs: List[TGAPIDocument] = []
        seen_pdf_urls = set()

        # 1. Inspect the product page HTML content first if provided (captures surrounding table/row context)
        if product_page.html_content:
            page_docs = self._extract_docs_from_html(
                product_page.html_content,
                page_url=product_page.source_url,
            )
            for p_doc in page_docs:
                if p_doc.pdf_url not in seen_pdf_urls:
                    seen_pdf_urls.add(p_doc.pdf_url)
                    discovered_docs.append(p_doc)

        # 2. Inspect any remaining direct or intermediate links
        for link in product_page.pi_links:
            clean_link = link.split("#")[0].strip()
            if not clean_link or clean_link in seen_pdf_urls:
                continue

            if self._is_direct_pdf_url(clean_link):
                seen_pdf_urls.add(clean_link)
                doc = self._build_document_from_link(clean_link, source_url=product_page.source_url)
                discovered_docs.append(doc)
            else:
                # Fetch intermediate page to extract PDF link and version metadata
                sub_docs = await self._scrape_pi_subpage(clean_link, product_page)
                for s_doc in sub_docs:
                    s_clean = s_doc.pdf_url.split("#")[0].strip()
                    if s_clean not in seen_pdf_urls:
                        seen_pdf_urls.add(s_clean)
                        s_doc.pdf_url = s_clean
                        discovered_docs.append(s_doc)

        return discovered_docs

    def _is_direct_pdf_url(self, url: str) -> bool:
        """Determines if URL points directly to a PDF document or PDF service."""
        lower = url.lower()
        return (
            lower.endswith(".pdf")
            or ".pdf?" in lower
            or "/pdf?" in lower
            or "format=pdf" in lower
            or "picmirepository.nsf/pdf" in lower
            or "viewportaldoc" in lower
        )

    def _build_document_from_link(
        self,
        pdf_url: str,
        source_url: Optional[str] = None,
        context_text: str = "",
    ) -> TGAPIDocument:
        """Builds a TGAPIDocument candidate, inferring dates and versions from context or URL."""
        rev_date = TGADateParser.extract_amendment_date(context_text)
        doc_date = TGADateParser.parse_date(context_text) or rev_date
        v_str, v_num = TGADateParser.parse_version(context_text)

        # If not found in text, look in URL
        if not doc_date:
            m_date = re.search(r"(\d{4}[-_]\d{2}[-_]\d{2})", pdf_url)
            if m_date:
                doc_date = TGADateParser.parse_date(m_date.group(1).replace("_", "-"))

        if not v_str:
            m_v = re.search(r"[_\-v]([0-9]+(?:\.[0-9]+)*)(?:\.pdf|$)", pdf_url, re.I)
            if m_v:
                v_str, v_num = TGADateParser.parse_version(m_v.group(1))

        return TGAPIDocument(
            title="Product Information",
            pdf_url=pdf_url,
            source_url=source_url,
            document_date=doc_date,
            revision_date=rev_date or doc_date,
            version_str=v_str,
            version_number=v_num,
            retrieved_date=datetime.utcnow(),
            raw_metadata={"context_text": context_text},
        )

    async def _scrape_pi_subpage(
        self,
        subpage_url: str,
        product_page: TGAProductPage,
    ) -> List[TGAPIDocument]:
        """Fetches an intermediate Product Information subpage and extracts PDF documents."""
        docs: List[TGAPIDocument] = []
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
                http2=False,
            ) as client:
                resp = await client.get(subpage_url)
                if resp.status_code == 200 and resp.text:
                    docs.extend(self._extract_docs_from_html(resp.text, page_url=subpage_url))
        except Exception as exc:
            logger.warning("Error fetching PI subpage (%s): %s", subpage_url, exc)
        return docs

    def _extract_docs_from_html(self, html: str, page_url: str) -> List[TGAPIDocument]:
        """Scrapes all PI PDF links, versions, and revision dates from an HTML page."""
        soup = BeautifulSoup(html, "html.parser")
        docs: List[TGAPIDocument] = []

        # Find all link tags
        for a in soup.find_all("a", href=True):
            href = a.get("href") or ""
            link_text = a.get_text(strip=True)
            abs_url = urljoin(page_url or TGA_BASE_URL, href).split("#")[0].strip()

            if not self._is_direct_pdf_url(abs_url):
                continue

            # Skip Consumer Medicine Information (CMI) PDFs (while allowing picmirepository PI documents)
            lower_url = abs_url.lower()
            lower_text = link_text.lower()
            is_cmi_doc = (
                "-cmi-" in lower_url
                or "_cmi" in lower_url
                or "/cmi/" in lower_url
                or lower_url.endswith("cmi.pdf")
                or "consumer medicine" in lower_text
                or "cmi" in lower_text.split()
            )
            if is_cmi_doc and "-pi-" not in lower_url and "product information" not in lower_text:
                continue

            # Gather surrounding context text (parent row or paragraph)
            parent = a.find_parent(["tr", "li", "div", "p"])
            context = parent.get_text(" ", strip=True) if parent else link_text

            doc = self._build_document_from_link(
                pdf_url=abs_url,
                source_url=page_url,
                context_text=context,
            )
            docs.append(doc)

        return docs
