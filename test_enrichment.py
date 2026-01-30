"""Test the full OCR pipeline with county enrichment."""

import httpx
import json

# Sample OCR text
ocr_text = """*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara | State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-20
Grantor: T.E.S.L.A. Holdings LLC
Grantee: John & Sarah Connor
Amount: $1,250,000.00 (One Million Two Hundred Fifty Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***"""

print("=== Testing Full OCR Pipeline with County Enrichment ===\n")

# Make request
response = httpx.post(
    "http://127.0.0.1:8000/api/v1/clean",
    json={"raw_text": ocr_text},
    timeout=60,
)

print(f"Status: {response.status_code}\n")

data = response.json()

print("=== Cleaned Data ===")
print(f"Confidence: {data['cleaned_data']['confidence']}")
print("\nExtracted Fields:")
for key, value in data['cleaned_data']['extracted_fields'].items():
    print(f"  {key}: {value}")

print("\n=== County Enrichment ===")
enrichment = data['cleaned_data'].get('county_enrichment')
if enrichment:
    print(f"  State: {enrichment['state']}")
    print(f"  County: {enrichment['county']}")
    print(f"  FIPS Code: {enrichment['fips_code']}")
    print(f"  Match Type: {enrichment['fips_match_type']}")
    print(f"  Tax Rate: {enrichment['tax_rate']}")
    if enrichment.get('enrichment_error'):
        print(f"  Error: {enrichment['enrichment_error']}")
else:
    print("  No enrichment data")

print("\n=== Validation ===")
print(f"  Is Valid: {data['validation']['is_valid']}")
if data['validation']['errors']:
    print("  Errors:")
    for e in data['validation']['errors']:
        print(f"    - {e}")
if data['validation']['warnings']:
    print("  Warnings:")
    for w in data['validation']['warnings']:
        print(f"    - {w}")

print(f"\n=== Processing Time: {data['processing_time_ms']:.2f}ms ===")
