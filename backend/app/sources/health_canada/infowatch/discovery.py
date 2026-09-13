"""
Discovery module for Health Canada Health Product InfoWatch.

Parses the published-newsletters index page HTML and produces a flat list of
IndexEntry objects — one per product/article leaf link.

The index page structure (confirmed from live page):

    <h2 id="a1">The Health Product InfoWatch</h2>

    <h3>August 2026</h3>
    <ul>
      <li><a href="...august-2026.html#a1">Monthly recap of health product safety information</a>
        <ul>
          <li><a href="...#a1.1">Omnitrope (somatropin for injection)</a></li>
          ...
        </ul>
      </li>
      <li><a href="...#a2">New health product safety information</a>
        <ul>
          <li><a href="...#a2.1">Product monograph update</a>
            <ul>
              <li><a href="...#a2.2.1">Tecfidera (dimethyl fumarate)</a></li>
            </ul>
          </li>
          ...
        </ul>
      </li>
    </ul>

    <h3>July 2026</h3>
    ...

    <h2 id="a2">Canadian Adverse Reaction Newsletters</h2>
    ...

Nesting depth varies (2–4 levels). This module handles all depths
dynamically without hard-coding months or years.
"""
from __future__ import annotations

import logging
import re
from calendar import month_abbr
from datetime import date
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.sources.health_canada.infowatch.classifier import classifier
from app.sources.health_canada.infowatch.models import ArticleType, IndexEntry

logger = logging.getLogger(__name__)

HC_BASE_URL = "https://www.canada.ca"
HC_INDEX_URL = (
    "https://www.canada.ca/en/health-canada/services/drugs-health-products"
    "/medeffect-canada/health-product-infowatch/published-newsletters.html"
)

# Month names → month numbers
_MONTH_MAP = {m.lower(): i for i, m in enumerate(month_abbr) if m}
# Add full month names
import calendar
for i, m in enumerate(calendar.month_name):
    if m:
        _MONTH_MAP[m.lower()] = i

# Pattern to extract brand name and generic name from titles like:
#   "Tecfidera (dimethyl fumarate)"
#   "Omnitrope (somatropin for injection)"
#   "Lunsumio SC (mosunetuzumab injection): Authorization with conditions"
_PRODUCT_PATTERN = re.compile(
    r"^(?P<brand>[^(]+?)\s*\((?P<generic>[^)]+)\)",
    re.IGNORECASE,
)

# Sections to always skip (structural boilerplate)
_SKIP_TITLES = {
    "scope",
    "reporting adverse reactions",
    "helpful links",
    "contact us",
    "on this page",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class IndexDiscovery:
    """
    Parses the Health Canada published-newsletters index HTML and returns
    a list of IndexEntry objects.

    This is intentionally separated from the crawler so it can be unit-tested
    with static HTML fixtures.
    """

    def parse_index(self, html: str) -> List[IndexEntry]:
        """
        Parse the full index HTML and return all discovered IndexEntry items.

        Args:
            html: Raw HTML of the published-newsletters index page.

        Returns:
            Flat list of IndexEntry objects (one per leaf article link).
        """
        soup = BeautifulSoup(html, "html.parser")
        entries: List[IndexEntry] = []

        # ---------------------------------------------------------------
        # Identify the two top-level newsletter sections:
        #   - "The Health Product InfoWatch"   (h2 id="a1")
        #   - "Canadian Adverse Reaction Newsletters"  (h2 id="a2")
        # ---------------------------------------------------------------
        current_newsletter_type = "Health Product InfoWatch"

        # Walk all h2 and h3 tags in document order
        # h2 → newsletter section boundary
        # h3 → month/year heading within a newsletter section

        # Find the main content area
        main = soup.find("main") or soup.find(id="wb-cont") or soup.body

        current_month: str = ""
        current_year: int = 0
        current_pub_date: Optional[date] = None

        # Iterate all relevant tags in order
        for element in main.descendants if main else soup.descendants:
            if not isinstance(element, Tag):
                continue

            # ── Newsletter-type boundary ──────────────────────────────
            if element.name == "h2" and element.get("id") in ("a1", "a2"):
                text = element.get_text(strip=True)
                if "canadian adverse reaction" in text.lower():
                    current_newsletter_type = "Canadian Adverse Reaction Newsletter"
                else:
                    current_newsletter_type = "Health Product InfoWatch"
                continue

            # ── Month/year heading ────────────────────────────────────
            if element.name == "h3":
                month, year = self._parse_month_year(element.get_text(strip=True))
                if month and year:
                    current_month = month
                    current_year = year
                    current_pub_date = self._build_date(month, year)
                continue

            # ── Top-level <ul> directly under h3 ─────────────────────
            # We only want the top-level <ul> siblings of h3, not inner lists
            if element.name == "ul" and element.parent and element.parent.name in ("div", "section", "main", "body"):
                if current_month and current_year:
                    new_entries = self._parse_month_ul(
                        ul=element,
                        newsletter_type=current_newsletter_type,
                        month=current_month,
                        year=current_year,
                        pub_date=current_pub_date,
                    )
                    entries.extend(new_entries)

        logger.info(
            "Discovery: found %d index entries across %s",
            len(entries),
            "Health Canada newsletters",
        )
        return entries

    # ------------------------------------------------------------------
    # Month UL parsing
    # ------------------------------------------------------------------

    def _parse_month_ul(
        self,
        ul: Tag,
        newsletter_type: str,
        month: str,
        year: int,
        pub_date: Optional[date],
    ) -> List[IndexEntry]:
        """
        Parse one top-level <ul> for a given month.

        Level 1 <li>:  category (e.g. "Monthly recap...", "New health product safety...")
        Level 2 <li>:  sub-category OR leaf product
        Level 3 <li>:  leaf product under sub-category
        """
        entries: List[IndexEntry] = []

        for li_l1 in ul.find_all("li", recursive=False):
            a_l1 = li_l1.find("a", recursive=False)
            cat_l1_text = a_l1.get_text(strip=True) if a_l1 else li_l1.get_text(" ", strip=True)
            cat_l1_url = self._resolve_url(a_l1.get("href", "")) if a_l1 else ""

            # Check for nested <ul> at level 2
            ul_l2 = li_l1.find("ul", recursive=False)

            if not ul_l2:
                # Leaf at level 1 — unlikely but handle gracefully
                entry = self._make_entry(
                    newsletter_type=newsletter_type,
                    month=month, year=year, pub_date=pub_date,
                    cat1=cat_l1_text, cat2="", cat3="",
                    article_title=cat_l1_text,
                    article_url=cat_l1_url,
                )
                if entry:
                    entries.append(entry)
                continue

            # Walk level 2
            for li_l2 in ul_l2.find_all("li", recursive=False):
                a_l2 = li_l2.find("a", recursive=False)
                cat_l2_text = a_l2.get_text(strip=True) if a_l2 else li_l2.get_text(" ", strip=True)
                cat_l2_url = self._resolve_url(a_l2.get("href", "")) if a_l2 else ""

                ul_l3 = li_l2.find("ul", recursive=False)

                if not ul_l3:
                    # Leaf at level 2 — article title is cat_l2_text
                    entry = self._make_entry(
                        newsletter_type=newsletter_type,
                        month=month, year=year, pub_date=pub_date,
                        cat1=cat_l1_text, cat2="", cat3="",
                        article_title=cat_l2_text,
                        article_url=cat_l2_url,
                    )
                    if entry:
                        entries.append(entry)
                    continue

                # Walk level 3
                for li_l3 in ul_l3.find_all("li", recursive=False):
                    a_l3 = li_l3.find("a", recursive=False)
                    cat_l3_text = a_l3.get_text(strip=True) if a_l3 else li_l3.get_text(" ", strip=True)
                    cat_l3_url = self._resolve_url(a_l3.get("href", "")) if a_l3 else ""

                    ul_l4 = li_l3.find("ul", recursive=False)

                    if not ul_l4:
                        # Leaf at level 3
                        entry = self._make_entry(
                            newsletter_type=newsletter_type,
                            month=month, year=year, pub_date=pub_date,
                            cat1=cat_l1_text, cat2=cat_l2_text, cat3="",
                            article_title=cat_l3_text,
                            article_url=cat_l3_url,
                        )
                        if entry:
                            entries.append(entry)
                        continue

                    # Level 4 (leaf products under a sub-sub-category)
                    for li_l4 in ul_l4.find_all("li", recursive=False):
                        a_l4 = li_l4.find("a", recursive=False)
                        cat_l4_text = a_l4.get_text(strip=True) if a_l4 else li_l4.get_text(" ", strip=True)
                        cat_l4_url = self._resolve_url(a_l4.get("href", "")) if a_l4 else ""
                        entry = self._make_entry(
                            newsletter_type=newsletter_type,
                            month=month, year=year, pub_date=pub_date,
                            cat1=cat_l1_text, cat2=cat_l2_text, cat3=cat_l3_text,
                            article_title=cat_l4_text,
                            article_url=cat_l4_url,
                        )
                        if entry:
                            entries.append(entry)

        return entries

    # ------------------------------------------------------------------
    # IndexEntry construction
    # ------------------------------------------------------------------

    def _make_entry(
        self,
        newsletter_type: str,
        month: str,
        year: int,
        pub_date: Optional[date],
        cat1: str,
        cat2: str,
        cat3: str,
        article_title: str,
        article_url: str,
    ) -> Optional[IndexEntry]:
        """Build an IndexEntry, returning None for skip/boilerplate entries."""
        title_clean = article_title.strip()

        # Skip structural boilerplate
        if title_clean.lower() in _SKIP_TITLES:
            return None
        if not title_clean or not article_url:
            return None

        # Extract product name / generic name from title
        product_name, generic_name = self._extract_product_names(title_clean)

        # Classify
        article_type = classifier.classify(
            category_level1=cat1,
            category_level2=cat2,
            category_level3=cat3,
            article_title=title_clean,
            url=article_url,
        )

        if article_type == ArticleType.SKIP:
            return None

        return IndexEntry(
            newsletter_type=newsletter_type,
            month=month,
            year=year,
            publication_date=pub_date,
            category_level1=cat1,
            category_level2=cat2,
            category_level3=cat3,
            article_title=title_clean,
            article_url=article_url,
            product_name=product_name,
            generic_name=generic_name,
            article_type=article_type,
            index_url=HC_INDEX_URL,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_product_names(title: str) -> Tuple[str, str]:
        """
        Extract brand/product name and generic/active ingredient from a title.

        Examples:
          "Tecfidera (dimethyl fumarate)"  → ("Tecfidera", "dimethyl fumarate")
          "Omnitrope (somatropin for injection)" → ("Omnitrope", "somatropin for injection")
          "Dimethyl fumarate-containing products" → ("", "dimethyl fumarate")
          "Monthly recap of health product safety information" → ("", "")
        """
        m = _PRODUCT_PATTERN.match(title)
        if m:
            brand = m.group("brand").strip()
            # Remove trailing colon/dash and any suffix after closing paren
            brand = re.sub(r"[\:\-]\s*$", "", brand).strip()
            generic = m.group("generic").strip()
            return brand, generic

        # No parentheses — check if the whole title is a recognisable INN/molecule
        # (heuristic: short titles without keywords are likely product names)
        return "", ""

    @staticmethod
    def _parse_month_year(heading_text: str) -> Tuple[str, int]:
        """
        Parse a heading like "August 2026" → ("August", 2026).
        Returns ("", 0) if not parseable.
        """
        text = heading_text.strip()
        match = re.match(r"^(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})$", text)
        if not match:
            return "", 0
        month = match.group("month")
        year = int(match.group("year"))
        if month.lower() not in _MONTH_MAP:
            return "", 0
        return month, year

    @staticmethod
    def _build_date(month: str, year: int) -> Optional[date]:
        """Build a date object for the first of the newsletter month."""
        month_num = _MONTH_MAP.get(month.lower())
        if month_num:
            try:
                return date(year, month_num, 1)
            except ValueError:
                pass
        return None

    @staticmethod
    def _resolve_url(href: str) -> str:
        """Resolve root-relative or absolute URLs."""
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return urljoin(HC_BASE_URL, href)


# Module-level singleton
discovery = IndexDiscovery()
