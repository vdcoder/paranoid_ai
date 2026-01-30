"""Tax rate lookup by FIPS code."""

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()
DEFAULT_PATH = Path(__file__).parent.parent.parent / "data" / "county_tax_rates.json"

class TaxRateLookup:
    """FIPS code to tax rate lookup with JSON file loading."""

    def __init__(self):
        self._rates: dict[str, float] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self, path: Path | str | None = None) -> dict[str, Any]:
        """Load tax rates from JSON file."""
        path = Path(path) if path else DEFAULT_PATH
        logger.info("loading_tax_rates", path=str(path))

        with open(path) as f:
            data = json.load(f)

        self._rates = {e["id"]: float(e["tax_rate"]) for e in data if e.get("id")}
        self._loaded = True
        return {"success": True, "rates_loaded": len(self._rates)}

    def lookup(self, fips: str) -> float | None:
        """Get tax rate for FIPS code."""
        return self._rates.get(fips) if self._loaded else None


_lookup: TaxRateLookup | None = None


def get_tax_rate_lookup() -> TaxRateLookup:
    global _lookup
    if _lookup is None:
        _lookup = TaxRateLookup()
    return _lookup


def ensure_tax_rates_loaded() -> TaxRateLookup:
    lookup = get_tax_rate_lookup()
    if not lookup.is_loaded:
        lookup.load()
    return lookup
