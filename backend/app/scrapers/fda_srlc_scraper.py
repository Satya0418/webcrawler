"""
FDA SrLC Web Scraper.
Responsible for parsing HTML responses and extracting structured data with faithful formatting.
"""
import logging
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def clean_element_formatted_text(elem) -> str:
    """
    Extract clean, well-formatted text from an HTML element.
    Preserves bullet points (•), paragraph breaks, and subsection headers.
    """
    if not elem:
        return ""

    soup = BeautifulSoup(str(elem), "lxml")

    # Replace list items with clean bullet lines
    for li in soup.find_all("li"):
        t = re.sub(r"[ \t\n\r]+", " ", li.get_text()).strip()
        if t:
            li.replace_with(f"\n• {t}")
        else:
            li.unwrap()

    # Preserve paragraph and block linebreaks
    for p in soup.find_all(["p", "div", "h4", "h5", "blockquote"]):
        p.insert_before("\n\n")
        p.unwrap()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    text = soup.get_text()

    # Clean whitespace while preserving line structure
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    result = []
    blank = False
    for line in lines:
        if line:
            result.append(line)
            blank = False
        elif not blank:
            result.append("")
            blank = True

    return "\n".join(result).strip()


class FDASrLCScraper:
    """Parser for FDA SrLC HTML responses."""

    def __init__(self):
        self.parser = "lxml"
        self.base_url = "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges"

    def parse_search_results(self, html_content: str, source_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parse search results from FDA SrLC response.

        Args:
            html_content: HTML response from search
            source_url: Source URL of the search

        Returns:
            List of extracted drug records
        """
        if not html_content:
            logger.error("Empty HTML content provided to parse_search_results")
            return []

        try:
            soup = BeautifulSoup(html_content, self.parser)
            records = []

            # Look for tables containing results
            tables = soup.find_all("table")
            for table in tables:
                headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
                if any("drug name" in h for h in headers) and any("active ingredient" in h or "application" in h for h in headers):
                    rows = table.find_all("tr")
                    for row in rows:
                        cells = row.find_all("td")
                        if not cells:
                            continue

                        cell_texts = [c.get_text(strip=True) for c in cells]
                        if len(cell_texts) >= 3:
                            drug_name = cell_texts[0]
                            active_ingredient = cell_texts[1] if len(cell_texts) > 1 else None
                            app_num = cell_texts[2] if len(cell_texts) > 2 else None
                            app_type = cell_texts[3] if len(cell_texts) > 3 else None
                            supp_date = cell_texts[4] if len(cell_texts) > 4 else None
                            updated_date = cell_texts[5] if len(cell_texts) > 5 else None

                            detail_url = None
                            link_elem = cells[0].find("a")
                            if link_elem and link_elem.get("href"):
                                href = link_elem["href"]
                                detail_url = urljoin(self.base_url + "/", href)
                            elif len(cells) > 6:
                                link_text = cells[6].get_text(strip=True)
                                if link_text.startswith("http"):
                                    detail_url = link_text

                            full_app_num = f"{app_type}-{app_num}" if app_type and app_num and not app_num.startswith(app_type) else app_num

                            record = {
                                "drug_name": drug_name,
                                "display_name": drug_name,
                                "active_ingredient": active_ingredient,
                                "application_number": full_app_num,
                                "source_date": supp_date,
                                "database_updated": updated_date,
                                "detail_url": detail_url,
                                "source_url": detail_url or source_url or self.base_url,
                                "source": "FDA_SRLC",
                            }
                            if drug_name:
                                records.append(record)

            # Fallback: Check autocomplete datalist if no table records found
            if not records:
                datalists = soup.find_all("datalist")
                for datalist in datalists:
                    for option in datalist.find_all("option"):
                        value = option.get("value", "").strip() or option.get_text(strip=True)
                        if ":" in value:
                            f_type, f_val = value.split(":", 1)
                            if f_type.strip().lower() == "drug name":
                                records.append({
                                    "drug_name": f_val.strip(),
                                    "display_name": f_val.strip(),
                                    "active_ingredient": None,
                                    "source": "autocomplete",
                                    "source_url": source_url or self.base_url,
                                })

            logger.info(f"Parsed {len(records)} records from search results")
            return records

        except Exception as e:
            logger.error(f"Error parsing search results: {e}", exc_info=True)
            return []

    def parse_detail_page(self, html_content: str, source_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Parse a detail page for a specific drug and all its safety changes across all supplements.

        Args:
            html_content: HTML response from detail page
            source_url: Source URL of detail page

        Returns:
            Extracted record data with safety changes or None if parsing failed
        """
        if not html_content:
            logger.error("Empty HTML content provided to parse_detail_page")
            return None

        try:
            soup = BeautifulSoup(html_content, self.parser)
            record: Dict[str, Any] = {
                "drug_name": None,
                "display_name": None,
                "active_ingredient": None,
                "application_number": None,
                "source_url": source_url,
                "source": "FDA_SRLC",
                "safety_changes": [],
            }

            # 1. Extract Drug Name & Application Number (e.g., ZYVOX (NDA-021132))
            for h in soup.find_all(["h2", "h3"]):
                text = h.get_text(strip=True)
                match = re.search(r"^([^\(]+?)\s*\(\s*([A-Za-z]+[\s\-]?\d+)\s*\)", text)
                if match:
                    record["drug_name"] = match.group(1).strip()
                    record["display_name"] = match.group(1).strip()
                    record["application_number"] = match.group(2).strip()
                    break

            if not record["drug_name"]:
                title_elem = soup.find(["h1", "h2", "h3"])
                if title_elem:
                    record["drug_name"] = title_elem.get_text(strip=True)
                    record["display_name"] = record["drug_name"]

            # 2. Extract Active Ingredient (e.g., (LINEZOLID))
            for h in soup.find_all(["h4", "h5"]):
                text = h.get_text(strip=True)
                if text.startswith("(") and text.endswith(")"):
                    record["active_ingredient"] = text.strip("() \t\n\r")
                    break

            # 3. Extract Safety Changes from Accordion
            accordion = soup.find("div", id="accordion") or soup.find("div", class_=lambda c: c and "accordion" in str(c))
            
            if accordion:
                headers = [h for h in accordion.find_all("h3") if re.search(r"\d{1,2}/\d{1,2}/\d{4}", h.get_text())]
                for header in headers:
                    header_text = header.get_text(strip=True)
                    date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", header_text)
                    suppl_match = re.search(r"\((SUPPL-[^\)]+)\)", header_text, re.IGNORECASE)

                    change_date = date_match.group(1) if date_match else None
                    suppl_id = suppl_match.group(1) if suppl_match else None

                    panel = header.find_next_sibling("div")
                    if not panel:
                        continue

                    # Look for Approved Drug Label (PDF) link
                    pdf_link = panel.find("a", href=re.compile(r"\.pdf", re.I))
                    pdf_url = pdf_link["href"].strip() if (pdf_link and pdf_link.get("href")) else None

                    # Iterate over each labeling section (h4)
                    h4_sections = panel.find_all("h4")
                    for h4 in h4_sections:
                        # Clean section title (e.g., "5 Warnings and Precautions", "6 Adverse Reactions")
                        raw_section = re.sub(r"\s+", " ", h4.get_text()).strip()

                        # Content is in the sibling div following h4
                        content_div = h4.find_next_sibling("div")
                        formatted_text = clean_element_formatted_text(content_div) if content_div else ""

                        # If there's an explicit original text split
                        original_text = None
                        updated_text = formatted_text
                        fda_comment = None

                        if pdf_url:
                            fda_comment = f"Approved Drug Label: {pdf_url}"

                        if "Original Text:" in formatted_text and "Updated Text:" in formatted_text:
                            parts = formatted_text.split("Updated Text:")
                            original_text = parts[0].replace("Original Text:", "").strip()
                            updated_text = parts[1].strip()

                        change_record = {
                            "section": raw_section,
                            "source_record_id": suppl_id or f"{record['drug_name']}-{change_date}",
                            "source_date": change_date,
                            "change_type": "Labeling Revision",
                            "original_text": original_text,
                            "updated_text": updated_text if updated_text else None,
                            "fda_comment": fda_comment,
                            "source_url": pdf_url or source_url or self.base_url,
                        }
                        record["safety_changes"].append(change_record)

            return record if (record.get("drug_name") or record.get("safety_changes")) else None

        except Exception as e:
            logger.error(f"Error parsing detail page: {e}", exc_info=True)
            return None

    def extract_drug_name(self, record: Dict[str, Any]) -> Optional[str]:
        """Extract drug/product name from record."""
        return record.get("drug_name") or record.get("display_name") or record.get("product_name")

    def extract_active_ingredient(self, record: Dict[str, Any]) -> Optional[str]:
        """Extract active ingredient from record."""
        return record.get("active_ingredient")

    def extract_application_number(self, record: Dict[str, Any]) -> Optional[str]:
        """Extract application number (NDA/BLA) from record."""
        return record.get("application_number") or record.get("nda") or record.get("bla")

    def extract_safety_section(self, record: Dict[str, Any]) -> Optional[str]:
        """Extract labeling section from record."""
        return record.get("section")

    def extract_dates(self, record: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Extract all relevant dates from record."""
        return {
            "source_date": record.get("source_date"),
            "approval_date": record.get("approval_date"),
            "effective_date": record.get("effective_date"),
        }

    def extract_text_fields(self, record: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """Extract original and updated text from record."""
        return {
            "original_text": record.get("original_text"),
            "updated_text": record.get("updated_text"),
            "fda_comment": record.get("fda_comment"),
        }

    def extract_source_url(self, record: Dict[str, Any]) -> Optional[str]:
        """Extract source URL from record."""
        return record.get("source_url")


# Create singleton instance
scraper = FDASrLCScraper()
