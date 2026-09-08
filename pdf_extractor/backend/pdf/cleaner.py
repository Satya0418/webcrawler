import re
from typing import List, Dict, Set, Tuple
from backend.models.schemas import DocumentBlock, BlockType
from backend.config import HEADER_MARGIN_RATIO, FOOTER_MARGIN_RATIO


class HeaderFooterCleaner:
    """
    Identifies and marks repeated headers and footers based on vertical margins
    and frequency across multiple pages.
    """

    PAGE_NUM_PATTERN = re.compile(
        r"^(page\s+\d+(\s+(of|/)\s+\d+)?|\d+\s*/\s*\d+|-\s*\d+\s*-|\d+)$",
        re.IGNORECASE
    )

    def __init__(
        self,
        top_margin_ratio: float = HEADER_MARGIN_RATIO,
        bottom_margin_ratio: float = FOOTER_MARGIN_RATIO
    ):
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio

    def normalize_header_text(self, text: str) -> str:
        """Strip variable numbers like page counts to find recurring template strings."""
        text = text.strip()
        # Replace digits with #
        return re.sub(r"\d+", "#", text)

    def analyze_and_tag(
        self,
        blocks: List[DocumentBlock],
        page_heights: Dict[int, float]
    ) -> List[DocumentBlock]:
        """
        Tags repeated or standard headers and footers as BlockType.HEADER or BlockType.FOOTER.
        """
        # Collect candidate texts in header/footer zones across pages
        header_candidates: Dict[str, Set[int]] = {}
        footer_candidates: Dict[str, Set[int]] = {}

        for b in blocks:
            page_h = page_heights.get(b.page_num, 792.0)
            top_bound = page_h * self.top_margin_ratio
            bottom_bound = page_h * (1.0 - self.bottom_margin_ratio)

            clean_text = b.text.strip()
            if not clean_text:
                continue

            norm = self.normalize_header_text(clean_text)

            # Check if block is in top zone
            if b.bbox[3] <= top_bound + 10:  # y1 is within top 8%
                if norm not in header_candidates:
                    header_candidates[norm] = set()
                header_candidates[norm].add(b.page_num)

            # Check if block is in bottom zone
            if b.bbox[1] >= bottom_bound - 10:  # y0 is within bottom 8%
                if norm not in footer_candidates:
                    footer_candidates[norm] = set()
                footer_candidates[norm].add(b.page_num)

        # A template is considered repeated if it appears on 2 or more distinct pages
        repeated_headers = {k for k, pages in header_candidates.items() if len(pages) >= 2}
        repeated_footers = {k for k, pages in footer_candidates.items() if len(pages) >= 2}

        # Apply tagging
        for b in blocks:
            page_h = page_heights.get(b.page_num, 792.0)
            top_bound = page_h * self.top_margin_ratio
            bottom_bound = page_h * (1.0 - self.bottom_margin_ratio)
            clean_text = b.text.strip()
            if not clean_text:
                continue

            norm = self.normalize_header_text(clean_text)
            is_page_num = bool(self.PAGE_NUM_PATTERN.match(clean_text.lower()))

            if b.bbox[3] <= top_bound + 10:
                if norm in repeated_headers or is_page_num:
                    b.block_type = BlockType.HEADER
            elif b.bbox[1] >= bottom_bound - 10:
                if norm in repeated_footers or is_page_num:
                    b.block_type = BlockType.FOOTER

        return blocks
