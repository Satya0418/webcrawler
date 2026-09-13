"""
Article-type classifier for Health Canada InfoWatch articles.

Maps category headings, article titles, URL fragments, and link text to
ArticleType enum values.

Classification uses the full context available from the index structure:
  - category_level1 (top-level section heading)
  - category_level2 (sub-section heading, e.g. "New health product safety information")
  - category_level3 (leaf category, e.g. "Product monograph update")
  - article_title   (product/article link text)
  - URL fragment    (anchor, secondary signal only)

Rules are intentionally simple and deterministic — no ML, no LLM.
If a title matches multiple rules the most specific one wins.
"""
from __future__ import annotations

import re
from typing import Optional

from app.sources.health_canada.infowatch.models import ArticleType

# ---------------------------------------------------------------------------
# Structural / boilerplate anchor texts — these are not safety content
# ---------------------------------------------------------------------------

_SKIP_PATTERNS = [
    r"\bscope\b",
    r"\breporting adverse reactions\b",
    r"\bhelpful links\b",
    r"\bcontact us\b",
    r"\bon this page\b",
    r"\bcontents?\b$",           # bare "content" links
    r"\bannual reports?\b",
]

_SKIP_RE = re.compile("|".join(_SKIP_PATTERNS), re.IGNORECASE)

# ---------------------------------------------------------------------------
# Category → ArticleType mappings  (ordered: most specific first)
# ---------------------------------------------------------------------------

# Maps normalised text fragments to ArticleType
_CATEGORY_RULES: list[tuple[re.Pattern, ArticleType]] = [
    # --- Leaf categories (level3) ---
    (re.compile(r"product\s+monograph\s+updat", re.IGNORECASE),          ArticleType.PRODUCT_MONOGRAPH_UPDATE),
    (re.compile(r"safety\s+brief", re.IGNORECASE),                       ArticleType.SAFETY_BRIEF),
    (re.compile(r"vaccine\s+safety\s+summar", re.IGNORECASE),            ArticleType.VACCINE_SAFETY_SUMMARY),
    (re.compile(r"health\s+product\s+safety\s+summar", re.IGNORECASE),   ArticleType.SAFETY_SUMMARY),
    (re.compile(r"medication\s+error\s+alert", re.IGNORECASE),            ArticleType.MEDICATION_ERROR_ALERT),
    (re.compile(r"notice\s+of\s+market\s+authoriz", re.IGNORECASE),      ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS),
    (re.compile(r"authoriz\w+\s+with\s+conditions?", re.IGNORECASE),     ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS),
    # --- Level1 / level2 categories ---
    (re.compile(r"monthly\s+recap", re.IGNORECASE),                       ArticleType.MONTHLY_RECAP),
    (re.compile(r"announcement", re.IGNORECASE),                          ArticleType.ANNOUNCEMENT),
    (re.compile(r"aefi\s+data|adverse\s+event.*following\s+immuniz", re.IGNORECASE),
                                                                          ArticleType.VACCINE_SAFETY_SUMMARY),
    (re.compile(r"adverse\s+reaction", re.IGNORECASE),                   ArticleType.ADVERSE_REACTION_INFORMATION),
    (re.compile(r"new\s+health\s+product\s+safety\s+information", re.IGNORECASE),
                                                                          ArticleType.SAFETY_SUMMARY),
]

# Additional signals from article title (not category)
_TITLE_RULES: list[tuple[re.Pattern, ArticleType]] = [
    (re.compile(r"authoriz\w+\s+with\s+conditions?", re.IGNORECASE),     ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS),
    (re.compile(r"aefi\s+data", re.IGNORECASE),                          ArticleType.VACCINE_SAFETY_SUMMARY),
    (re.compile(r"\d{4}\s+aefi\b", re.IGNORECASE),                       ArticleType.VACCINE_SAFETY_SUMMARY),
    (re.compile(r"\d{4}\s+ar\s+data\b", re.IGNORECASE),                  ArticleType.ADVERSE_REACTION_INFORMATION),
]


class ArticleClassifier:
    """
    Stateless classifier that maps index-level metadata to ArticleType.

    Usage::

        classifier = ArticleClassifier()
        article_type = classifier.classify(
            category_level1="Monthly recap of health product safety information",
            category_level2="",
            category_level3="",
            article_title="Omnitrope (somatropin for injection)",
        )
        # → ArticleType.MONTHLY_RECAP
    """

    @staticmethod
    def classify(
        category_level1: str = "",
        category_level2: str = "",
        category_level3: str = "",
        article_title: str = "",
        url: str = "",
    ) -> ArticleType:
        """
        Classify an article based on its full context from the index.

        Precedence:
          1. SKIP if title matches structural boilerplate.
          2. category_level3 (most specific).
          3. category_level2.
          4. category_level1.
          5. article_title signals.
          6. ArticleType.OTHER as fallback.
        """
        # 1. Skip structural/boilerplate entries
        combined_for_skip = f"{article_title} {category_level1} {category_level2} {category_level3}"
        if _SKIP_RE.search(combined_for_skip):
            # But only if it's ONLY a structural entry (title is the structural word)
            if _SKIP_RE.search(article_title.strip()):
                return ArticleType.SKIP

        # 2. Most specific: level3 category
        if category_level3:
            result = ArticleClassifier._match_category(category_level3)
            if result is not None:
                return result

        # 3. Article title signals (checked BEFORE level2/level1 so specific title
        #    keywords like "Authorization with conditions" or "AEFI data" win over
        #    generic category headings like "New health product safety information")
        for pattern, article_type in _TITLE_RULES:
            if pattern.search(article_title):
                return article_type

        # 4. Level2 category
        if category_level2:
            result = ArticleClassifier._match_category(category_level2)
            if result is not None:
                return result

        # 5. Level1 (least specific) category
        if category_level1:
            result = ArticleClassifier._match_category(category_level1)
            if result is not None:
                return result

        return ArticleType.OTHER

    @staticmethod
    def _match_category(text: str) -> Optional[ArticleType]:
        for pattern, article_type in _CATEGORY_RULES:
            if pattern.search(text):
                return article_type
        return None

    @staticmethod
    def is_safety_relevant(article_type: ArticleType) -> bool:
        """
        Return True if this article type may contain safety-relevant content
        that should be fetched and extracted.

        SKIP, ANNOUNCEMENT (standalone), and OTHER are not automatically fetched.
        """
        return article_type in {
            ArticleType.MONTHLY_RECAP,
            ArticleType.PRODUCT_MONOGRAPH_UPDATE,
            ArticleType.SAFETY_BRIEF,
            ArticleType.SAFETY_SUMMARY,
            ArticleType.VACCINE_SAFETY_SUMMARY,
            ArticleType.MEDICATION_ERROR_ALERT,
            ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS,
            ArticleType.ADVERSE_REACTION_INFORMATION,
            ArticleType.REVIEW_ARTICLE,
        }


# Module-level singleton
classifier = ArticleClassifier()
