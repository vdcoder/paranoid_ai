"""Tax rate lookup module using FIPS codes."""

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Default path to tax rates JSON
DEFAULT_TAX_RATES_PATH = Path(__file__).parent.parent.parent / "data" / "county_tax_rates.json"


class TaxRateLookup:
    """
    Tax rate lookup by FIPS code.
    
    Loads tax rates from a JSON file and provides fast lookup.
    """

    def __init__(self):
        """Initialize empty lookup. Call load() to load data."""
        self._rates: dict[str, float] = {}  # {fips: tax_rate}
        self._loaded = False
        self._source_path: Path | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if tax rates have been loaded."""
        return self._loaded

    @property
    def rate_count(self) -> int:
        """Get number of tax rates loaded."""
        return len(self._rates)

    def load(self, path: Path | str | None = None) -> dict[str, Any]:
        """
        Load tax rates from JSON file.
        
        Args:
            path: Path to JSON file. Uses default if not provided.
            
        Returns:
            dict with load statistics
        """
        path = Path(path) if path else DEFAULT_TAX_RATES_PATH
        self._source_path = path
        
        logger.info("loading_tax_rates", path=str(path))
        
        try:
            with open(path) as f:
                data = json.load(f)
            
            self._rates.clear()
            
            for entry in data:
                fips = entry.get("id")
                rate = entry.get("tax_rate")
                if fips and rate is not None:
                    self._rates[fips] = float(rate)
            
            self._loaded = True
            
            stats = {
                "success": True,
                "source_path": str(path),
                "rates_loaded": len(self._rates),
            }
            
            logger.info("tax_rates_loaded", **stats)
            return stats
            
        except Exception as e:
            logger.error("tax_rates_load_failed", path=str(path), error=str(e))
            raise

    def lookup(self, fips: str) -> float | None:
        """
        Look up tax rate for a FIPS code.
        
        Args:
            fips: County FIPS code (e.g., "06085" for Santa Clara)
            
        Returns:
            Tax rate as float (e.g., 0.012) or None if not found
        """
        if not self._loaded:
            logger.warning("tax_rates_not_loaded")
            return None
        
        return self._rates.get(fips)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about loaded data."""
        if not self._loaded:
            return {
                "loaded": False,
                "source_path": None,
                "rate_count": 0,
            }
        
        rates = list(self._rates.values())
        return {
            "loaded": True,
            "source_path": str(self._source_path),
            "rate_count": len(rates),
            "min_rate": min(rates) if rates else None,
            "max_rate": max(rates) if rates else None,
            "avg_rate": round(sum(rates) / len(rates), 4) if rates else None,
        }


# Global singleton instance
_tax_rate_lookup: TaxRateLookup | None = None


def get_tax_rate_lookup() -> TaxRateLookup:
    """Get the global TaxRateLookup instance."""
    global _tax_rate_lookup
    if _tax_rate_lookup is None:
        _tax_rate_lookup = TaxRateLookup()
    return _tax_rate_lookup


def ensure_tax_rates_loaded() -> TaxRateLookup:
    """Ensure tax rates are loaded, loading from default path if needed."""
    lookup = get_tax_rate_lookup()
    if not lookup.is_loaded:
        lookup.load()
    return lookup
