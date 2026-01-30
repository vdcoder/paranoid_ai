"""FastAPI application for Paranoid AI OCR cleaning service."""

from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Path as FastAPIPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from paranoid_ai import __version__
from paranoid_ai.counties import get_county_data_url, get_county_lookup, set_county_data_url
from paranoid_ai.api_models import CountyLookupRequest, HealthResponse, OCRInput, OCRResponse, get_settings
from paranoid_ai.service import OCRCleaningService

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

settings = get_settings()
service = OCRCleaningService(settings)

app = FastAPI(
    title="Paranoid AI",
    description="OCR text cleaning with LLM and paranoid validation",
    version=__version__,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    thisDir = Path(__file__).resolve().parent
    with open(thisDir / "index.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{{ version }}", __version__)
    return HTMLResponse(html.replace("{{ provider }}", settings.llm_provider.upper()))


@app.post("/api/v1/clean", response_model=OCRResponse)
async def clean_ocr(data: OCRInput) -> OCRResponse:
    """Clean OCR text using LLM and validate with paranoid checks."""
    try:
        return await service.process_ocr_text(data.raw_text, data.context, data.validation_rules)
    except Exception as e:
        logger.error("clean_failed", error=str(e))
        raise HTTPException(500, f"Processing failed: {e}")


@app.get("/api/v1/counties/status")
async def counties_status() -> dict:
    """Get county data loading status."""
    return {"url": get_county_data_url(), **get_county_lookup().get_stats()}


@app.post("/api/v1/counties/load")
async def counties_load(url: str | None = None) -> dict:
    """Load county FIPS data from Census Bureau (or custom URL)."""
    try:
        return await get_county_lookup().load(url)
    except Exception as e:
        raise HTTPException(500, f"Failed to load: {e}")


@app.put("/api/v1/counties/url")
async def counties_set_url(url: str) -> dict:
    """Set custom URL for county data."""
    set_county_data_url(url)
    return {"success": True, "url": url}


@app.post("/api/v1/counties/lookup")
async def counties_lookup(req: CountyLookupRequest) -> dict:
    """Look up county FIPS code with fuzzy matching."""
    lookup = get_county_lookup()
    if not lookup.is_loaded:
        raise HTTPException(400, "County data not loaded. POST /api/v1/counties/load first.")
    return lookup.lookup_with_variations(req.state, req.county, req.ai_variations)


@app.get("/api/v1/counties/{state}")
async def counties_by_state(state: str = FastAPIPath(..., min_length=2, max_length=2)) -> dict:
    """Get all counties for a state."""
    lookup = get_county_lookup()
    if not lookup.is_loaded:
        raise HTTPException(400, "County data not loaded.")
    counties = lookup.get_all_counties_for_state(state.upper())
    if not counties:
        raise HTTPException(404, f"State '{state}' not found")
    return {"state": state.upper(), "count": len(counties), "counties": counties}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version=__version__, llm_provider=settings.llm_provider)
