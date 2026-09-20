"""
Australia Therapeutic Goods Administration (TGA) package.
"""
from app.sources.australia_tga.crawler import AustraliaTGACrawler, tga_crawler
from app.sources.australia_tga.adapter import AustraliaTGAAdapter, tga_adapter
from app.sources.australia_tga.search import TGASearchEngine
from app.sources.australia_tga.product_page import TGAProductPageHandler
from app.sources.australia_tga.product_information import TGAProductInformationDiscoverer
from app.sources.australia_tga.version_selector import TGAVersionSelector
from app.sources.australia_tga.pdf_handler import TGAPDFHandler
from app.sources.australia_tga.section_extractor import TGASectionExtractor
from app.sources.australia_tga.table_extractor import TGATableExtractor
from app.sources.australia_tga.date_parser import TGADateParser
from app.sources.australia_tga.validators import TGAValidator
from app.sources.australia_tga.config import SOURCE_ID, TGA_BASE_URL, TGA_SEARCH_URL

__all__ = [
    "AustraliaTGACrawler",
    "tga_crawler",
    "AustraliaTGAAdapter",
    "tga_adapter",
    "TGASearchEngine",
    "TGAProductPageHandler",
    "TGAProductInformationDiscoverer",
    "TGAVersionSelector",
    "TGAPDFHandler",
    "TGASectionExtractor",
    "TGATableExtractor",
    "TGADateParser",
    "TGAValidator",
    "SOURCE_ID",
    "TGA_BASE_URL",
    "TGA_SEARCH_URL",
]
