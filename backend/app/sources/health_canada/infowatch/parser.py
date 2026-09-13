"""
Article-level HTML parser for Health Canada InfoWatch article pages.

Responsibilities:
  - Extract title, publication date, headings, paragraphs, tables
  - Identify medicines/products mentioned in each section
  - Detect PDF links for routing to the existing PDF extractor
  - Preserve source traceability (section heading, article URL)
  - Return a HealthCanadaArticle with one ProductMention per distinct product

Does NOT fetch pages (that is crawler.py).
Does NOT persist to the database (that is adapter.py).
Does NOT call the PDF extractor (that is adapter.py).
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from app.sources.health_canada.infowatch.models import (
    ArticleType,
    HealthCanadaArticle,
    IndexEntry,
    ProductMention,
)

logger = logging.getLogger(__name__)

HC_BASE_URL = "https://www.canada.ca"

# ---------------------------------------------------------------------------
# Product name extraction regexes
# ---------------------------------------------------------------------------

# "Tecfidera (dimethyl fumarate)" or "Lunsumio SC (mosunetuzumab injection)"
_PARENTHETICAL_PRODUCT_RE = re.compile(
    r"\b(?P<brand>[A-Z][A-Za-z0-9\-\s]{1,40}?)\s*\((?P<generic>[^)]{3,80})\)",
)

# "dimethyl fumarate-containing products"
_INGREDIENT_PHRASE_RE = re.compile(
    r"\b(?P<generic>[a-z][a-z\-\s]{3,50}?)\s*[\-–]\s*containing\b",
    re.IGNORECASE,
)

# Date patterns in article pages
_DATE_PATTERNS = [
    re.compile(r"(?:posted|published|updated|date[d]?)[:\s]+(?P<date>\w+ \d{1,2},?\s*\d{4})", re.IGNORECASE),
    re.compile(r"\b(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b"),
]

# Headings that indicate structural/boilerplate content to skip
_STRUCTURAL_HEADINGS = {
    "scope", "reporting adverse reactions", "helpful links", "contact us",
    "on this page", "table of contents", "references", "footnotes",
}

# Minimum characters for a paragraph to be considered meaningful content
_MIN_PARA_CHARS = 30


class ArticleParser:
    """
    Parses a single Health Canada InfoWatch article HTML page.

    Usage::

        parser = ArticleParser()
        article = parser.parse(html=html, index_entry=entry)
    """

    def parse(self, html: str, index_entry: IndexEntry) -> HealthCanadaArticle:
        """
        Parse article HTML and return a HealthCanadaArticle.

        Args:
            html:         Raw HTML string of the article page.
            index_entry:  The IndexEntry that led to this article being fetched.

        Returns:
            HealthCanadaArticle with extracted content and ProductMentions.
        """
        soup = BeautifulSoup(html, "html.parser")

        article = HealthCanadaArticle(
            article_url=index_entry.article_url.split("#")[0],
            anchor=index_entry.article_url.split("#")[1] if "#" in index_entry.article_url else "",
            index_url=index_entry.index_url,
            newsletter_month=index_entry.month,
            newsletter_year=index_entry.year,
            newsletter_type=index_entry.newsletter_type,
            article_type=index_entry.article_type,
            publication_date=index_entry.publication_date,
            raw_html=html,
        )

        # ── Find main content area ────────────────────────────────────
        main = (
            soup.find("main")
            or soup.find(id="wb-cont")
            or soup.find("div", class_=re.compile(r"mwsbodytext|mwsgeneric"))
            or soup.body
        )
        if not main:
            logger.warning("Could not locate main content in article: %s", article.article_url)
            article.full_text = soup.get_text(" ", strip=True)
            return article

        # ── Title ─────────────────────────────────────────────────────
        article.title = self._extract_title(soup, index_entry)

        # ── Publication date ──────────────────────────────────────────
        extracted_date = self._extract_date(main)
        if extracted_date:
            article.publication_date = extracted_date

        # ── PDF links ─────────────────────────────────────────────────
        article.pdf_urls = self._extract_pdf_links(main, article.article_url)

        # ── Sections (heading + content blocks) ───────────────────────
        sections = self._extract_sections(main)
        article.sections = sections
        article.headings = [s["heading"] for s in sections if s.get("heading")]
        article.full_text = "\n\n".join(
            f"{s.get('heading','')}\n{s.get('text','')}" for s in sections
        ).strip()
        article.tables = [t for s in sections for t in s.get("tables", [])]

        # ── Product mentions ──────────────────────────────────────────
        article.product_mentions = self._extract_product_mentions(
            sections=sections,
            index_entry=index_entry,
        )

        return article

    # ------------------------------------------------------------------
    # Title extraction
    # ------------------------------------------------------------------

    def _extract_title(self, soup: BeautifulSoup, index_entry: IndexEntry) -> str:
        # Try h1 first
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        # Fall back to index entry title
        return index_entry.article_title

    # ------------------------------------------------------------------
    # Date extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_date(content: Tag):
        """Try to extract a publication date from article content."""
        from datetime import date as date_class
        text = content.get_text(" ", strip=True)
        for pattern in _DATE_PATTERNS:
            m = pattern.search(text)
            if m:
                date_str = m.group("date").strip()
                try:
                    from dateutil import parser as du_parser
                    return du_parser.parse(date_str, fuzzy=True).date()
                except Exception:
                    pass
        return None

    # ------------------------------------------------------------------
    # PDF link extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_pdf_links(content: Tag, base_url: str) -> List[str]:
        """Find all PDF links within the article content."""
        pdf_urls = []
        for a in content.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().endswith(".pdf") or "pdf" in href.lower():
                absolute = href if href.startswith("http") else urljoin(HC_BASE_URL, href)
                pdf_urls.append(absolute)
        return list(dict.fromkeys(pdf_urls))  # deduplicate, preserve order

    # ------------------------------------------------------------------
    # Section extraction
    # ------------------------------------------------------------------

    def _extract_sections(self, content: Tag) -> List[dict]:
        """
        Walk the content area and group content by heading.

        Returns a list of dicts:
            {"heading": str, "text": str, "tables": [[[str]]]}
        """
        sections = []
        current_heading = ""
        current_paragraphs: List[str] = []
        current_tables: List[List[List[str]]] = []

        def flush():
            text = "\n".join(p for p in current_paragraphs if p.strip())
            if current_heading or text or current_tables:
                sections.append({
                    "heading": current_heading,
                    "text": text,
                    "tables": list(current_tables),
                })

        for element in content.children:
            if not isinstance(element, Tag):
                continue

            tag_name = element.name.lower() if element.name else ""

            # Headings
            if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                flush()
                current_heading = element.get_text(strip=True)
                current_paragraphs = []
                current_tables = []
                continue

            # Tables
            if tag_name == "table":
                table_data = self._extract_table(element)
                if table_data:
                    current_tables.append(table_data)
                continue

            # Paragraphs and lists
            if tag_name in ("p", "ul", "ol", "dl", "div", "section", "article"):
                text = element.get_text(" ", strip=True)
                if len(text) >= _MIN_PARA_CHARS:
                    current_paragraphs.append(text)

                # Recurse into divs that may contain sub-headings
                if tag_name in ("div", "section", "article"):
                    sub_sections = self._extract_sections(element)
                    if sub_sections:
                        flush()
                        current_heading = ""
                        current_paragraphs = []
                        current_tables = []
                        sections.extend(sub_sections)
                continue

        flush()
        return sections

    @staticmethod
    def _extract_table(table_tag: Tag) -> List[List[str]]:
        """Extract a 2D list of strings from an HTML table tag."""
        rows = []
        for tr in table_tag.find_all("tr"):
            row = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
            if any(cell.strip() for cell in row):
                rows.append(row)
        return rows if len(rows) >= 1 else []

    # ------------------------------------------------------------------
    # Product mention extraction
    # ------------------------------------------------------------------

    def _extract_product_mentions(
        self,
        sections: List[dict],
        index_entry: IndexEntry,
    ) -> List[ProductMention]:
        """
        Identify distinct products in the article sections.

        Strategy:
        1. Start with the product already identified in the IndexEntry.
        2. Scan each section heading and text for additional product patterns.
        3. Avoid duplicates (normalised name matching).
        4. Attach the relevant section context to each ProductMention.
        """
        from app.services.normalization import NormalizationService

        mentions: List[ProductMention] = []
        seen_normalised: set = set()

        def add_if_new(product_name: str, generic_name: str, section: dict):
            norm_p = NormalizationService.normalize_drug_name(product_name or generic_name)
            if not norm_p or norm_p in seen_normalised:
                return
            seen_normalised.add(norm_p)
            mentions.append(ProductMention(
                product_name=product_name,
                generic_name=generic_name,
                normalized_product=NormalizationService.normalize_drug_name(product_name),
                normalized_generic=NormalizationService.normalize_drug_name(generic_name),
                section_heading=section.get("heading", ""),
                context_text=section.get("text", "")[:2000],  # cap at 2000 chars
                article_type=index_entry.article_type,
            ))

        # Seed with index entry data
        if index_entry.product_name or index_entry.generic_name:
            # Find the best matching section
            best_section = self._find_best_section(
                sections, index_entry.product_name, index_entry.generic_name
            )
            add_if_new(index_entry.product_name, index_entry.generic_name, best_section)

        # Scan sections for additional product mentions
        for section in sections:
            heading = section.get("heading", "")
            text = section.get("text", "")

            # Skip structural sections
            if heading.lower().strip() in _STRUCTURAL_HEADINGS:
                continue

            combined = f"{heading}\n{text}"

            # Pattern 1: "Brand (generic)"
            for m in _PARENTHETICAL_PRODUCT_RE.finditer(combined):
                brand = m.group("brand").strip()
                generic = m.group("generic").strip()
                # Basic sanity: brand should start uppercase, generic lowercase
                if brand and generic and len(brand) >= 3:
                    add_if_new(brand, generic, section)

            # Pattern 2: "ingredient-containing products"
            for m in _INGREDIENT_PHRASE_RE.finditer(combined):
                generic = m.group("generic").strip()
                if generic and len(generic) >= 4:
                    add_if_new("", generic, section)

        return mentions

    @staticmethod
    def _find_best_section(
        sections: List[dict],
        product_name: str,
        generic_name: str,
    ) -> dict:
        """Find the section most relevant to the given product names."""
        search_terms = [t.lower() for t in [product_name, generic_name] if t]
        if not search_terms:
            return sections[0] if sections else {}

        best = {}
        best_score = -1
        for section in sections:
            text = (section.get("heading", "") + " " + section.get("text", "")).lower()
            score = sum(text.count(term) for term in search_terms)
            if score > best_score:
                best_score = score
                best = section

        return best if best else (sections[0] if sections else {})


# Module-level singleton
parser = ArticleParser()
