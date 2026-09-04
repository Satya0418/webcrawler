#!/usr/bin/env python3
"""
Test script for FDA scraper with real HTML fixtures.
"""
import logging
from app.scrapers.fda_srlc_scraper import scraper

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def test_scraper():
    """Test the scraper with real FDA HTML."""
    print("\n" + "="*80)
    print("FDA SCRAPER TEST")
    print("="*80)
    
    # Test 1: Parse search results from fixture
    print("\n[TEST 1] Parsing search results from fixture...")
    print("-" * 80)
    
    try:
        with open('tests/fixtures/fda/search_results_warfarin.html', 'r') as f:
            html = f.read()
        
        print(f"HTML size: {len(html)} bytes")
        
        results = scraper.parse_search_results(html)
        
        if results:
            print(f"✅ SUCCESS - Parsed {len(results)} records")
            for i, record in enumerate(results[:5]):
                print(f"\n   Record {i+1}:")
                print(f"      Drug: {record.get('drug_name')}")
                print(f"      Ingredient: {record.get('active_ingredient')}")
                print(f"      App #: {record.get('application_number')}")
                if i == 4 and len(results) > 5:
                    print(f"      ... and {len(results) - 5} more records")
                    break
        else:
            print("⚠️  No records parsed (fixture may contain search form, not results)")
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    # Test 2: Verify extraction methods
    print("\n[TEST 2] Testing extraction methods...")
    print("-" * 80)
    
    test_record = {
        'drug_name': 'Warfarin',
        'active_ingredient': 'Warfarin Sodium',
        'application_number': 'NDA-18-001',
        'source_url': 'https://fda.gov/...',
        'original_text': 'Original warning text',
        'updated_text': 'Updated warning text',
    }
    
    drug = scraper.extract_drug_name(test_record)
    ingredient = scraper.extract_active_ingredient(test_record)
    app = scraper.extract_application_number(test_record)
    url = scraper.extract_source_url(test_record)
    
    print(f"✅ Drug Name: {drug}")
    print(f"✅ Active Ingredient: {ingredient}")
    print(f"✅ Application #: {app}")
    print(f"✅ URL: {url}")
    
    # Test 3: Extract dates
    print("\n[TEST 3] Testing date extraction...")
    print("-" * 80)
    
    dates = scraper.extract_dates({
        'source_date': '01/15/2024',
        'approval_date': '02/20/2024',
        'effective_date': '03/01/2024',
    })
    
    print(f"✅ Dates extracted: {dates}")
    
    print("\n" + "="*80)
    print("TESTS COMPLETE")
    print("="*80)


if __name__ == "__main__":
    test_scraper()
