#!/usr/bin/env python3
"""
Test script for enhanced FDA crawler with browser headers.
Verifies that the crawler can connect to FDA without 403 errors.
"""
import asyncio
import logging
from app.crawler.fda_crawler import crawler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Test the enhanced crawler."""
    print("\n" + "="*80)
    print("ENHANCED FDA CRAWLER TEST")
    print("="*80)
    
    # Test 1: Get main page
    print("\n[TEST 1] Fetching main FDA SrLC page...")
    print("-" * 80)
    main_page = await crawler.get_main_page()
    
    if main_page:
        print(f"✅ SUCCESS - Received {len(main_page)} bytes")
        print(f"   Response contains 'Drug Safety': {'Drug Safety' in main_page}")
    else:
        print("❌ FAILED - Could not fetch main page")
    
    # Reset for next test
    crawler.reset_visited()
    
    # Test 2: Search for a drug
    print("\n[TEST 2] Searching for 'warfarin'...")
    print("-" * 80)
    search_results = await crawler.search_drug("warfarin")
    
    if search_results:
        print(f"✅ SUCCESS - Received {len(search_results)} bytes")
        print(f"   Response length: {len(search_results)} characters")
    else:
        print("❌ FAILED - Could not search for drug")
    
    # Test 3: Verify headers
    print("\n[TEST 3] Verifying crawler configuration...")
    print("-" * 80)
    print(f"✅ Base URL: {crawler.base_url}")
    print(f"✅ Timeout: {crawler.timeout}s")
    print(f"✅ Max retries: {crawler.max_retries}")
    print(f"✅ Backoff factor: {crawler.backoff_factor}")
    print(f"✅ Headers configured: {len(crawler.headers)} headers")
    print(f"   - User-Agent: {crawler.headers['User-Agent'][:50]}...")
    print(f"   - Accept: {crawler.headers['Accept'][:50]}...")
    
    # Test 4: URL tracking
    print("\n[TEST 4] URL tracking...")
    print("-" * 80)
    visited = crawler.get_visited_count()
    print(f"✅ Visited URLs: {visited}")
    
    print("\n" + "="*80)
    print("TESTS COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
