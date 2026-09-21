"""
FDA MedWatch Article Parser.
Extracts structured metadata, dates, product identifiers, and safety summaries
from official FDA MedWatch safety communications, alerts, and recall pages.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from bs4 import BeautifulSoup

from app.sources.fda_medwatch.models import MedWatchArticle

logger = logging.getLogger(__name__)

DATE_REGEX = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)


class FDAMedWatchArticleParser:
    """Parses MedWatch HTML articles and extracts article metadata."""

    @staticmethod
    def parse_article(html_content: str, url: str) -> Optional[MedWatchArticle]:
        """Parses an FDA MedWatch HTML safety article into a MedWatchArticle model."""
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, "lxml")

        # 1. Title
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = " ".join(h1.get_text().strip().split())
        if not title and soup.title:
            title = " ".join(soup.title.get_text().strip().split())

        # Clean title suffix e.g. " | FDA"
        title = re.sub(r"\s*\|\s*FDA\s*$", "", title).strip()

        # 2. Publication Date
        pub_date = None
        time_tag = soup.find("time")
        if time_tag:
            pub_date = time_tag.get("datetime") or time_tag.get_text().strip()
        if not pub_date:
            meta_date = soup.find("meta", property="article:published_time")
            if meta_date and meta_date.get("content"):
                pub_date = meta_date["content"].strip()
        if not pub_date:
            m = DATE_REGEX.search(html_content[:4000])
            if m:
                pub_date = m.group(0)

        # 3. Product / Active Ingredient detection from title or lead paragraph
        product_name = None
        active_ingredient = None
        m_paren = re.search(r"([A-Z][A-Za-z0-9\-\s]+?)\s*\(([^)]+)\)", title)
        if m_paren:
            product_name = m_paren.group(1).strip()
            active_ingredient = m_paren.group(2).strip()

        # 4. Safety Topic / Summary
        summary = ""
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            summary = meta_desc["content"].strip()
        if not summary:
            # First significant paragraph
            for p in soup.find_all("p"):
                txt = " ".join(p.get_text().strip().split())
                if len(txt) > 40 and not txt.lower().startswith(("fda", "search", "menu")):
                    summary = txt
                    break

        return MedWatchArticle(
            title=title or "FDA MedWatch Safety Alert",
            url=url,
            publication_date=pub_date,
            product_name=product_name,
            active_ingredient=active_ingredient,
            safety_topic=title,
            summary=summary,
        )
