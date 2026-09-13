"""
Data models / dataclasses for the Health Canada Health Product InfoWatch adapter.

These are in-memory transfer objects used during crawl and extraction.
They are NOT SQLAlchemy ORM models — all persistence uses the existing
Drug / SafetyLabelingChange / SafetyChangeVersion models in app/models/drug.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


# ---------------------------------------------------------------------------
# Article type classification
# ---------------------------------------------------------------------------

class ArticleType(str, Enum):
    """Classification for Health Canada InfoWatch article types."""
    MONTHLY_RECAP = "MONTHLY_RECAP"
    PRODUCT_MONOGRAPH_UPDATE = "PRODUCT_MONOGRAPH_UPDATE"
    SAFETY_BRIEF = "SAFETY_BRIEF"
    SAFETY_SUMMARY = "SAFETY_SUMMARY"
    VACCINE_SAFETY_SUMMARY = "VACCINE_SAFETY_SUMMARY"
    MEDICATION_ERROR_ALERT = "MEDICATION_ERROR_ALERT"
    MARKET_AUTHORIZATION_WITH_CONDITIONS = "MARKET_AUTHORIZATION_WITH_CONDITIONS"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    ADVERSE_REACTION_INFORMATION = "ADVERSE_REACTION_INFORMATION"
    REVIEW_ARTICLE = "REVIEW_ARTICLE"
    OTHER = "OTHER"
    # Skip types — these are structural / boilerplate sections, not safety content
    SKIP = "SKIP"


# ---------------------------------------------------------------------------
# Index-level entries (discovered from the published-newsletters index page)
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    """
    A single article discovered from the Health Canada published-newsletters index.

    Populated entirely from the index page WITHOUT opening the article URL.
    Used as the first-pass filter before deciding whether to crawl the article.
    """
    # Newsletter metadata
    newsletter_type: str          # "Health Product InfoWatch" | "Canadian Adverse Reaction Newsletter"
    month: str                    # e.g. "August"
    year: int                     # e.g. 2026
    publication_date: Optional[date] = None

    # Category / hierarchy from the nested list structure
    category_level1: str = ""     # e.g. "Monthly recap of health product safety information"
    category_level2: str = ""     # e.g. "New health product safety information"
    category_level3: str = ""     # e.g. "Product monograph update"

    # Article / product entry
    article_title: str = ""       # Full link text, e.g. "Tecfidera (dimethyl fumarate)"
    article_url: str = ""         # Absolute URL with anchor, e.g. ".../august-2026.html#a2.2.1"

    # Derived — extracted from article_title during discovery
    product_name: str = ""        # Brand name e.g. "Tecfidera"
    generic_name: str = ""        # Active ingredient e.g. "dimethyl fumarate"

    # Classification assigned by classifier.py
    article_type: ArticleType = ArticleType.OTHER

    # Source traceability
    index_url: str = ""           # The published-newsletters index page URL
    index_section_anchor: str = ""  # Anchor on index page pointing to this entry


# ---------------------------------------------------------------------------
# Product mention within an article
# ---------------------------------------------------------------------------

@dataclass
class ProductMention:
    """
    A single product/medicine identified inside an article.

    A monthly recap may contain multiple distinct ProductMentions.
    Each ProductMention is stored as a separate SafetyLabelingChange entry.
    """
    product_name: str             # Brand/product name
    generic_name: str             # Active ingredient / generic name
    normalized_product: str       # Lowercased/normalized for DB matching
    normalized_generic: str       # Lowercased/normalized for DB matching

    # Context extracted around this product mention
    section_heading: str = ""     # Nearest heading before the product mention
    context_text: str = ""        # Surrounding paragraphs / list items
    article_type: ArticleType = ArticleType.OTHER

    # Safety / regulatory fields (populated when article type warrants it)
    safety_issue: str = ""
    risk_description: str = ""
    health_canada_assessment: str = ""
    recommendation: str = ""
    manufacturer: str = ""
    monograph_section: str = ""   # For product monograph updates


# ---------------------------------------------------------------------------
# Fully extracted article
# ---------------------------------------------------------------------------

@dataclass
class HealthCanadaArticle:
    """
    Extracted content from a single Health Canada InfoWatch article page.

    Populated by parser.py after fetching and parsing the article HTML.
    """
    # Identity / traceability
    article_url: str              # Canonical URL (no anchor)
    anchor: str = ""              # Fragment/anchor if applicable
    index_url: str = ""           # Published-newsletters index URL

    # Metadata
    title: str = ""
    newsletter_month: str = ""
    newsletter_year: int = 0
    newsletter_type: str = "Health Product InfoWatch"
    article_type: ArticleType = ArticleType.OTHER
    publication_date: Optional[date] = None

    # Extracted content
    headings: List[str] = field(default_factory=list)
    full_text: str = ""           # All visible text, whitespace-normalized
    sections: List[dict] = field(default_factory=list)   # [{heading, text, tables}]
    tables: List[List[List[str]]] = field(default_factory=list)  # Extracted HTML tables

    # Products / medicines identified in this article
    product_mentions: List[ProductMention] = field(default_factory=list)

    # PDF links discovered in the article — to be routed to the existing PDF extractor
    pdf_urls: List[str] = field(default_factory=list)

    # Content hash for change detection (computed by adapter)
    content_hash: str = ""

    # Fetch metadata
    http_status: Optional[int] = None
    fetch_error: Optional[str] = None
    raw_html: str = ""            # Stored for re-processing; not persisted to DB
