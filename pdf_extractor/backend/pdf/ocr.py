import shutil
import io
import fitz
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

try:
    import pytesseract
    from pytesseract import Output
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    Output = None

from backend.config import TESSERACT_CMD, OCR_LANGUAGE


class OCRProcessor:
    """Handles OCR processing for scanned/image-only PDFs."""

    def __init__(self, tesseract_cmd: Optional[str] = None, lang: str = OCR_LANGUAGE):
        self.lang = lang
        self.tesseract_cmd = tesseract_cmd or TESSERACT_CMD
        if self.tesseract_cmd and PYTESSERACT_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def is_engine_available(self) -> bool:
        """Checks whether the Tesseract binary is available on the system."""
        if not PYTESSERACT_AVAILABLE:
            return False
        if self.tesseract_cmd and shutil.which(self.tesseract_cmd):
            return True
        return shutil.which("tesseract") is not None

    def ocr_page(self, page: fitz.Page, dpi: int = 200) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Runs OCR on a single PyMuPDF page.
        Returns:
            full_text: concatenated recognized text
            line_blocks: list of dicts with text, bbox, and confidence
        """
        if not self.is_engine_available():
            # Return empty with warning if engine is missing
            return "", []

        # Render page to image
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_bytes))

        # Run OCR with layout details
        data = pytesseract.image_to_data(pil_img, lang=self.lang, output_type=Output.DICT)
        
        # Scale factors from image pixels back to PDF points (72 points/inch)
        scale_x = page.rect.width / pix.width
        scale_y = page.rect.height / pix.height

        blocks: Dict[int, List[Dict[str, Any]]] = {}
        n_boxes = len(data["text"])
        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])
            if text and conf > 30:
                block_num = data["block_num"][i]
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                bbox = (
                    x * scale_x,
                    y * scale_y,
                    (x + w) * scale_x,
                    (y + h) * scale_y,
                )
                if block_num not in blocks:
                    blocks[block_num] = []
                blocks[block_num].append({
                    "text": text,
                    "bbox": bbox,
                    "conf": conf,
                    "height": h * scale_y,
                })

        # Group words into blocks
        line_blocks = []
        full_text_parts = []
        for b_num, words in blocks.items():
            if not words:
                continue
            b_text = " ".join(w["text"] for w in words)
            x0 = min(w["bbox"][0] for w in words)
            y0 = min(w["bbox"][1] for w in words)
            x1 = max(w["bbox"][2] for w in words)
            y1 = max(w["bbox"][3] for w in words)
            avg_h = sum(w["height"] for w in words) / len(words)
            line_blocks.append({
                "text": b_text,
                "bbox": (x0, y0, x1, y1),
                "font_size": avg_h,
                "is_bold": False,
                "confidence": sum(w["conf"] for w in words) / len(words)
            })
            full_text_parts.append(b_text)

        return "\n".join(full_text_parts), line_blocks
