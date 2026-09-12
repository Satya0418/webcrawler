import re
import fitz
from typing import List, Dict
from collections import Counter
from backend.models.schemas import DocumentBlock, BlockType
from backend.pdf.cleaner import HeaderFooterCleaner


class PDFParser:
    """Parses a PDF into structured DocumentBlocks with typography and layout metadata."""

    BULLET_REGEX = re.compile(r"^[\s\u2022\u25cf\u25cb\u25aa\u25ab\-\*]+(?:\s+|$)")
    NUMBERED_LIST_REGEX = re.compile(r"^\s*(?:\(\d+\)|\d+\.|\d+\))\s+")

    def __init__(self, doc: fitz.Document):
        self.doc = doc
        self.blocks: List[DocumentBlock] = []
        self.page_heights: Dict[int, float] = {}
        self.body_font_size: float = 11.0
        self.font_stats: Counter = Counter()

    def parse(self) -> List[DocumentBlock]:
        """Runs the complete block extraction and typography analysis pipeline."""
        raw_blocks: List[DocumentBlock] = []
        font_sizes: List[float] = []

        # 1. Extract blocks and spans from each page
        for page_idx in range(len(self.doc)):
            page_num = page_idx + 1
            page = self.doc[page_idx]
            self.page_heights[page_num] = page.rect.height

            page_dict = page.get_text("dict")
            blocks_data = page_dict.get("blocks", [])

            for b_idx, b in enumerate(blocks_data):
                # Filter out pure image blocks
                if b.get("type") != 0:
                    continue

                lines = b.get("lines", [])
                if not lines:
                    continue

                # Analyze lines and spans in this block
                block_text_lines = []
                block_font_sizes = []
                block_is_bold_flags = []

                for line in lines:
                    line_spans = line.get("spans", [])
                    line_text = "".join(span.get("text", "") for span in line_spans)
                    if line_text.strip():
                        block_text_lines.append(line_text.strip())

                    for span in line_spans:
                        text = span.get("text", "").strip()
                        if text:
                            sz = round(span.get("size", 11.0), 1)
                            font_name = span.get("font", "").lower()
                            flags = span.get("flags", 0)
                            # Flags: bit 4 is bold
                            is_bold = bool(flags & 16) or ("bold" in font_name) or ("black" in font_name) or ("heavy" in font_name)
                            block_font_sizes.append(sz)
                            block_is_bold_flags.append(is_bold)
                            font_sizes.append(sz)
                            self.font_stats[sz] += len(text)

                combined_text = "\n".join(block_text_lines).strip()
                if not combined_text:
                    continue

                avg_font_size = (
                    sum(block_font_sizes) / len(block_font_sizes)
                    if block_font_sizes
                    else 11.0
                )
                is_mostly_bold = (
                    sum(1 for f in block_is_bold_flags if f) > (len(block_is_bold_flags) / 2)
                    if block_is_bold_flags
                    else False
                )

                # Determine list types and extract individual list items
                b_type = BlockType.PARAGRAPH
                bullet_items = None

                bullet_count = sum(1 for line in block_text_lines if self.BULLET_REGEX.match(line))
                numbered_count = sum(1 for line in block_text_lines if self.NUMBERED_LIST_REGEX.match(line))

                if bullet_count > 0:
                    b_type = BlockType.BULLET_LIST
                    # Clean the bullet marker from each line
                    bullet_items = []
                    current_item = ""
                    for line in block_text_lines:
                        if self.BULLET_REGEX.match(line):
                            if current_item:
                                bullet_items.append(current_item.strip())
                            current_item = self.BULLET_REGEX.sub("", line).strip()
                        else:
                            if current_item:
                                current_item += " " + line.strip()
                            else:
                                current_item = line.strip()
                    if current_item:
                        bullet_items.append(current_item.strip())

                elif numbered_count > 0:
                    b_type = BlockType.NUMBERED_LIST
                    bullet_items = [self.NUMBERED_LIST_REGEX.sub("", line).strip() for line in block_text_lines]

                bbox = tuple(b.get("bbox", (0.0, 0.0, 0.0, 0.0)))
                block_id = f"p{page_num}_b{b_idx}"

                raw_blocks.append(
                    DocumentBlock(
                        block_id=block_id,
                        page_num=page_num,
                        bbox=bbox,
                        block_type=b_type,
                        text=combined_text,
                        font_size=avg_font_size,
                        is_bold=is_mostly_bold,
                        bullet_items=bullet_items,
                    )
                )

        # 2. Compute body font size (most frequent font size by character count)
        if self.font_stats:
            self.body_font_size = self.font_stats.most_common(1)[0][0]
        else:
            self.body_font_size = 11.0

        # 3. Sort blocks by reading order: page, y0, x0
        raw_blocks.sort(key=lambda x: (x.page_num, round(x.bbox[1], 1), round(x.bbox[0], 1)))

        # 4. Tag headers and footers using position & frequency analysis
        cleaner = HeaderFooterCleaner()
        self.blocks = cleaner.analyze_and_tag(raw_blocks, self.page_heights)

        return self.blocks
