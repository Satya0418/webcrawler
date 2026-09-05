"""
FDA SrLC Web Scraper.
Responsible for parsing HTML responses and extracting structured data with faithful formatting.
"""
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_fda_date(date_str: Optional[Any]) -> Optional[datetime]:
    """
    Parse string or datetime to standard datetime object for accurate comparison and chronological sorting.
    Handles ISO, FDA MM/DD/YYYY, M/D/YYYY, text dates (e.g. 'June 25, 2026', '25-Jun-2026'), and timestamps.
    """
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str

    raw = str(date_str).strip()
    if not raw:
        return None

    # Search for date pattern anywhere in string
    date_regex = re.compile(
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\d{1,2}[-\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s]\d{2,4})",
        re.IGNORECASE,
    )
    m = date_regex.search(raw)
    target = m.group(1).strip() if m else raw

    # Strip supplement notes if present: e.g. "06/25/2026(SUPPL-25)" or "06/25/2026 (SUPPL-25)"
    target_clean = re.sub(r"\(SUPPL[^\)]*\)", "", target, flags=re.IGNORECASE).strip()
    date_part = target_clean.split(" ")[0].split("T")[0].strip()

    # Try standard formats on date_part
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%d-%B-%Y", "%b-%d-%Y", "%B-%d-%Y"):
        try:
            return datetime.strptime(date_part, fmt)
        except ValueError:
            pass

    # Try full target string on textual formats
    for fmt in (
        "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
        "%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d-%B-%Y"
    ):
        try:
            return datetime.strptime(target_clean, fmt)
        except ValueError:
            pass

    # Fallback to dateutil parser
    try:
        import dateutil.parser
        return dateutil.parser.parse(target_clean)
    except Exception:
        pass

    return None


def format_fda_date_to_report(date_str: Optional[Any]) -> Optional[str]:
    """
    Convert FDA dates (e.g., '12/05/2025', '2025-12-05', '06/25/2026', '6/5/2025')
    to standard medical report format: '05-Dec-2025' or '25-Jun-2026'.
    """
    dt = parse_fda_date(date_str)
    if dt:
        return dt.strftime("%d-%b-%Y")
    return str(date_str) if date_str else None


def clean_adverse_reaction_text(raw_text: str) -> str:
    """
    Filter and clean adverse reaction text according to report specifications:
    - Stops immediately if section 17 / PCI/PI/MG / Medication Guide appears.
    - Strips editorial meta text ('Additions and/or revisions underlined:', '...').
    - Removes cross-references in brackets like '[see Warnings and Precautions (5.5)]'.
    - Strips leading section numbering (e.g. '6.2 ').
    """
    if not raw_text:
        return ""

    # Cut off at section 17 / PCI / PI / MG / Patient Counseling Information / Medication Guide
    stop_regex = re.compile(
        r"(?i)(?:^|\n)\s*(?:17\b|17\s+17|PCI/PI/MG|Patient\s+Counseling\s+Information|MEDICATION\s+GUIDE|How\s+should\s+I\s+use)",
    )
    m = stop_regex.search(raw_text)
    if m:
        raw_text = raw_text[:m.start()]

    # Strip cross-references in brackets like "[see Warnings and Precautions (5.5)]" across multiple lines
    raw_text = re.sub(r"\s*\[\s*see\s+[^\]]+\]", "", raw_text, flags=re.IGNORECASE)

    # Normalize broken subsection headers that have accidental linebreaks
    raw_text = re.sub(r"(?i)\bPostmarketing\s*\n+\s*Experience\b", "Postmarketing Experience", raw_text)
    raw_text = re.sub(r"(?i)\bClinical\s*\n+\s*Trials?\s*\n+\s*Experience\b", "Clinical Trials Experience", raw_text)

    cleaned_blocks = []
    blocks = raw_text.split("\n\n")

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Skip ellipsis lines
        if block in ("...", "…") or re.match(r"^[\.\s…]+$", block):
            continue

        # Skip editorial / guidance lines
        if re.match(r"(?i)^(additions\s+and/or\s+revisions\s+underlined|newly\s+added|approved\s+drug\s+label)", block):
            continue

        # Clean individual lines in block
        lines = block.split("\n")
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check stop condition per line
            if re.match(r"(?i)^(17\b|17\s+17|PCI/PI/MG|Patient\s+Counseling|MEDICATION\s+GUIDE|How\s+should\s+I\s+use)", line):
                break

            if line in ("...", "…") or re.match(r"^[\.\s…]+$", line):
                continue
            if re.match(r"(?i)^(additions\s+and/or\s+revisions\s+underlined|newly\s+added)", line):
                continue

            # Strip section numbers from subheadings: "6.2 Postmarketing Experience" -> "Postmarketing Experience"
            line = re.sub(r"^\s*6\.\d+\s*", "", line)
            line = re.sub(r"^\s*6\s+Adverse\s+Reactions", "Adverse Reactions", line, flags=re.IGNORECASE)

            # Strip cross-references in brackets like "[see Warnings and Precautions (5.5)]"
            line = re.sub(r"\s*\[\s*see\s+[^\]]+\]", "", line, flags=re.IGNORECASE)

            cleaned_lines.append(line)

        if cleaned_lines:
            merged_lines = []
            curr = ""
            for line in cleaned_lines:
                is_bullet = line.startswith("•") or line.startswith("-") or line.startswith("*")
                is_heading = len(line) < 60 and ("Experience" in line or "Reactions" in line or "Trials" in line)
                is_disorder_start = bool(re.match(r"^[A-Z][a-zA-Z\s,\/]+:\s*", line))

                if is_bullet or is_heading:
                    if curr:
                        merged_lines.append(curr)
                        curr = ""
                    merged_lines.append(line)
                elif is_disorder_start:
                    if curr:
                        merged_lines.append(curr)
                    curr = line
                else:
                    if curr:
                        curr = f"{curr} {line}"
                    else:
                        curr = line
            if curr:
                merged_lines.append(curr)

            cleaned_blocks.append("\n\n".join(merged_lines))

    return "\n\n".join(cleaned_blocks).strip()


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
                for header in accordion.find_all("h3"):
                    header_text = header.get_text(strip=True)
                    dt_obj = parse_fda_date(header_text)
                    if not dt_obj:
                        date_match = re.search(
                            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
                            header_text,
                            re.IGNORECASE,
                        )
                        if date_match:
                            dt_obj = parse_fda_date(date_match.group(1))

                    if not dt_obj:
                        continue

                    change_date = dt_obj.strftime("%m/%d/%Y")
                    suppl_match = re.search(r"\((SUPPL-[^\)]+)\)", header_text, re.IGNORECASE)
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

                        # Collect all sibling elements up to the next h4
                        section_elements = []
                        for sib in h4.next_siblings:
                            if getattr(sib, "name", None) == "h4":
                                break
                            if getattr(sib, "name", None):
                                section_elements.append(sib)

                        elem_texts = [clean_element_formatted_text(elem) for elem in section_elements]
                        formatted_text = "\n\n".join([t for t in elem_texts if t]).strip()

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

                        # Clean adverse reactions text to prevent section 17 or editorial noise leakage
                        if "adverse reaction" in raw_section.lower() and updated_text:
                            updated_text = clean_adverse_reaction_text(updated_text)

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

    def extract_adverse_reactions_report(
        self,
        html_content: str,
        drug_name: Optional[str] = None,
        active_ingredient: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Extract only the latest Adverse Reactions labeling change for a drug matching the
        reporting standard:
        1. Checks all dates/supplements in the accordion, ordered chronologically (newest first).
        2. Finds the most recent date in which Adverse Reactions is present.
        3. Strips section 17 PCI/PI/MG, 'Additions and/or revisions underlined', '...',
           and bracketed cross-references.
        4. Formats the date as DD-Mon-YYYY (e.g. 05-Dec-2025).
        5. If no Adverse Reactions found in any date, returns status 'no_data' with message
           'No data is present on adverse reaction'.
        """
        if not html_content:
            return {
                "status": "no_data",
                "drug_name": drug_name,
                "active_ingredient": active_ingredient,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        try:
            soup = BeautifulSoup(html_content, self.parser)

            # 1. Extract Drug Name & Active Ingredient if not provided
            if not drug_name:
                for h in soup.find_all(["h2", "h3"]):
                    text = h.get_text(strip=True)
                    match = re.search(r"^([^\(]+?)\s*\(\s*([A-Za-z]+[\s\-]?\d+)\s*\)", text)
                    if match:
                        drug_name = match.group(1).strip()
                        break
                if not drug_name:
                    title_elem = soup.find(["h1", "h2", "h3"])
                    if title_elem:
                        drug_name = title_elem.get_text(strip=True)

            if not active_ingredient:
                for h in soup.find_all(["h4", "h5"]):
                    text = h.get_text(strip=True)
                    if text.startswith("(") and text.endswith(")"):
                        active_ingredient = text.strip("() \t\n\r")
                        break

            drug_display = (drug_name or "Drug").title() if (drug_name and drug_name.isupper()) else (drug_name or "Drug")
            ingr_display = (active_ingredient or "").lower()
            ingr_clean = re.sub(r"\b(sulfate|hydrochloride|sodium|potassium|acetate)\b", "", ingr_display, flags=re.I).strip()
            if not ingr_clean:
                ingr_clean = ingr_display or "active ingredient"

            # 2. Extract Accordion
            accordion = soup.find("div", id="accordion") or soup.find("div", class_=lambda c: c and "accordion" in str(c))
            if not accordion:
                return {
                    "status": "no_data",
                    "drug_name": drug_display,
                    "active_ingredient": ingr_clean,
                    "message": "No data is present on adverse reaction",
                    "formatted_report": "No data is present on adverse reaction",
                }

            date_panels = []
            for header in accordion.find_all("h3"):
                header_text = header.get_text(strip=True)
                dt_obj = parse_fda_date(header_text)
                if not dt_obj:
                    date_match = re.search(
                        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
                        header_text,
                        re.IGNORECASE,
                    )
                    if date_match:
                        dt_obj = parse_fda_date(date_match.group(1))

                if not dt_obj:
                    continue

                change_date = dt_obj.strftime("%m/%d/%Y")
                suppl_match = re.search(r"\((SUPPL-[^\)]+)\)", header_text, re.IGNORECASE)
                suppl_id = suppl_match.group(1) if suppl_match else None

                panel = header.find_next_sibling("div")
                if panel:
                    date_panels.append({
                        "date_str": change_date,
                        "date_obj": dt_obj,
                        "suppl_id": suppl_id,
                        "panel": panel,
                    })

            # Sort chronologically descending (newest date first)
            date_panels.sort(key=lambda p: p["date_obj"], reverse=True)

            # 3. Check each date panel in chronological order for Adverse Reactions
            selected_panel = None
            selected_ar_content = None

            for dp in date_panels:
                panel = dp["panel"]
                h_elements = panel.find_all(["h4", "h5", "h3"])
                ar_parts = []

                for h in h_elements:
                    sec_title = re.sub(r"\s+", " ", h.get_text()).strip()

                    # Skip if section 17 or counseling information
                    if re.search(r"(?i)\b(?:17\b|17\s+17|PCI/PI/MG|Patient\s+Counseling|Medication\s+Guide)", sec_title):
                        continue

                    # Check if section title is Adverse Reactions
                    if re.search(r"(?i)\badverse\s+(?:reactions?|events?)\b", sec_title):
                        # Collect all content elements between this heading and next heading
                        section_elements = []
                        for sib in h.next_siblings:
                            if getattr(sib, "name", None) in ["h4", "h5", "h3"]:
                                break
                            if getattr(sib, "name", None):
                                section_elements.append(sib)

                        elem_texts = [clean_element_formatted_text(elem) for elem in section_elements]
                        formatted_text = "\n\n".join([t for t in elem_texts if t]).strip()
                        if formatted_text:
                            ar_parts.append(formatted_text)

                if ar_parts:
                    combined_text = "\n\n".join(ar_parts)
                    cleaned = clean_adverse_reaction_text(combined_text)
                    if cleaned:
                        selected_panel = dp
                        selected_ar_content = cleaned
                        break  # Stop at the latest date where adverse reaction is present

            if not selected_panel or not selected_ar_content:
                return {
                    "status": "no_data",
                    "drug_name": drug_display,
                    "active_ingredient": ingr_clean,
                    "message": "No data is present on adverse reaction",
                    "formatted_report": "No data is present on adverse reaction",
                    "dates_evaluated": [dp["date_str"] for dp in date_panels],
                }

            # 4. Format into exact report matching Image 2
            formatted_date = format_fda_date_to_report(selected_panel["date_str"])
            intro_line = (
                f"On {formatted_date}, the United States Food and Drug Administration "
                f"Center for Drug Evaluation and Research approved the following safety labeling "
                f"changes for {drug_display} ({ingr_clean}; Additions underlined):"
            )

            report_lines = [
                "3.1 The United States Food and Drug Administration",
                "",
                intro_line,
                "",
                "Adverse Reactions",
                "",
            ]

            for block in selected_ar_content.split("\n\n"):
                block = block.strip()
                if block:
                    report_lines.append(block)
                    report_lines.append("")

            formatted_report = "\n".join(report_lines).strip()

            return {
                "status": "success",
                "drug_name": drug_display,
                "active_ingredient": ingr_clean,
                "selected_date": selected_panel["date_str"],
                "formatted_date": formatted_date,
                "supplement_id": selected_panel["suppl_id"],
                "adverse_reactions_text": selected_ar_content,
                "intro_sentence": intro_line,
                "formatted_report": formatted_report,
                "dates_evaluated": [dp["date_str"] for dp in date_panels],
            }

        except Exception as e:
            logger.error(f"Error extracting adverse reactions report: {e}", exc_info=True)
            return {
                "status": "error",
                "drug_name": drug_name,
                "message": f"Error parsing adverse reactions: {str(e)}",
                "formatted_report": "No data is present on adverse reaction",
            }

    def extract_adverse_reactions_from_records(
        self,
        drug_name: str,
        active_ingredient: Optional[str],
        changes: List[Any],
    ) -> Dict[str, Any]:
        """
        Extract Adverse Reactions report from a list of SafetyLabelingChange database objects or dicts.
        Finds the latest date where section is 'Adverse Reactions'.
        """
        drug_display = (drug_name or "Drug").title() if (drug_name and drug_name.isupper()) else (drug_name or "Drug")
        ingr_display = (active_ingredient or "").lower()
        ingr_clean = re.sub(r"\b(sulfate|hydrochloride|sodium|potassium|acetate)\b", "", ingr_display, flags=re.I).strip()
        if not ingr_clean:
            ingr_clean = ingr_display or "active ingredient"

        if not changes:
            return {
                "status": "no_data",
                "drug_name": drug_display,
                "active_ingredient": ingr_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        def _get_val(obj, attr):
            if isinstance(obj, dict):
                return obj.get(attr)
            return getattr(obj, attr, None)

        # Filter records for Adverse Reactions
        ar_changes = []
        for c in changes:
            sec = _get_val(c, "section") or ""
            if re.search(r"(?i)\badverse\s+reactions?\b", sec):
                ar_changes.append(c)

        if not ar_changes:
            return {
                "status": "no_data",
                "drug_name": drug_display,
                "active_ingredient": ingr_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        # Group records by parsed date
        from collections import defaultdict
        grouped_by_date = defaultdict(list)
        for c in ar_changes:
            s_date = _get_val(c, "source_date")
            dt_obj = parse_fda_date(s_date)
            if dt_obj:
                grouped_by_date[dt_obj].append(c)

        if not grouped_by_date:
            return {
                "status": "no_data",
                "drug_name": drug_display,
                "active_ingredient": ingr_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
            }

        # Sort dates in descending order (latest date first)
        sorted_dates = sorted(grouped_by_date.keys(), reverse=True)

        selected_dt = None
        selected_suppl_id = None
        selected_cleaned_text = None

        for dt in sorted_dates:
            records_for_date = grouped_by_date[dt]
            texts = []
            suppl_id = None
            for rec in records_for_date:
                txt = _get_val(rec, "updated_text") or ""
                if txt:
                    texts.append(txt)
                if not suppl_id and _get_val(rec, "source_record_id"):
                    suppl_id = _get_val(rec, "source_record_id")

            if texts:
                cleaned = clean_adverse_reaction_text("\n\n".join(texts))
                if cleaned:
                    selected_dt = dt
                    selected_suppl_id = suppl_id
                    selected_cleaned_text = cleaned
                    break  # Stop at the latest date where adverse reactions are present

        if not selected_cleaned_text or not selected_dt:
            return {
                "status": "no_data",
                "drug_name": drug_display,
                "active_ingredient": ingr_clean,
                "message": "No data is present on adverse reaction",
                "formatted_report": "No data is present on adverse reaction",
                "dates_evaluated": [dt.strftime("%m/%d/%Y") for dt in sorted_dates],
            }

        s_date_str = selected_dt.strftime("%m/%d/%Y")
        formatted_date = format_fda_date_to_report(selected_dt)
        intro_line = (
            f"On {formatted_date}, the United States Food and Drug Administration "
            f"Center for Drug Evaluation and Research approved the following safety labeling "
            f"changes for {drug_display} ({ingr_clean}; Additions underlined):"
        )

        report_lines = [
            "3.1 The United States Food and Drug Administration",
            "",
            intro_line,
            "",
            "Adverse Reactions",
            "",
        ]

        for block in selected_cleaned_text.split("\n\n"):
            block = block.strip()
            if block:
                report_lines.append(block)
                report_lines.append("")

        formatted_report = "\n".join(report_lines).strip()

        return {
            "status": "success",
            "drug_name": drug_display,
            "active_ingredient": ingr_clean,
            "selected_date": s_date_str,
            "formatted_date": formatted_date,
            "supplement_id": selected_suppl_id,
            "adverse_reactions_text": selected_cleaned_text,
            "intro_sentence": intro_line,
            "formatted_report": formatted_report,
            "dates_evaluated": [dt.strftime("%m/%d/%Y") for dt in sorted_dates],
        }


# Create singleton instance
scraper = FDASrLCScraper()
