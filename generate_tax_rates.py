"""Generate county tax rates JSON file with random tax rates for all FIPS codes."""

import asyncio
import json
import random
from pathlib import Path

from paranoid_ai.counties import get_county_lookup


async def generate_tax_rates_json():
    """Generate a JSON file mapping FIPS codes to random tax rates."""
    
    # Load county data
    lookup = get_county_lookup()
    await lookup.load()
    
    print(f"Loaded {lookup.county_count} counties from {lookup.source_url}")
    
    # Collect all unique FIPS codes
    fips_codes = set()
    
    for state, counties in lookup._data.items():
        for county_name, fips in counties.items():
            fips_codes.add(fips)
    
    print(f"Found {len(fips_codes)} unique FIPS codes")
    
    # Generate random tax rates (between 0.005 and 0.025 - typical property tax range)
    # Using 3 decimal places like their example (0.012, 0.011, 0.010)
    tax_rates = []
    
    for fips in sorted(fips_codes):
        tax_rate = round(random.uniform(0.005, 0.025), 3)
        tax_rates.append({
            "id": fips,
            "tax_rate": tax_rate
        })
    
    # Sort by FIPS code for consistency
    tax_rates.sort(key=lambda x: x["id"])
    
    # Write to JSON file
    output_path = Path(__file__).parent / "data" / "county_tax_rates.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(tax_rates, f, indent=2)
    
    print(f"\nGenerated {len(tax_rates)} tax rate entries")
    print(f"Written to: {output_path}")
    
    # Show sample
    print("\n=== Sample entries ===")
    for entry in tax_rates[:10]:
        print(f"  {entry}")
    
    print("\n...")
    
    for entry in tax_rates[-5:]:
        print(f"  {entry}")
    
    # Stats
    rates = [e["tax_rate"] for e in tax_rates]
    print(f"\n=== Stats ===")
    print(f"  Min rate: {min(rates):.3f}")
    print(f"  Max rate: {max(rates):.3f}")
    print(f"  Avg rate: {sum(rates)/len(rates):.3f}")


if __name__ == "__main__":
    asyncio.run(generate_tax_rates_json())
