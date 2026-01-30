"""Test OCR pipeline with validation errors."""

import httpx

ocr = """*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara | State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor: TESLA Holdings
Grantee: John Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
*** END ***"""

r = httpx.post('http://127.0.0.1:8000/api/v1/clean', json={'raw_text': ocr}, timeout=60)
d = r.json()

print('=== County Enrichment ===')
e = d['cleaned_data']['county_enrichment']
print(f"  FIPS: {e['fips_code']} | Tax Rate: {e['tax_rate']}")

print()
print('=== Validation Errors (Panic Mode!) ===')
print(f"  Is Valid: {d['validation']['is_valid']}")
for err in d['validation']['errors']:
    print(f'  - {err}')
