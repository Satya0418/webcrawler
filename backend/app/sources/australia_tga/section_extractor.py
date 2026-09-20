"""
Section extraction engine for Australia TGA Product Information.
Exclusively responsible for isolating Section 4.6 and Section 4.8, preserving original
wording, table formatting, page numbers, and stop boundaries.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.sources.australia_tga.config import (
    MISSING_SECTION_4_6_TEXT,
    MISSING_SECTION_4_8_TEXT,
    SECTION_4_6_NAME,
    SECTION_4_6_NUM,
    SECTION_4_8_NAME,
    SECTION_4_8_NUM,
    STOP_SECTION_FOR_4_6,
    STOP_SECTION_FOR_4_8,
)
from app.sources.australia_tga.models import ExtractedSection, ExtractedTable
from app.sources.australia_tga.table_extractor import TGATableExtractor

logger = logging.getLogger(__name__)


class TGASectionExtractor:
    """
    Deterministically isolates and extracts Section 4.6 and Section 4.8 from PDF extraction results.
    Strictly enforces stop boundaries and page traceability.
    """

    @classmethod
    def process_sections(
        cls,
        extraction_data: Dict[str, Any],
    ) -> Dict[str, ExtractedSection]:
        """
        Processes extraction output for both 4.6 and 4.8.
        Returns a dict containing:
        {
            "section_4_6": ExtractedSection,
            "section_4_8": ExtractedSection,
        }
        """
        res_4_6 = extraction_data.get("section_4_6")
        res_4_8 = extraction_data.get("section_4_8")

        sec_4_6 = cls.extract_section_4_6(res_4_6)
        sec_4_8 = cls.extract_section_4_8(res_4_8)

        return {
            "section_4_6": sec_4_6,
            "section_4_8": sec_4_8,
        }

    @classmethod
    def extract_section_4_6(cls, raw_result: Any) -> ExtractedSection:
        """
        Extracts Section 4.6 (Fertility, Pregnancy and Lactation).
        Stops strictly at Section 4.7.
        """
        if not raw_result:
            return ExtractedSection(
                section_number=SECTION_4_6_NUM,
                title=SECTION_4_6_NAME,
                start_page=0,
                end_page=0,
                pages_str="",
                text_content=MISSING_SECTION_4_6_TEXT,
                tables=[],
                is_present=False,
                confidence=0.0,
            )

        content = cls._get_content_string(raw_result)
        status = cls._get_status(raw_result)
        start_p, end_p = cls._get_page_range(raw_result)

        if status == "not_found" or not content or not content.strip():
            logger.info("Section 4.6 not found in document")
            return ExtractedSection(
                section_number=SECTION_4_6_NUM,
                title=SECTION_4_6_NAME,
                start_page=0,
                end_page=0,
                pages_str="",
                text_content=MISSING_SECTION_4_6_TEXT,
                tables=[],
                is_present=False,
                confidence=0.0,
            )

        # Truncate strictly at Section 4.7 if boundary leaked
        cleaned_text = cls._truncate_at_stop_boundary(
            content,
            stop_patterns=[r"\b4\.7\b", r"effects\s+on\s+ability\s+to\s+drive"],
        )

        pages_str = cls._format_page_str(start_p, end_p)
        confidence = cls._get_confidence(raw_result)

        return ExtractedSection(
            section_number=SECTION_4_6_NUM,
            title=SECTION_4_6_NAME,
            start_page=start_p,
            end_page=end_p,
            pages_str=pages_str,
            text_content=cleaned_text.strip(),
            tables=[],
            is_present=True,
            confidence=confidence,
        )

    @classmethod
    def extract_section_4_8(cls, raw_result: Any) -> ExtractedSection:
        """
        Extracts Section 4.8 (Adverse Effects / Undesirable Effects).
        Stops strictly at Section 4.9 or Section 5.
        Captures all adverse reaction tables, system organ classes, and footnotes.
        """
        if not raw_result:
            return ExtractedSection(
                section_number=SECTION_4_8_NUM,
                title=SECTION_4_8_NAME,
                start_page=0,
                end_page=0,
                pages_str="",
                text_content=MISSING_SECTION_4_8_TEXT,
                tables=[],
                is_present=False,
                confidence=0.0,
            )

        content = cls._get_content_string(raw_result)
        status = cls._get_status(raw_result)
        start_p, end_p = cls._get_page_range(raw_result)

        if status == "not_found" or not content or not content.strip():
            logger.info("Section 4.8 not found in document")
            return ExtractedSection(
                section_number=SECTION_4_8_NUM,
                title=SECTION_4_8_NAME,
                start_page=0,
                end_page=0,
                pages_str="",
                text_content=MISSING_SECTION_4_8_TEXT,
                tables=[],
                is_present=False,
                confidence=0.0,
            )

        # Extract structured adverse reaction tables
        tables = TGATableExtractor.extract_and_format_tables(raw_result)

        # Truncate strictly at Section 4.9 or Section 5 if boundary leaked
        cleaned_text = cls._truncate_at_stop_boundary(
            content,
            stop_patterns=[r"\b4\.9\b", r"\boverdose\b", r"\b5\.0?\b", r"pharmacological\s+properties"],
        )

        # Integrate clean merged tables into text content (replacing fragmented raw tables)
        if tables:
            cleaned_text = TGATableExtractor.integrate_merged_tables_into_text(cleaned_text, tables)

        pages_str = cls._format_page_str(start_p, end_p)
        confidence = cls._get_confidence(raw_result)

        return ExtractedSection(
            section_number=SECTION_4_8_NUM,
            title=SECTION_4_8_NAME,
            start_page=start_p,
            end_page=end_p,
            pages_str=pages_str,
            text_content=cleaned_text.strip(),
            tables=tables,
            is_present=True,
            confidence=confidence,
        )

    SUBHEAD_PATTERNS = [
        r"^effects?\s+on\s+fertility\b",
        r"^fertility\s*$",
        r"^use\s+in\s+pregnancy\b",
        r"^pregnancy\s*$",
        r"^category\s+[A-X0-9]+(?:\s*\(.*?\))?\s*$",
        r"^use\s+in\s+lactation\b",
        r"^lactation\s*$",
        r"^breastfeeding\s*$",
        r"^use\s+in\s+breastfeeding\b",
        r"^females?\s+and\s+males?\s+of\s+reproductive\s+potential\b",
        r"^contraception\s*$",
        r"^summary\s+of\s+(?:the\s+)?safety\s+profile\b",
        r"^tabulated\s+list\s+of\s+adverse\s+reactions\b",
        r"^description\s+of\s+selected\s+adverse\s+reactions\b",
        r"^reporting\s+(?:of\s+)?suspected\s+adverse\s+effects\b",
        r"^post-?marketing\s+experience\b",
        r"^clinical\s+trials?\s+experience\b",
        r"^paediatric\s+use\b",
        r"^use\s+in\s+the\s+elderly\b",
        r"^prevention\s+of\s+vte\b",
        r"^treatment\s+of\s+dvt\b",
        r"^prevention\s+of\s+stroke\b",
    ]

    @classmethod
    def is_subheading_line(cls, line: str) -> bool:
        """Determines if a line is a regulatory sub-topic or subheading."""
        clean = re.sub(r"^###\s*", "", line.strip())
        if not clean or len(clean) > 80:
            return False
        if any(re.search(p, clean, re.I) for p in cls.SUBHEAD_PATTERNS):
            return True
        # Heuristic for other subheadings: short title case line without terminal punctuation
        if not re.search(r"[\.\,\;\!\?]$", clean) and len(clean) < 55:
            words = clean.split()
            if 1 <= len(words) <= 7:
                sentence_words = {
                    "and", "or", "to", "in", "is", "was", "were", "the",
                    "for", "with", "from", "by", "at"
                }
                if words[0].lower() not in sentence_words:
                    upper_words = [w for w in words if w[0].isupper()]
                    if len(upper_words) / len(words) >= 0.6:
                        return True
        return False

    @classmethod
    def _truncate_at_stop_boundary(cls, text: str, stop_patterns: List[str]) -> str:
        """Stops extraction strictly before the next section begins."""
        lines = text.split("\n")
        retained_lines: List[str] = []

        combined_regex = re.compile("|".join(f"(?:{p})" for p in stop_patterns), re.IGNORECASE)

        for line in lines:
            line_s = line.strip()
            # If line is a heading or starts with stop section
            if re.match(r"^(?:###\s*)?(\[Page\s+\d+\]\s+)?(4\.7|4\.9|5(\.0)?)\b", line_s, re.IGNORECASE):
                break
            if combined_regex.search(line_s) and len(line_s) < 80:
                # Likely heading of next section
                if any(k in line_s.lower() for k in ("4.7", "4.9", "5.", "overdose", "pharmacological")):
                    break
            retained_lines.append(line)

        return "\n".join(retained_lines)

    @classmethod
    def _get_content_string(cls, raw_result: Any) -> str:
        """
        Retrieves formatted, structured text content from ExtractionResult or dict,
        preserving distinct subheadings and paragraphs.
        """
        blocks = getattr(raw_result, "blocks", None)
        if blocks is None and isinstance(raw_result, dict):
            blocks = raw_result.get("blocks", [])

        if not blocks:
            # Fallback to content string if blocks are not present
            content = ""
            if hasattr(raw_result, "content"):
                content = getattr(raw_result, "content") or ""
            elif isinstance(raw_result, dict):
                content = raw_result.get("content") or ""

            if not content:
                return ""

            lines = content.split("\n")
            out: List[str] = []
            curr_para: List[str] = []

            def flush_curr():
                if curr_para:
                    text = " ".join(curr_para).strip()
                    if text:
                        out.append(text)
                    curr_para.clear()

            for l in lines:
                ls = l.strip()
                if not ls:
                    flush_curr()
                    continue
                if cls.is_subheading_line(ls) or re.match(r"^(?:\[Page\s+\d+\]\s*)?(4\.[68]|5\.[0-9])\b", ls, re.I):
                    flush_curr()
                    clean_sub = re.sub(r"^(?:\[Page\s+\d+\]\s*)?###\s*", "", ls)
                    out.append(f"### {clean_sub}")
                elif ls.startswith("|") and ("|" in ls[1:]):
                    flush_curr()
                    out.append(ls)
                else:
                    curr_para.append(ls)

            flush_curr()
            return "\n\n".join(out)

        items: List[str] = []
        current_para_lines: List[str] = []

        def flush_para():
            if current_para_lines:
                text = " ".join(current_para_lines).strip()
                if text:
                    items.append(text)
                current_para_lines.clear()

        for idx, b in enumerate(blocks):
            t = getattr(b, "text", "") if hasattr(b, "text") else (b.get("text", "") if isinstance(b, dict) else "")
            b_type = getattr(b, "block_type", "") if hasattr(b, "block_type") else (b.get("block_type", "") if isinstance(b, dict) else "")
            if b_type == "table":
                flush_para()
                items.append(t.strip())
                continue

            clean_t = re.sub(r"^\[Page\s+\d+\]\s*", "", (t or "").strip())
            if not clean_t:
                continue

            lines = clean_t.split("\n")
            for line in lines:
                ls = line.strip()
                if not ls:
                    continue

                if cls.is_subheading_line(ls):
                    flush_para()
                    clean_sub = re.sub(r"^###\s*", "", ls)
                    items.append(f"### {clean_sub}")
                elif re.match(r"^(?:\[Page\s+\d+\]\s*)?(4\.[68]|5\.[0-9])\b", ls, re.I):
                    flush_para()
                    clean_header = re.sub(r"^(?:\[Page\s+\d+\]\s*)?###\s*", "", ls)
                    items.append(f"### {clean_header}")
                elif ls.startswith("|") and ("|" in ls[1:]):
                    flush_para()
                    items.append(ls)
                else:
                    current_para_lines.append(ls)

            # Check if next block is a continuation of this sentence across a page break
            next_is_continuation = False
            if idx + 1 < len(blocks) and current_para_lines:
                last_line = current_para_lines[-1]
                nxt_b = blocks[idx + 1]
                next_t = getattr(nxt_b, "text", "") if hasattr(nxt_b, "text") else (nxt_b.get("text", "") if isinstance(nxt_b, dict) else "")
                next_clean = re.sub(r"^\[Page\s+\d+\]\s*", "", (next_t or "").strip())
                if next_clean and not re.search(r"[\.\!\?\:]$", last_line) and next_clean[0].islower():
                    next_is_continuation = True

            if not next_is_continuation:
                flush_para()

        flush_para()
        return "\n\n".join(items)

    @classmethod
    def _get_status(cls, raw_result: Any) -> str:
        """Retrieves status string from ExtractionResult or dict."""
        if hasattr(raw_result, "status"):
            return getattr(raw_result, "status") or "success"
        if isinstance(raw_result, dict):
            return raw_result.get("status", "success")
        return "success"

    @classmethod
    def _get_page_range(cls, raw_result: Any) -> tuple[int, int]:
        """Extracts start_page and end_page from ExtractionResult or dict."""
        start_p = getattr(raw_result, "start_page", 0) if hasattr(raw_result, "start_page") else 0
        end_p = getattr(raw_result, "end_page", 0) if hasattr(raw_result, "end_page") else 0

        if isinstance(raw_result, dict):
            start_p = raw_result.get("start_page", start_p)
            end_p = raw_result.get("end_page", end_p)

        return int(start_p or 0), int(end_p or 0)

    @classmethod
    def _get_confidence(cls, raw_result: Any) -> float:
        """Extracts validation confidence score."""
        val = getattr(raw_result, "validation", None)
        if val and hasattr(val, "confidence_score"):
            return float(val.confidence_score)
        if isinstance(raw_result, dict):
            val_d = raw_result.get("validation", {})
            if isinstance(val_d, dict):
                return float(val_d.get("confidence_score", 1.0))
        return 1.0

    @classmethod
    def _format_page_str(cls, start_p: int, end_p: int) -> str:
        """Formats page numbers e.g. '18–20' or '18'."""
        if start_p > 0 and end_p > 0:
            return f"{start_p}–{end_p}" if start_p != end_p else str(start_p)
        if start_p > 0:
            return str(start_p)
        return ""
