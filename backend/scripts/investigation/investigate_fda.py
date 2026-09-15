#!/usr/bin/env python3
"""
FDA SrLC Investigation Script

This script investigates the actual FDA Drug Safety-related Labeling Changes website
to understand the structure of search results and detail pages.

Run: python investigate_fda.py
"""

import asyncio
import httpx
import json
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Configuration
FDA_BASE_URL = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges"
TIMEOUT = 30
OUTPUT_DIR = Path("tests/fixtures/fda")

# Create output directory if it doesn't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def fetch_page(url: str, params: dict = None) -> str:
    """Fetch a page from FDA."""
    print(f"\n{'='*80}")
    print(f"Fetching: {url}")
    if params:
        print(f"Params: {params}")
    print('='*80)
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            print(f"✓ Status: {response.status_code}")
            print(f"✓ Content length: {len(response.text)} bytes")
            return response.text
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def analyze_html(html_content: str, name: str) -> dict:
    """Analyze HTML structure."""
    print(f"\n{'─'*80}")
    print(f"Analyzing: {name}")
    print('─'*80)
    
    soup = BeautifulSoup(html_content, "lxml")
    
    analysis = {
        "name": name,
        "page_title": soup.title.string if soup.title else None,
        "has_forms": len(soup.find_all("form")) > 0,
        "forms_found": len(soup.find_all("form")),
        "has_tables": len(soup.find_all("table")) > 0,
        "tables_found": len(soup.find_all("table")),
        "has_javascript": len(soup.find_all("script")) > 0,
        "scripts_found": len(soup.find_all("script")),
        "has_links": len(soup.find_all("a")) > 0,
        "links_found": len(soup.find_all("a")),
    }
    
    print(f"Title: {analysis['page_title']}")
    print(f"Forms: {analysis['forms_found']}")
    print(f"Tables: {analysis['tables_found']}")
    print(f"Scripts: {analysis['scripts_found']}")
    print(f"Links: {analysis['links_found']}")
    
    # Analyze first form if exists
    if soup.find("form"):
        form = soup.find("form")
        print(f"\nFirst Form:")
        print(f"  Action: {form.get('action')}")
        print(f"  Method: {form.get('method', 'GET')}")
        print(f"  Input fields:")
        for inp in form.find_all("input"):
            print(f"    - {inp.get('name')}: type={inp.get('type')}, value={inp.get('value')}")
    
    # Analyze first table if exists
    if soup.find("table"):
        table = soup.find("table")
        print(f"\nFirst Table:")
        print(f"  Headers: {len(table.find_all('th'))} columns")
        headers = [h.get_text(strip=True) for h in table.find_all('th')[:5]]
        print(f"  First headers: {headers}")
        rows = table.find_all('tr')
        print(f"  Rows: {len(rows)} total")
        if len(rows) > 1:
            print(f"  First data row cells: {len(rows[1].find_all('td'))}")
    
    return analysis


def save_html(html_content: str, filename: str):
    """Save HTML to file."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✓ Saved to: {filepath}")


async def investigate_search():
    """Investigate FDA search functionality."""
    print("\n" + "="*80)
    print("STEP 1: INVESTIGATING FDA SrLC SEARCH")
    print("="*80)
    
    # Fetch the main page
    main_page = await fetch_page(f"{FDA_BASE_URL}/index.cfm")
    if main_page:
        save_html(main_page, "search_page.html")
        analyze_html(main_page, "Main Search Page")
    
    # Try a search for warfarin using POST (FDA form uses POST to results page)
    print("\n" + "="*80)
    print("STEP 2: SEARCHING FOR 'WARFARIN' (POST to results page)")
    print("="*80)
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            # The form posts to this endpoint
            result_url = f"{FDA_BASE_URL}/index.cfm?event=searchResult.page"
            print(f"\nFetching: {result_url}")
            print(f"Method: POST")
            print(f"Data: drug_name=warfarin")
            print(f"(Following redirects)")
            
            response = await client.post(
                result_url,
                data={"drug_name": "warfarin"}
            )
            response.raise_for_status()
            print(f"✓ Status: {response.status_code}")
            print(f"✓ Content length: {len(response.text)} bytes")
            print(f"✓ Final URL: {response.url}")
            search_results = response.text
    except Exception as e:
        print(f"✗ Error: {e}")
        search_results = None
    
    if search_results:
        save_html(search_results, "search_results_warfarin.html")
        analysis = analyze_html(search_results, "Warfarin Search Results")
        
        # Extract links from results
        soup = BeautifulSoup(search_results, "lxml")
        result_links = []
        
        # Look for result links (usually in tables or divs)
        for link in soup.find_all("a"):
            href = link.get("href")
            text = link.get_text(strip=True)
            
            # Filter for likely result links
            if href and ("?id=" in href or "?nda=" in href or "detail" in href.lower()):
                result_links.append({
                    "text": text,
                    "href": href,
                    "full_url": urljoin(FDA_BASE_URL, href)
                })
        
        print(f"\nFound {len(result_links)} potential result links:")
        for i, link in enumerate(result_links[:5]):  # Show first 5
            print(f"\n  [{i+1}] Text: {link['text']}")
            print(f"      Href: {link['href']}")
            print(f"      Full: {link['full_url']}")
        
        # Try to follow the first result if found
        if result_links:
            print("\n" + "="*80)
            print("STEP 3: EXAMINING FIRST SEARCH RESULT DETAIL PAGE")
            print("="*80)
            
            first_link = result_links[0]
            detail_page = await fetch_page(first_link["full_url"])
            
            if detail_page:
                save_html(detail_page, "search_result_detail.html")
                analyze_html(detail_page, "Detail Page")
                
                # Look for safety information
                soup_detail = BeautifulSoup(detail_page, "lxml")
                safety_sections = soup_detail.find_all(
                    ["section", "article", "div"],
                    {"class": ["content", "safety", "detail"]}
                )
                
                print(f"\nFound {len(safety_sections)} potential content sections")


async def investigate_date_search():
    """Investigate date-based search."""
    print("\n" + "="*80)
    print("STEP 4: INVESTIGATING DATE SEARCH")
    print("="*80)
    
    # Try a date range search
    date_search = await fetch_page(
        f"{FDA_BASE_URL}/index.cfm",
        params={
            "StartDate": "01/01/2026",
            "EndDate": "09/03/2026",
        }
    )
    
    if date_search:
        save_html(date_search, "search_results_date.html")
        analyze_html(date_search, "Date Range Search Results")


async def check_robots_txt():
    """Check FDA robots.txt."""
    print("\n" + "="*80)
    print("STEP 5: CHECKING ROBOTS.TXT")
    print("="*80)
    
    robots_url = "https://www.accessdata.fda.gov/robots.txt"
    print(f"Checking: {robots_url}")
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(robots_url)
            if response.status_code == 200:
                print(f"✓ Found robots.txt")
                # Show relevant sections
                lines = response.text.split('\n')
                for line in lines[:20]:  # First 20 lines
                    if line.strip():
                        print(f"  {line}")
            else:
                print(f"✗ Status: {response.status_code}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def main():
    """Run investigation."""
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "FDA SrLC WEBSITE INVESTIGATION".center(78) + "║")
    print("║" + "Understanding Search & Data Structure".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝")
    
    # Run investigations
    await investigate_search()
    await investigate_date_search()
    await check_robots_txt()
    
    print("\n" + "="*80)
    print("INVESTIGATION COMPLETE")
    print("="*80)
    print(f"\nHTML samples saved to: {OUTPUT_DIR}")
    print("\nNext steps:")
    print("1. Review the saved HTML files in tests/fixtures/fda/")
    print("2. Identify the HTML selectors for:")
    print("   - Search result table/list")
    print("   - Drug name field")
    print("   - Safety change date field")
    print("   - Links to detail pages")
    print("   - Detail page structure")
    print("3. Update app/scrapers/fda_srlc_scraper.py with actual parsers")
    print("4. Create regression tests with these fixtures")


if __name__ == "__main__":
    asyncio.run(main())
