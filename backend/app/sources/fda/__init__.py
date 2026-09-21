"""
FDA sources namespace.
"""
from app.sources.fda_srlc import adapter as srlc_adapter, crawler as srlc_crawler, fda_srlc_adapter, fda_srlc_crawler
from app.sources.fda_medwatch import adapter as medwatch_adapter_mod, crawler as medwatch_crawler_mod, medwatch_adapter, medwatch_crawler

__all__ = [
    "srlc_adapter",
    "srlc_crawler",
    "fda_srlc_adapter",
    "fda_srlc_crawler",
    "medwatch_adapter_mod",
    "medwatch_crawler_mod",
    "medwatch_adapter",
    "medwatch_crawler",
]
