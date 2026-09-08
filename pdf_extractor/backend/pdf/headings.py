import re
from typing import List, Optional, Tuple, Dict, Any
from backend.models.schemas import DocumentBlock, BlockType
from backend.config import MAX_HEADING_LENGTH


class HeadingDetector:
    """
    Multi-signal heading detector that analyzes numbering patterns, font typography,
    block geometry, TOC artifacts, and sentence structure to identify real section headings.
    """

    # Matches section numbering like:
    # "16", "16.", "16.1", "16.1.", "16.1.1", "Section 16", "Section 16.1:"
    HEADING_REGEX = re.compile(
        r"^(?:Section\s+|SECTION\s+|Chapter\s+|CHAPTER\s+)?(\d+(?:\.\d+)*)(?:[\.\:\s\-]+)(.*)$",
        re.IGNORECASE
    )

    STANDALONE_NUMBER_REGEX = re.compile(
        r"^(?:Section\s+|SECTION\s+)?(\d+(?:\.\d+)*)\.?$",
        re.IGNORECASE
    )

    # In-text citation patterns like "See Section 16.1 for details" or "In 16.1% of patients"
    IN_TEXT_CITATION_PREFIXES = (
        "see section",
        "in section",
        "refer to",
        "according to",
        "as in",
        "table",
        "figure",
        "fig.",
        "appendix",
    )

    # Dot leaders in TOC: "........" or "...... 20"
    TOC_DOT_LEADER_REGEX = re.compile(r"(\.{3,}|…|\s{5,}\d+$)")

    def __init__(self, body_font_size: float = 11.0, toc_bookmarks: Optional[List[Tuple[int, str, int]]] = None):
        self.body_font_size = body_font_size
        self.toc_bookmarks = toc_bookmarks or []

    def canonicalize_section_number(self, num_str: str) -> str:
        """Normalizes section numbers, e.g., '16.' -> '16', '16.01' -> '16.1'."""
        num_str = num_str.strip().strip(".:-")
        try:
            parts = [str(int(p)) for p in num_str.split(".") if p.isdigit()]
            return ".".join(parts) if parts else num_str
        except Exception:
            return num_str

    def calculate_level(self, canonical_num: str) -> int:
        """Determines heading depth: '16' -> 1, '16.1' -> 2, '16.1.1' -> 3."""
        parts = canonical_num.split(".")
        return len(parts)

    def is_toc_line(self, text: str, page_num: int) -> bool:
        """Detects whether a line belongs to a Table of Contents rather than the body."""
        clean = text.strip()
        # Pages 1 to 5 with dot leaders or trailing page numbers
        if self.TOC_DOT_LEADER_REGEX.search(clean):
            return True
        # If line ends with page number separated by space/tabs: "16.1 Adverse Events   24"
        if re.search(r"[A-Za-z\)]\s{3,}\d{1,4}$", clean):
            return True
        return False

    def is_in_text_citation(self, text: str) -> bool:
        """Rejects in-text mentions like 'See Section 16.1 for details.'"""
        clean = text.strip().lower()
        for prefix in self.IN_TEXT_CITATION_PREFIXES:
            if clean.startswith(prefix):
                return True
        # If line is very long, it is a sentence/paragraph, not a heading
        if len(text.strip()) > MAX_HEADING_LENGTH:
            return True
        # If text ends with terminal sentence punctuation after multiple words
        # (e.g. "Adverse events were reported in Section 16.1.")
        words = text.strip().split()
        if len(words) > 5 and text.strip().endswith((".", ";", "!")):
            return True
        # Check for percentage: "16.1% of subjects"
        if re.search(r"^\d+(?:\.\d+)*%", text.strip()):
            return True
        return False

    def match_heading(self, line: str, page_num: int) -> Optional[Tuple[str, str, int]]:
        """
        Attempts to match a heading on a single line.
        Returns (canonical_number, title, level) or None.
        """
        clean = line.strip()
        if not clean or self.is_toc_line(clean, page_num) or self.is_in_text_citation(clean):
            return None

        # Check standard heading: "16.1 Adverse Events" or "16. SAFETY"
        m = self.HEADING_REGEX.match(clean)
        if m:
            raw_num, title = m.groups()
            title = title.strip()
            # If title starts with lowercase word and is long, probably a sentence: "16.1 patients were treated"
            first_word = title.split()[0] if title.split() else ""
            if first_word and first_word[0].islower() and len(title.split()) > 3:
                return None

            canon_num = self.canonicalize_section_number(raw_num)
            level = self.calculate_level(canon_num)
            return canon_num, title, level

        # Check standalone section number: "16.1"
        m_num = self.STANDALONE_NUMBER_REGEX.match(clean)
        if m_num:
            raw_num = m_num.group(1)
            canon_num = self.canonicalize_section_number(raw_num)
            level = self.calculate_level(canon_num)
            return canon_num, "", level

        return None

    def process_blocks(self, blocks: List[DocumentBlock]) -> List[DocumentBlock]:
        """
        Examines all blocks, splits blocks if a heading is found on line 0 followed by body text,
        and tags heading blocks with section_number, is_heading=True, and heading_level.
        """
        result_blocks: List[DocumentBlock] = []

        for b in blocks:
            # Skip blocks already identified as header or footer
            if b.block_type in (BlockType.HEADER, BlockType.FOOTER, BlockType.TABLE):
                result_blocks.append(b)
                continue

            lines = [l for l in b.text.split("\n") if l.strip()]
            if not lines:
                continue

            first_line = lines[0]
            heading_match = self.match_heading(first_line, b.page_num)

            # Signal evaluation:
            is_valid_heading = False
            canon_num = ""
            title = ""
            level = 0

            if heading_match:
                canon_num, title, level = heading_match

                # Typography check:
                # Heading should be >= body font size, or bold, or bookmark match
                is_prominent = (
                    b.font_size >= (self.body_font_size - 0.5) or
                    b.is_bold or
                    any(bm[1].startswith(canon_num) for bm in self.toc_bookmarks)
                )

                if is_prominent:
                    is_valid_heading = True

            if is_valid_heading:
                # If block has multiple lines, split line 0 (heading) from subsequent lines (body)
                heading_text = f"{canon_num} {title}".strip() if title else first_line.strip()
                
                # Create heading block
                heading_block = DocumentBlock(
                    block_id=f"{b.block_id}_h",
                    page_num=b.page_num,
                    bbox=b.bbox,
                    block_type=BlockType.HEADING,
                    text=heading_text,
                    font_size=b.font_size,
                    is_bold=b.is_bold,
                    section_number=canon_num,
                    is_heading=True,
                    heading_level=level,
                )
                result_blocks.append(heading_block)

                # If there are subsequent lines in this block, create a separate body block
                if len(lines) > 1:
                    remaining_text = "\n".join(lines[1:]).strip()
                    if remaining_text:
                        body_block = DocumentBlock(
                            block_id=f"{b.block_id}_b",
                            page_num=b.page_num,
                            bbox=b.bbox,
                            block_type=BlockType.PARAGRAPH,
                            text=remaining_text,
                            font_size=b.font_size,
                            is_bold=b.is_bold,
                            section_number=canon_num,
                            is_heading=False,
                            heading_level=None,
                        )
                        result_blocks.append(body_block)
            else:
                result_blocks.append(b)

        return result_blocks
