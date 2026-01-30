# 🔍 Paranoid AI

> **Trust, but verify.** An OCR text cleaning service that uses LLM intelligence with code-based validation.

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Anthropic Claude](https://img.shields.io/badge/Anthropic-Claude-orange.svg)](https://www.anthropic.com/)

## Overview

Paranoid AI is a production-ready OCR text cleaning service that combines the power of Large Language Models with **paranoid validation** — we don't just trust the AI, we verify its output with deterministic code.

The system extracts structured data from messy OCR text (property deeds, legal documents, etc.) and validates every field against authoritative sources like the U.S. Census Bureau.

## ✨ Key Features

### 🤖 LLM-Powered Extraction
- Leverages Anthropic Claude for intelligent text cleaning
- Extracts structured fields: amounts, dates, counties, states
- Handles OCR artifacts, typos, and formatting issues

### 🛡️ Paranoid Validation Pipeline
Four layers of verification ensure data integrity:

1. **Amount Verification** — Cross-validates numeric amounts against text representations using `text2num`
2. **Date Logic Checks** — Ensures temporal consistency (e.g., recording date ≥ signing date)
3. **Date Format Validation** — Verifies dates are parseable and not in the future
4. **County Verification** — Validates counties against Census Bureau FIPS codes

### 🗺️ Multi-Layer County Matching
A 4-layer matching strategy handles real-world OCR challenges:

| Layer | Strategy | Example |
|-------|----------|---------|
| L1 | Exact Match | `Santa Clara` → ✅ |
| L2 | Abbreviation Expansion | `S. Clara` → `Santa Clara` → ✅ |
| L3 | AI Variations | LLM suggests `St. Clara`, `Sta Clara` |
| L4 | Fuzzy Match (80%+) | `Alamida` → `Alameda` (85.7%) |

### 💰 Tax Rate Enrichment
Automatic FIPS-to-tax-rate lookup for 3,235+ U.S. counties.

### 📊 Structured Logging
JSON-formatted logs via `structlog` for production observability.

## 🏗️ Architecture

```
src/paranoid_ai/
├── api.py              # FastAPI application & endpoints
├── config.py           # Pydantic settings management
├── models.py           # Request/response models
├── service.py          # Orchestration layer
├── counties.py         # Census Bureau FIPS lookup
├── tax_rates.py        # FIPS → tax rate mapping
├── templates.py        # HTML templates
├── validation/
│   ├── __init__.py
│   └── validator.py    # Paranoid validation logic
└── llm/
    ├── __init__.py
    ├── base.py         # Abstract LLM provider
    ├── anthropic.py    # Anthropic Claude implementation
    └── prompts.py      # Prompt templates
```

## 🚀 Quick Start

### Prerequisites
- Python 3.13+
- Anthropic API key

### Installation

```bash
# Clone and navigate
cd paranoid_ai

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e .
```

### Configuration

Create a `.env` file:

```env
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=anthropic
LOG_LEVEL=INFO
```

### Running the Server

```bash
# Start the API server
python -m uvicorn paranoid_ai.api:app --host 127.0.0.1 --port 8000

# Load Census county data (required for validation)
curl -X POST http://127.0.0.1:8000/api/v1/counties/load
```

Visit `http://127.0.0.1:8000` for the interactive UI, or `http://127.0.0.1:8000/docs` for OpenAPI documentation.

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Interactive web UI |
| `POST` | `/api/v1/clean` | Process OCR text |
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/counties/load` | Load Census data |
| `GET` | `/api/v1/counties/status` | County data status |
| `GET` | `/api/v1/counties/lookup` | Manual FIPS lookup |

## 🧪 Validation Examples

### ✅ Valid Input
```
"Santa Clara County, CA" → FIPS 06085, is_valid: true
```

### ❌ Fake County Rejection
```
"Fakeville County, CA" → is_valid: false
Error: "UNRECOGNIZED COUNTY: 'Fakeville' in state 'CA' could not be found 
in Census data. Tried exact match, abbreviation expansion, AI variations, 
and fuzzy matching (80% threshold)."
```

### ⚠️ Fuzzy Match with Warning
```
"Alamida County, CA" → "Alameda" (85.7% match) → FIPS 06001
```

## 🛠️ Engineering Hygiene

- **Type Safety** — Full type hints with Pydantic v2 validation
- **Async/Await** — Non-blocking I/O throughout
- **Configuration** — Environment-based settings with sensible defaults
- **Structured Logging** — JSON logs for production observability
- **Dependency Injection** — Clean separation of concerns
- **Error Handling** — Graceful degradation with detailed error messages
- **Modern Python** — Python 3.13 with latest idioms

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `pydantic` | Data validation |
| `anthropic` | LLM provider |
| `httpx` | Async HTTP client |
| `structlog` | Structured logging |
| `text2num` | Text-to-number parsing |
| `rapidfuzz` | Fuzzy string matching |
| `python-dotenv` | Environment management |

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

<p align="center">
  <em>Built with 🔐 paranoia by <a href="https://github.com/victordiaz">Victor Diaz</a></em>
</p>
