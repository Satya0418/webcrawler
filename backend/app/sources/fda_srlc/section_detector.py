"""
Section Detector and Text Cleaner for FDA SrLC.
Detects Adverse Reactions, Warnings and Precautions, and Pregnancy / Use in Specific Populations
according to FDA 21 CFR 201.56 / 201.57 section identifiers.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup, NavigableString, Tag

logger = logging.getLogger(__name__)


def sanitize_fda_section_html(raw_html: str) -> str:
    """
    Sanitize raw FDA section HTML to preserve exact visual formatting:
    - Retains <a>, <h4>, <h5>, <h6>, <strong>, <b>, <i>, <em>, <u>, <ul>, <ol>, <li>, <p>, <br>.
    - Retains href and target on <a> links.
    - Removes unneeded styles, classes, and script/style tags.
    - Stops / cuts off at Section 17 (PCI/PI/MG, Patient Counseling, Medication Guide).
    - Removes empty tags and normalizes excessive spaces while preserving semantic HTML.
    """
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "lxml")

    # Decompose script, style, head, meta
    for s in soup(["script", "style", "head", "meta", "title"]):
        s.decompose()

    # Cut off at section 17 / PCI / PI / MG / Patient Counseling Information / Medication Guide
    stop_pattern = re.compile(
        r"(?i)\b(?:17\b|PCI/PI/MG|Patient\s+Counseling|MEDICATION\s+GUIDE|How\s+should\s+I\s+use)",
    )
    for elem in soup.find_all(["h4", "h5", "h6", "p", "strong", "b"]):
        if stop_pattern.search(elem.get_text()):
            # Remove this element and all subsequent siblings
            for sib in list(elem.find_next_siblings()):
                sib.decompose()
            elem.decompose()
            break

    # Unwrap container divs
    for div in soup.find_all("div"):
        div.unwrap()

    # Whitelist tags
    allowed_tags = {"p", "b", "strong", "i", "em", "u", "ul", "ol", "li", "a", "br", "h4", "h5", "h6", "span"}
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            tag.unwrap()
        else:
            if tag.name == "a":
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("href", "target", "title")}
                if "target" not in tag.attrs:
                    tag["target"] = "_blank"
                tag["rel"] = "noopener noreferrer"
            else:
                tag.attrs = {}

    # Normalize whitespace in text nodes
    for p in soup.find_all("p"):
        if not p.get_text(strip=True) and not p.find("a"):
            p.decompose()

    html_out = str(soup)
    html_out = re.sub(r"^<html><body>|</body></html>$", "", html_out).strip()
    return html_out


def clean_fda_element_text(elem: Any) -> str:
    """
    Extract clean, well-formatted text from an HTML element.
    Preserves bullet points (•), paragraph breaks, subsection headers,
    underlines, italic notes, and cross-references.
    """
    if not elem:
        return ""

    soup = BeautifulSoup(str(elem), "lxml")
    body = soup.body or soup

    # Stop at Section 17
    stop_pattern = re.compile(
        r"(?i)\b(?:17\b|PCI/PI/MG|Patient\s+Counseling|MEDICATION\s+GUIDE|How\s+should\s+I\s+use)",
    )
    for el in body.find_all(["h4", "h5", "h6", "p", "strong", "b"]):
        if stop_pattern.search(el.get_text()):
            for sib in list(el.find_next_siblings()):
                sib.decompose()
            el.decompose()
            break

    # Normalize internal newlines inside paragraphs, spans, headers to spaces so sentences aren't fragmented
    for tag in body.find_all(["p", "span", "h4", "h5", "h6", "div"]):
        for c in tag.contents:
            if isinstance(c, NavigableString):
                c.replace_with(re.sub(r"[\r\n\t]+", " ", str(c)))

    # Process lists: replace li with clean bullet line preserving inline tags
    for li in body.find_all("li"):
        li_inner = []
        for child in li.children:
            if isinstance(child, NavigableString):
                li_inner.append(re.sub(r"[\r\n\t]+", " ", str(child)))
            elif isinstance(child, Tag):
                tag_name = child.name
                txt = re.sub(r"\s+", " ", child.get_text()).strip()
                if tag_name in ("u", "ins"):
                    inner_html = "".join(str(c) for c in child.children)
                    inner_cleaned = re.sub(r"\s+", " ", inner_html).strip()
                    li_inner.append(f"<u>{inner_cleaned}</u>")
                elif tag_name in ("i", "em"):
                    li_inner.append(f"<i>{txt}</i>")
                elif tag_name in ("b", "strong"):
                    li_inner.append(f"<strong>{txt}</strong>")
                elif tag_name == "p":
                    inner_html = "".join(str(c) for c in child.children)
                    inner_cleaned = re.sub(r"\s+", " ", inner_html).strip()
                    li_inner.append(inner_cleaned)
                else:
                    li_inner.append(txt)
        full_li = "".join(li_inner).strip()
        full_li = re.sub(r"\s+", " ", full_li)
        li.replace_with(f"\n• {full_li}\n")

    # Preserve <u> underline tags for additions and revisions
    for u in body.find_all(["u", "ins"]):
        u_html = "".join(str(c) for c in u.children)
        u_clean = re.sub(r"\s+", " ", u_html).strip()
        if u_clean:
            u.replace_with(f"<u>{u_clean}</u>")
        else:
            u.decompose()

    # Preserve <i> italic tags
    for i in body.find_all(["i", "em"]):
        i_txt = re.sub(r"\s+", " ", i.get_text()).strip()
        if i_txt:
            i.replace_with(f"<i>{i_txt}</i>")
        else:
            i.decompose()

    # Preserve <b>/<strong> bold tags
    for b in body.find_all(["b", "strong"]):
        b_txt = re.sub(r"\s+", " ", b.get_text()).strip()
        if b_txt:
            b.replace_with(f"<strong>{b_txt}</strong>")
        else:
            b.decompose()

    # Preserve paragraph and block linebreaks
    for p in body.find_all(["p", "div", "h4", "h5", "h6", "blockquote", "ul", "ol"]):
        p.insert_before("\n\n")
        p.unwrap()

    for br in body.find_all("br"):
        br.replace_with("\n")

    text = body.get_text()

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

    joined = "\n".join(result).strip()
    # Merge adjacent formatting tags on the same line (using [ \t]* so we never merge across newlines)
    joined = re.sub(r"</u>[ \t]*<u>", " ", joined)
    joined = re.sub(r"</i>[ \t]*<i>", " ", joined)
    joined = re.sub(r"</strong>[ \t]*<strong>", " ", joined)
    joined = re.sub(r"</b>[ \t]*<b>", " ", joined)
    joined = re.sub(r"<i>:</i>\s*", ":", joined)
    return joined.strip()


def clean_faithful_fda_text(raw_html_or_elem: Any) -> str:
    """Alias for clean_fda_element_text preserving faithful structure."""
    return clean_fda_element_text(raw_html_or_elem)


def clean_adverse_reaction_text(raw_text: str) -> str:
    """
    Filter and clean adverse reaction text:
    - Stops immediately if section 17 / PCI/PI/MG / Medication Guide appears.
    - Preserves subsection headers, bullet points, underlines, and cross-references.
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

    # Normalize broken subsection headers that have accidental linebreaks
    raw_text = re.sub(r"(?i)\bPostmarketing\s*\n+\s*Experience\b", "Postmarketing Experience", raw_text)
    raw_text = re.sub(r"(?i)\bClinical\s*\n+\s*Trials?\s*\n+\s*Experience\b", "Clinical Trials Experience", raw_text)

    # Normalize whitespace while preserving line structure
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.split("\n")]
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


def clean_general_section_text(raw_text: str) -> str:
    """Clean warnings or pregnancy sections, cutting off at section 17."""
    if not raw_text:
        return ""

    # Cut off at section 17 / PCI / PI / MG
    stop_regex = re.compile(
        r"(?i)(?:^|\n)\s*(?:17\b|17\s+17|PCI/PI/MG|Patient\s+Counseling\s+Information|MEDICATION\s+GUIDE)",
    )
    m = stop_regex.search(raw_text)
    if m:
        raw_text = raw_text[:m.start()]

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.split("\n")]
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


class FDASrLCSectionDetector:
    """Detects and categorizes FDA safety sections with strict priority order."""

    @staticmethod
    def is_adverse_reactions(header_text: str) -> bool:
        """Identify Section 6 / Adverse Reactions."""
        clean = re.sub(r"[\r\n\t]+", " ", header_text).strip().lower()
        if re.search(r"\b6\b|\badverse\s+reactions?\b|\badverse\s+events?\b", clean):
            return "adverse" in clean or "reaction" in clean or clean.startswith("6")
        return False

    @staticmethod
    def is_warnings_and_precautions(header_text: str) -> bool:
        """Identify Section 5 / Warnings and Precautions."""
        clean = re.sub(r"[\r\n\t]+", " ", header_text).strip().lower()
        if re.search(r"\b5\b|\bwarnings?\b|\bprecautions?\b", clean):
            return "warning" in clean or "precaution" in clean or clean.startswith("5")
        return False

    @staticmethod
    def is_use_in_specific_populations(header_text: str) -> bool:
        """Identify Section 8 / Use in Specific Populations."""
        clean = re.sub(r"[\r\n\t]+", " ", header_text).strip().lower()
        if re.search(r"\b8\b|\bspecific\s+populations?\b|\bpregnancy\b|\blactation\b", clean):
            return "specific population" in clean or "use in" in clean or clean.startswith("8") or "pregnancy" in clean
        return False

    @staticmethod
    def extract_pregnancy_subsections(section_text: str) -> Optional[str]:
        """
        Inspect Section 8 content to detect and extract pregnancy-relevant subsections:
        - 8.1 Pregnancy
        - 8.2 Lactation
        - 8.3 Females and Males of Reproductive Potential (or Nursing Mothers)
        Returns the pregnancy-specific text if found, or None if section only contains geriatric/pediatric.
        """
        if not section_text:
            return None

        # Check for presence of pregnancy / lactation / reproductive indicators
        has_preg_indicator = bool(re.search(
            r"(?i)(\b8\.1\b|\b8\.2\b|\b8\.3\b|\bpregnancy\b|\blactation\b|\breproductive\s+potential\b|\bnursing\s+mothers\b|\bteratogen|\bfetal\b|\bneonat)",
            section_text,
        ))
        if not has_preg_indicator:
            return None

        # If subsections are clearly demarcated, extract 8.1 / 8.2 / 8.3
        pattern = re.compile(
            r"(?i)(?:^|\n)\s*(8\.[123]\b[^\n]*|pregnancy\b[^\n]*|lactation\b[^\n]*|females\s+and\s+males\s+of\s+reproductive\s+potential\b[^\n]*)(.*?)(?=(?:(?:^|\n)\s*8\.[456789]\b)|$)",
            re.DOTALL,
        )
        matches = pattern.findall(section_text)
        if matches:
            parts = []
            for heading, body in matches:
                parts.append(f"{heading.strip()}\n{body.strip()}")
            extracted = "\n\n".join(parts).strip()
            return clean_general_section_text(extracted)

        # Fallback: whole section text if pregnancy indicator was confirmed
        return clean_general_section_text(section_text)
