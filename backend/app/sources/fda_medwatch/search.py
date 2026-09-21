"""
FDA MedWatch Search Client.
Coordinates multi-source search across MedWatch articles, openFDA label records,
FAERS adverse event signals, and product recalls.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
import httpx

from app.sources.fda_medwatch.article_discovery import FDAMedWatchArticleDiscovery
from app.sources.fda_medwatch.config import (
    CONNECT_TIMEOUT,
    DEFAULT_HEADERS,
    DEFAULT_TIMEOUT,
    OPENFDA_ENFORCEMENT_URL,
    OPENFDA_EVENT_URL,
    OPENFDA_LABEL_URL,
)
from app.sources.fda_medwatch.models import MedWatchArticle

logger = logging.getLogger(__name__)


class FDAMedWatchSearch:
    """Coordinates search for medicine safety information across FDA MedWatch sources."""

    def __init__(
        self,
        article_discovery: Optional[FDAMedWatchArticleDiscovery] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.article_discovery = article_discovery or FDAMedWatchArticleDiscovery(timeout=timeout)
        self.timeout = timeout

    async def fetch_openfda_drug_metadata(self, query: str) -> Dict[str, Any]:
        """Queries openFDA label endpoint to get official application number and active ingredient."""
        out = {"brand_name": query.upper(), "active_ingredient": "", "application_number": "", "sponsor": ""}
        if not query:
            return out

        try:
            url = f"{OPENFDA_LABEL_URL}?search=openfda.brand_name:{quote_plus(query)}+openfda.generic_name:{quote_plus(query)}&limit=1"
            async with httpx.AsyncClient(
                headers={"User-Agent": "curl/8.7.1"},
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        r0 = results[0]
                        openfda = r0.get("openfda", {})
                        b_names = openfda.get("brand_name", [])
                        g_names = openfda.get("generic_name", [])
                        app_nums = openfda.get("application_number", [])
                        m_names = openfda.get("manufacturer_name", [])

                        if b_names:
                            out["brand_name"] = b_names[0].upper()
                        if g_names:
                            out["active_ingredient"] = g_names[0].upper()
                        if app_nums:
                            out["application_number"] = app_nums[0]
                        if m_names:
                            out["sponsor"] = m_names[0]
        except Exception as exc:
            logger.debug("openFDA drug label query error for '%s': %s", query, exc)

        return out

    async def fetch_openfda_recalls(self, query: str) -> List[Dict[str, Any]]:
        """Queries openFDA drug recall enforcement notices."""
        recalls = []
        if not query:
            return recalls
        try:
            url = f"{OPENFDA_ENFORCEMENT_URL}?search=product_description:{quote_plus(query)}&limit=2"
            async with httpx.AsyncClient(
                headers={"User-Agent": "curl/8.7.1"},
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("results", []):
                        recalls.append({
                            "recall_number": r.get("recall_number", "FDA-RECALL"),
                            "classification": r.get("classification", "Class II"),
                            "reason": r.get("reason_for_recall", "Safety concern"),
                            "firm": r.get("recalling_firm", "Manufacturer"),
                            "date": r.get("recall_initiation_date", ""),
                        })
        except Exception as exc:
            logger.debug("openFDA recall query error: %s", exc)
        return recalls

    async def fetch_openfda_events(self, query: str) -> List[Dict[str, Any]]:
        """Queries openFDA FAERS adverse event signals."""
        events = []
        if not query:
            return events
        try:
            url = f"{OPENFDA_EVENT_URL}?search=patient.drug.medicinalproduct:{quote_plus(query)}&limit=2"
            async with httpx.AsyncClient(
                headers={"User-Agent": "curl/8.7.1"},
                timeout=httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT, read=self.timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("results", []):
                        pt = r.get("patient", {})
                        rx = [x.get("reactionmeddrapt", "") for x in pt.get("reaction", []) if x.get("reactionmeddrapt")]
                        events.append({
                            "report_id": r.get("safetyreportid", ""),
                            "reactions": rx[:4],
                            "date": r.get("receiptdate", ""),
                        })
        except Exception as exc:
            logger.debug("openFDA FAERS event query error: %s", exc)
        return events
