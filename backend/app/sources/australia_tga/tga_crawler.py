"""
Australia Therapeutic Goods Administration (TGA) Crawler compatibility module.
Maintains backward compatibility by exporting AustraliaTGACrawler and tga_crawler.
"""
from app.sources.australia_tga.crawler import AustraliaTGACrawler, tga_crawler

__all__ = ["AustraliaTGACrawler", "tga_crawler"]
