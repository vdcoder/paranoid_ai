"""County lookup module with real-time Census data fetching."""

import csv
import re
from functools import lru_cache
from io import StringIO
from typing import Any

import httpx
import structlog
from rapidfuzz import fuzz, process

from paranoid_ai.config import get_settings

logger = structlog.get_logger()

# Default Census Bureau URL for county data
DEFAULT_COUNTY_DATA_URL = (
    "https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt"
)

# Module-level URL override (can be set via API)
_custom_url: str | None = None

# Fuzzy matching threshold (0-100) - minimum score to accept a match
# 80% is lenient enough to catch OCR typos but strict enough to avoid false positives
FUZZY_MATCH_THRESHOLD = 80


class CountyLookup:
    """
    County FIPS code lookup with fuzzy matching support.
    
    Fetches data from Census Bureau and provides lookup with AI-assisted
    variation matching for OCR-corrupted county names.
    """

    def __init__(self):
        """Initialize empty county lookup. Call load() to fetch data."""
        self._data: dict[str, dict[str, str]] = {}  # {state: {county_name: fips}}
        self._variations: dict[str, dict[str, str]] = {}  # {state: {variation: canonical}}
        self._loaded = False
        self._source_url: str | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if county data has been loaded."""
        return self._loaded

    @property
    def source_url(self) -> str | None:
        """Get the URL from which data was loaded."""
        return self._source_url

    @property
    def county_count(self) -> int:
        """Get total number of counties loaded."""
        return sum(len(counties) for counties in self._data.values())

    async def load(self, url: str | None = None) -> dict[str, Any]:
        """
        Load county data from Census Bureau or custom URL.
        
        Args:
            url: Optional custom URL. Uses default Census URL if not provided.
            
        Returns:
            dict with load statistics
        """
        url = url or _custom_url or DEFAULT_COUNTY_DATA_URL
        self._source_url = url
        
        logger.info("loading_county_data", url=url)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
            content = response.text
            self._parse_census_data(content)
            self._build_variations()
            self._loaded = True
            
            stats = {
                "success": True,
                "source_url": url,
                "states_loaded": len(self._data),
                "counties_loaded": self.county_count,
            }
            
            logger.info("county_data_loaded", **stats)
            return stats
            
        except Exception as e:
            logger.error("county_data_load_failed", url=url, error=str(e))
            raise

    def _parse_census_data(self, content: str) -> None:
        """
        Parse Census Bureau pipe-delimited county data.
        
        Format: STATE|STATEFP|COUNTYFP|COUNTYNS|COUNTYNAME|CLASSFP|FUNCSTAT
        Example: AL|01|001|00161526|Autauga County|H1|A
        """
        self._data.clear()
        
        reader = csv.DictReader(StringIO(content), delimiter="|")
        
        for row in reader:
            state = row.get("STATE", "").strip()
            state_fp = row.get("STATEFP", "").strip()
            county_fp = row.get("COUNTYFP", "").strip()
            county_name = row.get("COUNTYNAME", "").strip()
            
            if not all([state, state_fp, county_fp, county_name]):
                continue
            
            # FIPS code is state + county (e.g., "01" + "001" = "01001")
            fips = f"{state_fp}{county_fp}"
            
            # Normalize county name (remove "County", "Parish", etc.)
            canonical_name = self._normalize_county_name(county_name)
            
            if state not in self._data:
                self._data[state] = {}
            
            # Store both original and normalized names
            self._data[state][canonical_name] = fips
            self._data[state][county_name] = fips  # Keep original too

    def _normalize_county_name(self, name: str) -> str:
        """
        Normalize county name by removing common suffixes.
        
        "Santa Clara County" -> "Santa Clara"
        "Orleans Parish" -> "Orleans"
        """
        # Common suffixes to remove
        suffixes = [
            r"\s+County$",
            r"\s+Parish$",
            r"\s+Borough$",
            r"\s+Census Area$",
            r"\s+Municipality$",
            r"\s+city$",  # Virginia independent cities
        ]
        
        result = name
        for suffix in suffixes:
            result = re.sub(suffix, "", result, flags=re.IGNORECASE)
        
        return result.strip()

    def _build_variations(self) -> None:
        """
        Build common variations/abbreviations for county names.
        
        This helps match OCR errors and abbreviations:
        - "S. Clara" -> "Santa Clara"
        - "St. Louis" -> "Saint Louis"
        - "Ft. Worth" -> "Fort Worth"
        """
        self._variations.clear()
        
        abbreviation_map = {
            "Saint": ["St.", "St", "Ste.", "Ste"],
            "Fort": ["Ft.", "Ft"],
            "Mount": ["Mt.", "Mt"],
            "North": ["N.", "N"],
            "South": ["S.", "S"],
            "East": ["E.", "E"],
            "West": ["W.", "W"],
            "San": ["S."],
            "Santa": ["S.", "Sta.", "Sta"],
            "Los": ["L."],
        }
        
        for state, counties in self._data.items():
            if state not in self._variations:
                self._variations[state] = {}
            
            for county_name, fips in counties.items():
                # Add lowercase version
                self._variations[state][county_name.lower()] = county_name
                
                # Generate abbreviation variations
                for full_word, abbrevs in abbreviation_map.items():
                    if full_word in county_name:
                        for abbrev in abbrevs:
                            variation = county_name.replace(full_word, abbrev)
                            self._variations[state][variation.lower()] = county_name

    def lookup(self, state: str, county: str) -> str | None:
        """
        Look up FIPS code for a county.
        
        Args:
            state: Two-letter state code (e.g., "CA")
            county: County name (can be normalized or have variations)
            
        Returns:
            FIPS code string or None if not found
        """
        if not self._loaded:
            logger.warning("county_lookup_not_loaded")
            return None
        
        state = state.upper().strip()
        
        if state not in self._data:
            return None
        
        # Try exact match first
        if county in self._data[state]:
            return self._data[state][county]
        
        # Try normalized version
        normalized = self._normalize_county_name(county)
        if normalized in self._data[state]:
            return self._data[state][normalized]
        
        # Try variations
        if state in self._variations:
            county_lower = county.lower()
            if county_lower in self._variations[state]:
                canonical = self._variations[state][county_lower]
                return self._data[state].get(canonical)
        
        return None

    def lookup_with_variations(
        self, state: str, county: str, ai_variations: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Look up FIPS code using a multi-layer matching strategy.
        
        Matching Pipeline:
        1. Try cleaned county name directly (exact match)
        2. Try our abbreviation variations on the cleaned name
        3. For each AI-suggested variation:
           a. Try exact match
           b. Apply our abbreviation fixes, then try
        4. Fuzzy match as final fallback (rapidfuzz)
        
        Args:
            state: Two-letter state code
            county: County name from OCR (cleaned by AI)
            ai_variations: AI-suggested variations of the county name
            
        Returns:
            dict with lookup result and detailed match info
        """
        result = {
            "input_state": state,
            "input_county": county,
            "fips_code": None,
            "matched_name": None,
            "match_type": None,
            "match_score": None,  # For fuzzy matches
            "variations_tried": [],
            "matching_strategy": [],  # Log of what we tried
        }
        
        state = state.upper().strip()
        
        if state not in self._data:
            result["match_type"] = "state_not_found"
            return result
        
        # =====================================================
        # Layer 1: Try cleaned county name directly
        # =====================================================
        result["matching_strategy"].append(f"L1: Exact match '{county}'")
        fips = self.lookup(state, county)
        if fips:
            result["fips_code"] = fips
            result["matched_name"] = county
            result["match_type"] = "exact"
            result["match_score"] = 100
            logger.info("county_matched", layer=1, strategy="exact", county=county)
            return result
        
        result["variations_tried"].append(county)
        
        # =====================================================
        # Layer 2: Try our abbreviation variations on cleaned name
        # =====================================================
        our_variations = self._generate_abbreviation_variations(county)
        for variation in our_variations:
            result["matching_strategy"].append(f"L2: Abbreviation variation '{variation}'")
            fips = self.lookup(state, variation)
            if fips:
                result["fips_code"] = fips
                result["matched_name"] = variation
                result["match_type"] = "abbreviation_expansion"
                result["match_score"] = 100
                logger.info("county_matched", layer=2, strategy="abbreviation", 
                           original=county, matched=variation)
                return result
            result["variations_tried"].append(variation)
        
        # =====================================================
        # Layer 3: Try AI-suggested variations
        # =====================================================
        if ai_variations:
            for ai_var in ai_variations:
                # 3a: Try AI variation directly
                result["matching_strategy"].append(f"L3a: AI variation '{ai_var}'")
                fips = self.lookup(state, ai_var)
                if fips:
                    result["fips_code"] = fips
                    result["matched_name"] = ai_var
                    result["match_type"] = "ai_variation"
                    result["match_score"] = 100
                    logger.info("county_matched", layer=3, strategy="ai_direct", 
                               original=county, matched=ai_var)
                    return result
                result["variations_tried"].append(ai_var)
                
                # 3b: Apply our abbreviation fixes to AI variation
                ai_var_expansions = self._generate_abbreviation_variations(ai_var)
                for expansion in ai_var_expansions:
                    if expansion not in result["variations_tried"]:
                        result["matching_strategy"].append(f"L3b: AI+abbrev '{expansion}'")
                        fips = self.lookup(state, expansion)
                        if fips:
                            result["fips_code"] = fips
                            result["matched_name"] = expansion
                            result["match_type"] = "ai_variation_expanded"
                            result["match_score"] = 100
                            logger.info("county_matched", layer=3, strategy="ai_expanded",
                                       original=county, ai_var=ai_var, matched=expansion)
                            return result
                        result["variations_tried"].append(expansion)
        
        # =====================================================
        # Layer 4: Fuzzy matching as final fallback
        # =====================================================
        result["matching_strategy"].append(f"L4: Fuzzy match (threshold={FUZZY_MATCH_THRESHOLD}%)")
        fuzzy_result = self._fuzzy_match(state, county)
        
        if fuzzy_result:
            result["fips_code"] = fuzzy_result["fips"]
            result["matched_name"] = fuzzy_result["matched_name"]
            result["match_type"] = "fuzzy"
            result["match_score"] = fuzzy_result["score"]
            logger.info("county_matched", layer=4, strategy="fuzzy",
                       original=county, matched=fuzzy_result["matched_name"],
                       score=fuzzy_result["score"])
            return result
        
        # Nothing worked
        result["match_type"] = "not_found"
        logger.warning("county_not_found", state=state, county=county,
                      variations_tried=len(result["variations_tried"]))
        return result

    def _generate_abbreviation_variations(self, name: str) -> list[str]:
        """
        Generate possible variations by expanding/contracting abbreviations.
        
        "S. Clara" -> ["Santa Clara", "San Clara", "South Clara"]
        "Saint Louis" -> ["St. Louis", "St Louis"]
        """
        variations = []
        
        # Expansion map: abbreviation -> possible full words
        expansion_map = {
            "S.": ["Santa", "San", "South"],
            "S ": ["Santa ", "San ", "South "],
            "St.": ["Saint", "St"],
            "St ": ["Saint ", "St "],
            "Ste.": ["Sainte"],
            "Ft.": ["Fort"],
            "Ft ": ["Fort "],
            "Mt.": ["Mount"],
            "Mt ": ["Mount "],
            "N.": ["North"],
            "N ": ["North "],
            "E.": ["East"],
            "E ": ["East "],
            "W.": ["West"],
            "W ": ["West "],
            "Sta.": ["Santa"],
            "Sta ": ["Santa "],
            "L.": ["Los"],
        }
        
        # Contraction map: full word -> abbreviations
        contraction_map = {
            "Santa": ["S.", "Sta.", "Sta"],
            "San": ["S."],
            "South": ["S."],
            "Saint": ["St.", "St"],
            "Sainte": ["Ste."],
            "Fort": ["Ft.", "Ft"],
            "Mount": ["Mt.", "Mt"],
            "North": ["N.", "N"],
            "East": ["E.", "E"],
            "West": ["W.", "W"],
            "Los": ["L."],
        }
        
        # Try expansions
        for abbrev, expansions in expansion_map.items():
            if abbrev in name:
                for expansion in expansions:
                    variation = name.replace(abbrev, expansion, 1)
                    if variation != name and variation not in variations:
                        variations.append(variation)
        
        # Try contractions
        for full_word, contractions in contraction_map.items():
            if full_word in name:
                for contraction in contractions:
                    variation = name.replace(full_word, contraction, 1)
                    if variation != name and variation not in variations:
                        variations.append(variation)
        
        return variations

    def _fuzzy_match(self, state: str, county: str) -> dict[str, Any] | None:
        """
        Perform fuzzy matching against all counties in a state.
        
        Uses rapidfuzz for fast Levenshtein-based matching.
        Only returns a match if score >= FUZZY_MATCH_THRESHOLD.
        """
        if state not in self._data:
            return None
        
        # Get all county names for this state
        county_names = list(self._data[state].keys())
        
        if not county_names:
            return None
        
        # Use rapidfuzz to find best match
        # We use token_set_ratio which handles word order and partial matches well
        best_match = process.extractOne(
            county,
            county_names,
            scorer=fuzz.token_set_ratio,
            score_cutoff=FUZZY_MATCH_THRESHOLD
        )
        
        if best_match:
            matched_name, score, _ = best_match
            fips = self._data[state].get(matched_name)
            
            logger.debug("fuzzy_match_found", 
                        query=county, matched=matched_name, 
                        score=score, threshold=FUZZY_MATCH_THRESHOLD)
            
            return {
                "matched_name": matched_name,
                "score": score,
                "fips": fips,
            }
        
        logger.debug("fuzzy_match_failed", 
                    query=county, threshold=FUZZY_MATCH_THRESHOLD,
                    best_candidates=process.extract(county, county_names, limit=3))
        
        return None

    def get_all_counties_for_state(self, state: str) -> list[str]:
        """Get all county names for a state (for AI context)."""
        state = state.upper().strip()
        if state not in self._data:
            return []
        
        # Return unique normalized names
        return sorted(set(
            self._normalize_county_name(name) 
            for name in self._data[state].keys()
        ))

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about loaded data."""
        return {
            "loaded": self._loaded,
            "source_url": self._source_url,
            "states": len(self._data),
            "counties": self.county_count,
            "counties_by_state": {
                state: len(counties) 
                for state, counties in sorted(self._data.items())
            } if self._loaded else {},
        }


# Global singleton instance
_county_lookup: CountyLookup | None = None


def get_county_lookup() -> CountyLookup:
    """Get the global CountyLookup instance."""
    global _county_lookup
    if _county_lookup is None:
        _county_lookup = CountyLookup()
    return _county_lookup


def set_county_data_url(url: str) -> None:
    """
    Set a custom URL for county data.
    
    This will be used on next load() call.
    """
    global _custom_url
    _custom_url = url
    logger.info("county_data_url_set", url=url)


def get_county_data_url() -> str:
    """Get the current county data URL (custom or default)."""
    return _custom_url or DEFAULT_COUNTY_DATA_URL
