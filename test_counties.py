"""Test script for county lookup functionality."""

import asyncio
from paranoid_ai.counties import get_county_lookup


async def test():
    lookup = get_county_lookup()
    await lookup.load()
    
    print("\n=== County Lookup Tests ===\n")
    
    # Test various lookups
    tests = [
        ("CA", "Santa Clara County"),       # Exact
        ("CA", "Santa Clara"),               # Normalized
        ("CA", "S. Clara"),                  # Abbreviation variation
        ("CA", "St. Clara"),                 # OCR variation (should NOT match - we want Santa, not Saint)
        ("TX", "Harris County"),             # Houston
        ("TX", "Ft. Bend"),                  # Fort Bend with abbreviation
        ("NY", "New York County"),           # Manhattan
        ("LA", "Orleans Parish"),            # Louisiana parish
        ("MO", "St. Louis"),                 # Saint Louis with abbreviation
        ("CO", "Boulder County"),            # Boulder
    ]
    
    for state, county in tests:
        result = lookup.lookup_with_variations(state, county)
        fips = result["fips_code"] or "NOT FOUND"
        match = result["match_type"]
        matched = result.get("matched_name", "")
        print(f"  {state}, {county:25} -> FIPS: {fips} (match: {match}, name: {matched})")
    
    print("\n=== AI-Assisted Lookup Test ===\n")
    
    # Test with AI-suggested variations (simulated)
    result = lookup.lookup_with_variations(
        state="CA",
        county="S. Clara",  # OCR error
        ai_variations=["Santa Clara", "San Clara", "St. Clara"]  # AI suggestions
    )
    print(f"  Looking up 'S. Clara' with AI variations:")
    print(f"    FIPS: {result['fips_code']}")
    print(f"    Match type: {result['match_type']}")
    print(f"    Matched name: {result['matched_name']}")
    print(f"    Variations tried: {result['variations_tried']}")
    
    print("\n=== All CA Counties ===\n")
    ca_counties = lookup.get_all_counties_for_state("CA")
    print(f"  CA has {len(ca_counties)} counties")
    print(f"  First 5: {ca_counties[:5]}")
    print(f"  Last 5: {ca_counties[-5:]}")


if __name__ == "__main__":
    asyncio.run(test())
