"""
Tests for the Health Canada InfoWatch article-type classifier.
"""
from __future__ import annotations

import pytest
from app.sources.health_canada.infowatch.classifier import ArticleClassifier
from app.sources.health_canada.infowatch.models import ArticleType


@pytest.fixture
def clf() -> ArticleClassifier:
    return ArticleClassifier()


class TestArticleClassifier:

    def test_monthly_recap(self, clf):
        result = clf.classify(
            category_level1="Monthly recap of health product safety information",
            article_title="Omnitrope (somatropin for injection)",
        )
        assert result == ArticleType.MONTHLY_RECAP

    def test_product_monograph_update(self, clf):
        result = clf.classify(
            category_level1="New health product safety information",
            category_level3="Product monograph update",
            article_title="Tecfidera (dimethyl fumarate)",
        )
        assert result == ArticleType.PRODUCT_MONOGRAPH_UPDATE

    def test_safety_brief(self, clf):
        result = clf.classify(
            category_level1="New health product safety information",
            category_level3="Safety brief",
            article_title="Carbamazepine and oxcarbazepine oral suspensions",
        )
        assert result == ArticleType.SAFETY_BRIEF

    def test_safety_brief_from_level2(self, clf):
        result = clf.classify(
            category_level2="Safety briefs",
            article_title="Hepatotoxicity risk",
        )
        assert result == ArticleType.SAFETY_BRIEF

    def test_vaccine_safety_summary(self, clf):
        result = clf.classify(
            category_level3="Vaccine safety summary",
            article_title="2025 AEFI data",
        )
        assert result == ArticleType.VACCINE_SAFETY_SUMMARY

    def test_aefi_from_title(self, clf):
        result = clf.classify(
            category_level1="New health product safety information",
            article_title="2025 AEFI data",
        )
        assert result == ArticleType.VACCINE_SAFETY_SUMMARY

    def test_medication_error_alert(self, clf):
        result = clf.classify(
            category_level3="Medication error alert",
            article_title="Psyllium and the risk of choking",
        )
        assert result == ArticleType.MEDICATION_ERROR_ALERT

    def test_market_authorization_with_conditions(self, clf):
        result = clf.classify(
            category_level3="Notice of market authorization with conditions",
            article_title="Ojemda (tovorafenib): Authorization with conditions",
        )
        assert result == ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS

    def test_authorization_in_title(self, clf):
        result = clf.classify(
            category_level2="New health product safety information",
            article_title="Wegovy (semaglutide): Authorization with conditions",
        )
        assert result == ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS

    def test_announcement(self, clf):
        result = clf.classify(
            category_level1="Announcement",
            article_title="Health Canada News: Ministerial Reliance Order",
        )
        assert result == ArticleType.ANNOUNCEMENT

    def test_scope_is_skip(self, clf):
        result = clf.classify(
            article_title="Scope",
        )
        assert result == ArticleType.SKIP

    def test_reporting_adverse_reactions_is_skip(self, clf):
        result = clf.classify(
            article_title="Reporting adverse reactions",
        )
        assert result == ArticleType.SKIP

    def test_helpful_links_is_skip(self, clf):
        result = clf.classify(
            article_title="Helpful links",
        )
        assert result == ArticleType.SKIP

    def test_contact_us_is_skip(self, clf):
        result = clf.classify(
            article_title="Contact us",
        )
        assert result == ArticleType.SKIP

    def test_level3_takes_precedence_over_level1(self, clf):
        # Level3 = "Product monograph update" should win over level1 = "Monthly recap"
        result = clf.classify(
            category_level1="Monthly recap of health product safety information",
            category_level3="Product monograph update",
            article_title="Some Drug",
        )
        assert result == ArticleType.PRODUCT_MONOGRAPH_UPDATE

    def test_is_safety_relevant_true(self, clf):
        for t in [
            ArticleType.MONTHLY_RECAP,
            ArticleType.PRODUCT_MONOGRAPH_UPDATE,
            ArticleType.SAFETY_BRIEF,
            ArticleType.VACCINE_SAFETY_SUMMARY,
            ArticleType.MEDICATION_ERROR_ALERT,
            ArticleType.MARKET_AUTHORIZATION_WITH_CONDITIONS,
        ]:
            assert clf.is_safety_relevant(t), f"{t} should be safety relevant"

    def test_is_safety_relevant_false_for_skip(self, clf):
        assert not clf.is_safety_relevant(ArticleType.SKIP)

    def test_unknown_falls_back_to_other(self, clf):
        result = clf.classify(
            category_level1="Something entirely unrecognised",
            article_title="Random entry",
        )
        assert result == ArticleType.OTHER
