"""Test the multi-layer county matching system."""

import asyncio
from paranoid_ai.counties import get_county_lookup, FUZZY_MATCH_THRESHOLD


async def test_matching_layers():
    """Test all layers of the county matching system."""
    
    lookup = get_county_lookup()
    await lookup.load()
    
    print("=" * 70)
    print("MULTI-LAYER COUNTY MATCHING TEST")
    print(f"Fuzzy Match Threshold: {FUZZY_MATCH_THRESHOLD}%")
    print("=" * 70)
    
    test_cases = [
        # (state, county, ai_variations, expected_match_type)
        ("CA", "Santa Clara", None, "Layer 1: Exact match"),
        ("CA", "S. Clara", None, "Layer 2: Abbreviation expansion"),
        ("CA", "Xanta Klara", ["Santa Clara", "San Clara"], "Layer 3a: AI variation"),
        ("CA", "Sta Klara", ["Sta. Clara"], "Layer 3b: AI + abbreviation"),
        ("CA", "Sonta Claro", None, "Layer 4: Fuzzy match"),
        ("TX", "Ft. Bend", None, "Layer 2: Fort Bend expansion"),
        ("MO", "St. Louis", None, "Layer 1: Exact (already in variations)"),
        ("LA", "Orleans Parish", None, "Layer 1: Exact with Parish"),
        ("CA", "Alamida", None, "Layer 4: Fuzzy (Alameda typo)"),
        ("NY", "New Yrok", None, "Layer 4: Fuzzy (New York typo)"),
    ]
    
    print()
    for state, county, ai_vars, description in test_cases:
        result = lookup.lookup_with_variations(state, county, ai_vars)
        
        fips = result.get("fips_code", "NOT FOUND")
        match_type = result.get("match_type", "?")
        score = result.get("match_score", "")
        matched = result.get("matched_name", "")
        
        score_str = f" ({score}%)" if score and match_type == "fuzzy" else ""
        
        print(f"📍 {description}")
        print(f"   Input: '{county}', {state}")
        if ai_vars:
            print(f"   AI Variations: {ai_vars}")
        print(f"   → FIPS: {fips} | Match: {match_type}{score_str}")
        if matched and matched != county:
            print(f"   → Matched as: '{matched}'")
        print()
    
    print("=" * 70)
    print("MATCHING STRATEGY TRACE EXAMPLE")
    print("=" * 70)
    
    # Show detailed trace
    result = lookup.lookup_with_variations(
        "CA", 
        "Snta Klara",  # Intentionally misspelled
        ["Santa Klara", "Sta Clara"]  # AI suggestions also imperfect
    )
    
    print(f"\nInput: 'Snta Klara', CA")
    print(f"AI Variations: ['Santa Klara', 'Sta Clara']")
    print(f"\nMatching Strategy Trace:")
    for step in result.get("matching_strategy", []):
        print(f"   {step}")
    print(f"\nResult: FIPS={result['fips_code']}, Type={result['match_type']}, Score={result.get('match_score')}")
    print(f"Matched as: {result.get('matched_name')}")


if __name__ == "__main__":
    asyncio.run(test_matching_layers())
