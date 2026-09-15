#!/usr/bin/env python3
"""
FDA Adverse Reactions Extractor & Report Formatter.

Extracts the latest Adverse Reactions labeling change for a medicine:
1. Analyzes all dates in descending chronological order (newest date first).
2. Selects the most recent date containing an Adverse Reactions section.
   (e.g., if 2026 has no adverse reaction, but 2025 does, selects 2025).
3. Strips section 17 (17 PCI/PI/MG / Medication Guide / Patient Counseling Information).
4. Strips editorial noise ('Additions underlined', '...', and in-text references like '[see Warnings...]').
5. Formats the date as DD-Mon-YYYY (e.g., 05-Dec-2025).
6. Generates the exact report format shown in Image 2.
7. If no Adverse Reactions found across all dates, outputs:
   'No data is present on adverse reaction'.

Usage:
  python extract_adverse_reactions.py "ARIKAYCE"
  python extract_adverse_reactions.py "Warfarin"
  python extract_adverse_reactions.py --url "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm?event=searchdetail.page&DrugNameID=2214"
  python extract_adverse_reactions.py --file tests/fixtures/fda/detail_zyvox.html
"""
import sys
import os
import argparse
import asyncio
import json
import logging

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.services.database_service import DatabaseService
from app.scrapers.fda_srlc_scraper import scraper
from app.crawler.fda_crawler import crawler

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


async def fetch_and_extract_adverse_reactions(
    drug_name: str = None,
    url: str = None,
    file_path: str = None,
    use_db: bool = True,
) -> dict:
    """
    Fetch and extract Adverse Reactions according to user specifications.
    """
    # 1. From local file / fixture
    if file_path:
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "message": f"File not found: {file_path}",
                "formatted_report": "No data is present on adverse reaction",
            }
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        return scraper.extract_adverse_reactions_report(html, drug_name=drug_name)

    # 2. From direct detail URL
    if url:
        html = await crawler.get_detail_page(url)
        if not html:
            return {
                "status": "error",
                "message": f"Could not fetch detail page from {url}",
                "formatted_report": "No data is present on adverse reaction",
            }
        return scraper.extract_adverse_reactions_report(html, drug_name=drug_name, source_url=url)

    # 3. From Drug Name
    if not drug_name:
        return {
            "status": "error",
            "message": "Please specify a drug name, --url, or --file",
            "formatted_report": "No data is present on adverse reaction",
        }

    query_clean = drug_name.strip()

    # 1. First, search live on FDA SrLC to ensure latest published supplements are never missed
    try:
        search_html = await crawler.search_drug(query_clean)
        if search_html:
            candidates = scraper.parse_search_results(search_html)
            if candidates:
                for cand in candidates[:3]:
                    detail_url = cand.get("detail_url")
                    if detail_url:
                        detail_html = await crawler.get_detail_page(detail_url)
                        if detail_html:
                            # Parse detail and sync to DB
                            if use_db:
                                try:
                                    db = SessionLocal()
                                    drug, _ = DatabaseService.insert_or_update_drug(db, cand)
                                    detail_data = scraper.parse_detail_page(detail_html, source_url=detail_url)
                                    if detail_data:
                                        for chg in detail_data.get("safety_changes", []):
                                            DatabaseService.save_safety_change(db, drug.id, chg)
                                        db.commit()
                                    db.close()
                                except Exception as e:
                                    logger.debug(f"DB sync during live extraction error: {e}")

                            report = scraper.extract_adverse_reactions_report(
                                detail_html,
                                drug_name=cand.get("drug_name"),
                                active_ingredient=cand.get("active_ingredient"),
                                source_url=detail_url,
                            )
                            if report.get("status") == "success":
                                return report
    except Exception as e:
        logger.warning(f"Online search error for '{query_clean}': {e}")

    # 2. Fallback to local database if online crawl returned no match or offline
    if use_db:
        try:
            db = SessionLocal()
            local_drugs = DatabaseService.search_drugs(db, query_clean)
            if local_drugs:
                for d in local_drugs:
                    changes = DatabaseService.get_safety_changes_by_drug_id(db, d.id)
                    if changes:
                        report = scraper.extract_adverse_reactions_from_records(
                            drug_name=d.display_name,
                            active_ingredient=d.active_ingredient,
                            changes=changes,
                        )
                        if report.get("status") == "success":
                            db.close()
                            return report
            db.close()
        except Exception as e:
            logger.debug(f"DB fallback failed: {e}")

    return {
        "status": "no_data",
        "drug_name": query_clean,
        "message": "No data is present on adverse reaction",
        "formatted_report": "No data is present on adverse reaction",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract Adverse Reactions from FDA SrLC matching report format."
    )
    parser.add_argument("drug_name", nargs="?", help="Name of the drug (e.g. ARIKAYCE, Warfarin)")
    parser.add_argument("--url", help="Direct FDA SrLC detail URL or DrugNameID")
    parser.add_argument("--file", help="Path to local HTML fixture or detail file")
    parser.add_argument("--json", action="store_true", help="Output full JSON response")
    parser.add_argument("--no-db", action="store_true", help="Skip local DB and query FDA online")

    args = parser.parse_args()

    if not args.drug_name and not args.url and not args.file:
        parser.print_help()
        sys.exit(1)

    result = asyncio.run(
        fetch_and_extract_adverse_reactions(
            drug_name=args.drug_name,
            url=args.url,
            file_path=args.file,
            use_db=not args.no_db,
        )
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Output the formatted report text
        print(result.get("formatted_report", "No data is present on adverse reaction"))


if __name__ == "__main__":
    main()
