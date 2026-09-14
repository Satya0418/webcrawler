"""
Health Canada Drug Product Database (DPD) & MedEffect Safety Alerts Crawler.

Provides live medicine searching on the official Health Canada database:
- Drug Product Database (DPD) API for brand name, DIN, active ingredients,
  manufacturer, dosage form, route, and official Product Monograph PDF links.
- Health Canada Recalls and Safety Alerts for safety advisories, warnings,
  and adverse reaction alerts.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup
import httpx

from app.services.normalization import NormalizationService

logger = logging.getLogger(__name__)

# Base URLs
DPD_API_BASE = "https://health-products.canada.ca/api/drug"
DPD_WEB_BASE = "https://health-products.canada.ca/dpd-bdpp"
RECALLS_BASE = "https://recalls-rappels.canada.ca"

SOURCE_ID = "HEALTH_CANADA"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
}


class HealthCanadaDPDCrawler:
    """Crawler and extractor for Health Canada official medicine data."""

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout
        self.headers = DEFAULT_HEADERS

    async def search_medicine(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Health Canada for a medicine by brand name, generic name, or DIN.

        Returns a list of structured drug records with safety labeling changes:
        [
            {
                "display_name": "OZEMPIC",
                "normalized_name": "ozempic",
                "active_ingredient": "SEMAGLUTIDE 1.34 MG/ML",
                "application_number": "02471469",
                "source": "HEALTH_CANADA",
                "company_name": "NOVO NORDISK CANADA INC",
                "safety_changes": [...],
            },
            ...
        ]
        """
        q = (query or "").strip()
        if not q or len(q) < 2:
            return []

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # 1. Query DPD by brand name
                products = await self._query_dpd_products(client, q)

                # 2. Concurrently query Health Canada safety recalls / advisories
                recalls_task = asyncio.create_task(self._query_safety_recalls(client, q))

                results: List[Dict[str, Any]] = []

                # Process up to top 5 distinct products to ensure fast response
                seen_dins = set()
                selected_products = []
                for p in products:
                    din = str(p.get("drug_identification_number") or "").strip()
                    if din and din in seen_dins:
                        continue
                    if din:
                        seen_dins.add(din)
                    selected_products.append(p)
                    if len(selected_products) >= 5:
                        break

                # Fetch details for each product
                for p in selected_products:
                    drug_code = p.get("drug_code")
                    brand_name = p.get("brand_name") or q.upper()
                    din = p.get("drug_identification_number") or ""
                    company = p.get("company_name") or ""
                    last_update = p.get("last_update_date")

                    # Concurrently fetch ingredient, status, form, route, and monograph link
                    details = await self._fetch_product_details(client, drug_code)

                    active_ingr = details.get("active_ingredient") or ""
                    form = details.get("form") or ""
                    route = details.get("route") or ""
                    status = details.get("status") or "Marketed"
                    status_date = details.get("status_date") or last_update
                    pm_url = details.get("monograph_url") or f"{DPD_WEB_BASE}/info?lang=eng&code={drug_code}"

                    safety_changes: List[Dict[str, Any]] = []

                    # Add Canadian Product Monograph safety change
                    monograph_text_parts = [
                        f"Health Canada Product Monograph for {brand_name}.",
                        f"Drug Identification Number (DIN): {din}",
                        f"Manufacturer / Sponsor: {company}",
                        f"Active Ingredient(s): {active_ingr}",
                        f"Dosage Form: {form}",
                        f"Route of Administration: {route}",
                        f"Regulatory Status: {status} (as of {status_date})",
                    ]
                    if pm_url and pm_url.endswith(".PDF"):
                        monograph_text_parts.append(f"Official Product Monograph Document: {pm_url}")

                    monograph_text = "\n\n".join(monograph_text_parts)
                    rec_id = hashlib.sha256(f"{din}|{brand_name}|monograph".encode()).hexdigest()[:32]

                    safety_changes.append({
                        "source": SOURCE_ID,
                        "source_record_id": rec_id,
                        "display_name": brand_name,
                        "normalized_name": NormalizationService.normalize_drug_name(brand_name),
                        "active_ingredient": active_ingr,
                        "section": "Product Monograph Update",
                        "change_type": "Health Canada Authorized Monograph",
                        "source_date": str(status_date) if status_date else None,
                        "source_url": pm_url,
                        "original_text": f"DIN {din} - {company}",
                        "updated_text": monograph_text,
                        "fda_comment": f"Health Canada DPD — DIN {din} ({status})",
                    })

                    results.append({
                        "display_name": brand_name,
                        "normalized_name": NormalizationService.normalize_drug_name(brand_name),
                        "active_ingredient": active_ingr,
                        "application_number": din,
                        "source": SOURCE_ID,
                        "company_name": company,
                        "safety_changes": safety_changes,
                    })

                # Await safety recalls and attach to results or create a safety advisory entry
                try:
                    recalls = await recalls_task
                    if recalls:
                        for recall in recalls:
                            recall_title = recall.get("title") or f"Health Canada Safety Alert: {q}"
                            recall_url = recall.get("url") or RECALLS_BASE
                            recall_date = recall.get("date")
                            recall_desc = recall.get("desc") or recall_title

                            rec_id = hashlib.sha256(f"{recall_url}|{recall_title}".encode()).hexdigest()[:32]
                            recall_change = {
                                "source": SOURCE_ID,
                                "source_record_id": rec_id,
                                "display_name": results[0]["display_name"] if results else q.capitalize(),
                                "normalized_name": NormalizationService.normalize_drug_name(results[0]["display_name"] if results else q),
                                "active_ingredient": results[0]["active_ingredient"] if results else None,
                                "section": "Adverse Reaction Information",
                                "change_type": "Health Canada Safety Alert / Recall",
                                "source_date": recall_date,
                                "source_url": recall_url,
                                "original_text": recall_title,
                                "updated_text": f"{recall_title}\n\n{recall_desc}",
                                "fda_comment": f"Health Canada MedEffect Alert — {recall_title}",
                            }

                            if results:
                                results[0]["safety_changes"].append(recall_change)
                            else:
                                # If no DPD record was found but a recall exists
                                results.append({
                                    "display_name": q.capitalize(),
                                    "normalized_name": NormalizationService.normalize_drug_name(q),
                                    "active_ingredient": None,
                                    "application_number": None,
                                    "source": SOURCE_ID,
                                    "safety_changes": [recall_change],
                                })
                except Exception as exc:
                    logger.warning("Error awaiting safety recalls for '%s': %s", q, exc)

                return results
        except Exception as exc:
            logger.error("Error searching Health Canada DPD for '%s': %s", q, exc)
            return []

    async def _query_dpd_products(
        self,
        client: httpx.AsyncClient,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Query DPD API by brand name, DIN, or active ingredient."""
        # 1. Try brand name search
        url = f"{DPD_API_BASE}/drugproduct/?brandname={quote_plus(query)}"
        try:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    return data
        except Exception as e:
            logger.warning("DPD brand name query error for '%s': %s", query, e)

        # 2. If query is numeric, try DIN search
        clean_din = re.sub(r"\D", "", query)
        if clean_din and len(clean_din) >= 4:
            url_din = f"{DPD_API_BASE}/drugproduct/?din={clean_din}"
            try:
                r_din = await client.get(url_din)
                if r_din.status_code == 200:
                    data = r_din.json()
                    if isinstance(data, list) and data:
                        return data
            except Exception:
                pass

        return []

    async def _fetch_product_details(
        self,
        client: httpx.AsyncClient,
        drug_code: Optional[int],
    ) -> Dict[str, Any]:
        """Fetch active ingredients, status, form, route, and monograph link."""
        if not drug_code:
            return {}

        details: Dict[str, Any] = {
            "active_ingredient": "",
            "status": "Marketed",
            "status_date": None,
            "form": "",
            "route": "",
            "monograph_url": None,
        }

        # Concurrently request related DPD endpoints and monograph page
        ai_url = f"{DPD_API_BASE}/activeingredient/?id={drug_code}"
        st_url = f"{DPD_API_BASE}/status/?id={drug_code}"
        fm_url = f"{DPD_API_BASE}/form/?id={drug_code}"
        rt_url = f"{DPD_API_BASE}/route/?id={drug_code}"
        web_url = f"{DPD_WEB_BASE}/info?lang=eng&code={drug_code}"

        async def _get_json(url: str) -> Any:
            try:
                res = await client.get(url)
                return res.json() if res.status_code == 200 else None
            except Exception:
                return None

        async def _get_monograph(url: str) -> Optional[str]:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "pdf.hres.ca/dpd_pm/" in href:
                            return href
                        if "Product monograph" in a.get_text():
                            return urljoin(url, href)
            except Exception:
                pass
            return None

        ai_res, st_res, fm_res, rt_res, pm_res = await asyncio.gather(
            _get_json(ai_url),
            _get_json(st_url),
            _get_json(fm_url),
            _get_json(rt_url),
            _get_monograph(web_url),
            return_exceptions=True,
        )

        # Parse active ingredients
        if isinstance(ai_res, list) and ai_res:
            ais = []
            for item in ai_res:
                ingr = item.get("ingredient_name", "").strip()
                strength = item.get("strength", "").strip()
                unit = item.get("strength_unit", "").strip()
                dosage_unit = item.get("dosage_unit", "").strip()
                strength_str = f"{strength} {unit}".strip()
                if dosage_unit:
                    strength_str = f"{strength_str}/{dosage_unit}".strip()
                ais.append(f"{ingr} {strength_str}".strip() if strength_str else ingr)
            details["active_ingredient"] = "; ".join(filter(None, ais))

        # Parse status
        if isinstance(st_res, dict):
            details["status"] = st_res.get("status") or "Marketed"
            details["status_date"] = st_res.get("history_date") or st_res.get("original_market_date")

        # Parse form
        if isinstance(fm_res, list) and fm_res:
            forms = [f.get("pharmaceutical_form_name", "").strip() for f in fm_res if f.get("pharmaceutical_form_name")]
            details["form"] = ", ".join(filter(None, forms))

        # Parse route
        if isinstance(rt_res, list) and rt_res:
            routes = [r.get("route_of_administration_name", "").strip() for r in rt_res if r.get("route_of_administration_name")]
            details["route"] = ", ".join(filter(None, routes))

        # Monograph URL
        if isinstance(pm_res, str) and pm_res:
            details["monograph_url"] = pm_res

        return details

    async def _query_safety_recalls(
        self,
        client: httpx.AsyncClient,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Query Health Canada Recalls and Safety Alerts for medicine safety advisories."""
        url = f"{RECALLS_BASE}/en/search/site?search_api_fulltext={quote_plus(query)}&f%5B0%5D=cat%3A180"
        recalls: List[Dict[str, Any]] = []
        try:
            r = await client.get(url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                rows = soup.find_all(
                    ["article", "div"],
                    class_=lambda c: c and ("search-result" in c or "views-row" in c),
                )
                for row in rows[:5]:
                    h = row.find(["h3", "h2", "a"])
                    a_tag = row.find("a", href=True)
                    date_tag = row.find(class_=lambda c: c and ("date" in c or "time" in c))
                    desc_tag = row.find(class_=lambda c: c and ("snippet" in c or "body" in c or "summary" in c))
                    if h and a_tag:
                        link = a_tag["href"]
                        if not link.startswith("http"):
                            link = urljoin(RECALLS_BASE, link)
                        recalls.append({
                            "title": h.get_text(strip=True),
                            "url": link,
                            "date": date_tag.get_text(strip=True) if date_tag else None,
                            "desc": desc_tag.get_text(strip=True) if desc_tag else None,
                        })
        except Exception as e:
            logger.debug("Recalls search error for '%s': %s", query, e)
        return recalls


dpd_crawler = HealthCanadaDPDCrawler()
