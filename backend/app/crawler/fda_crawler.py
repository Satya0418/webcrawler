"""
FDA SrLC Web Crawler.
Responsible for fetching pages from the FDA SrLC database.
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional, Set, Dict, Any
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class FDACrawler:
    """Crawler for FDA SrLC database."""

    def __init__(self):
        self.base_url = settings.FDA_BASE_URL
        self.timeout = settings.FDA_CRAWL_TIMEOUT
        self.max_retries = settings.FDA_CRAWL_RETRIES
        self.backoff_factor = settings.FDA_CRAWL_BACKOFF_FACTOR
        self.visited_urls: Set[str] = set()
        
        # Browser-like headers to avoid 403 errors
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': f'{self.base_url}/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    async def search_drug(self, drug_name: str) -> Optional[str]:
        """
        Search for a drug by name or active ingredient using POST.

        Args:
            drug_name: Medicine name or active ingredient

        Returns:
            HTML response content or None if failed
        """
        try:
            # FDA search uses POST to results page with TextSearch parameter
            search_url = f"{self.base_url}/index.cfm?event=searchResult.page"
            search_data = {
                "drug_name": drug_name,
                "TextSearch": "Search"
            }

            logger.info(f"Starting search for drug: {drug_name}")
            
            # Use session-based client to maintain cookies
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                # Log the request
                logger.debug(f"POST to {search_url} with data: {search_data}")
                
                response = await client.post(search_url, data=search_data)
                response.raise_for_status()

                self.visited_urls.add(search_url)
                logger.info(f"✓ Search successful for '{drug_name}' - received {len(response.text)} bytes")
                return response.text

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code} error searching for '{drug_name}': {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error searching for '{drug_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error searching for '{drug_name}': {e}")
            return None

    async def get_page(self, url: str) -> Optional[str]:
        """
        Fetch a single page from FDA with retry logic.

        Args:
            url: Full URL to fetch

        Returns:
            HTML response content or None if failed
        """
        if url in self.visited_urls:
            logger.debug(f"URL already visited: {url}")
            return None

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})")
                
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    headers=self.headers,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    self.visited_urls.add(url)
                    logger.info(f"✓ Successfully crawled: {url} - {len(response.text)} bytes")
                    return response.text

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden on {url} (attempt {attempt + 1})")
                    # Wait before retry
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt * self.backoff_factor
                        logger.debug(f"Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"HTTP {e.response.status_code} error on {url}: {e}")
                    return None
                    
            except httpx.RequestError as e:
                logger.warning(f"Request error on {url} (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt * self.backoff_factor
                    await asyncio.sleep(wait_time)
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {e}")
                return None

        logger.error(f"Failed to fetch {url} after {self.max_retries} attempts")
        return None

    async def get_main_page(self) -> Optional[str]:
        """
        Fetch the main FDA SrLC page.

        Returns:
            HTML response content or None if failed
        """
        main_url = self.base_url
        return await self.get_page(main_url)

    async def get_detail_page(self, url_or_path: str) -> Optional[str]:
        """
        Fetch a drug detail page from FDA.

        Args:
            url_or_path: Full URL or relative path/DrugNameID

        Returns:
            HTML response content or None if failed
        """
        if url_or_path.startswith("http"):
            full_url = url_or_path
        elif url_or_path.startswith("/"):
            full_url = f"https://www.accessdata.fda.gov{url_or_path}"
        elif "DrugNameID=" in url_or_path:
            full_url = f"{self.base_url}/index.cfm?event=searchdetail.page&{url_or_path}"
        else:
            full_url = f"{self.base_url}/index.cfm?event=searchdetail.page&DrugNameID={url_or_path}"

        logger.info(f"Fetching detail page: {full_url}")
        return await self.get_page(full_url)

    def reset_visited(self):
        """Reset the visited URLs set."""
        self.visited_urls.clear()
        logger.info("Visited URLs cleared")

    def get_visited_count(self) -> int:
        """Get number of visited URLs."""
        return len(self.visited_urls)


# Create singleton instance
crawler = FDACrawler()
