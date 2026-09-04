#!/usr/bin/env python3
"""
Capture actual FDA search results page for detailed analysis.
"""
import asyncio
import logging
from app.crawler.fda_crawler import crawler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Capture search results HTML."""
    print("\n" + "="*80)
    print("CAPTURING ACTUAL FDA SEARCH RESULTS")
    print("="*80)
    
    # Search for warfarin
    print("\nSearching for 'warfarin'...")
    html = await crawler.search_drug("warfarin")
    
    if html:
        print(f"✓ Received {len(html)} bytes")
        
        # Save to fixture
        fixture_path = "tests/fixtures/fda/search_results_warfarin_post.html"
        with open(fixture_path, 'w') as f:
            f.write(html)
        
        print(f"✓ Saved to {fixture_path}")
        
        # Analyze structure
        print("\nAnalyzing HTML structure...")
        print(f"  - Contains '<table': {('<table' in html)}")
        print(f"  - Contains 'tbody': {('tbody' in html)}")
        print(f"  - Contains 'warfarin': {('warfarin' in html.lower())}")
        print(f"  - Contains 'drug': {('drug' in html.lower())}")
        print(f"  - Contains 'results': {('results' in html.lower())}")
        
        # Look for specific patterns
        import re
        
        # Look for result patterns
        links = re.findall(r'href=["\']([^"\']*)["\']', html)[:10]
        print(f"  - Found {len(re.findall(r'href=', html))} links")
        print(f"  - First 5 links: {links}")
        
        # Look for drug names
        drug_names = re.findall(r'drug[_-]?name', html, re.IGNORECASE)
        print(f"  - 'drug_name' mentions: {len(drug_names)}")
        
    else:
        print("❌ Failed to fetch search results")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(main())
