"""FastAPI application for OCR cleaning service."""

import structlog
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from paranoid_ai import __version__
from paranoid_ai.config import get_settings
from paranoid_ai.counties import (
    get_county_data_url,
    get_county_lookup,
    set_county_data_url,
)
from paranoid_ai.models import HealthResponse, OCRInput, OCRResponse
from paranoid_ai.service import OCRCleaningService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="Paranoid AI - OCR Cleaning API",
    description="OCR text cleaning with LLM and paranoid validation",
    version=__version__,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instance
settings = get_settings()
service = OCRCleaningService(settings)


# =============================================
# Pydantic models for County API
# =============================================

class CountyUrlRequest(BaseModel):
    """Request to set county data URL."""
    url: str = Field(..., description="URL to fetch county data from")


class CountyLookupRequest(BaseModel):
    """Request to look up a county FIPS code."""
    state: str = Field(..., min_length=2, max_length=2, description="Two-letter state code (e.g., 'CA')")
    county: str = Field(..., description="County name (can include OCR variations)")
    ai_variations: list[str] | None = Field(
        default=None, description="Optional AI-suggested variations to try"
    )

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.upper().strip()


class StatePathRequest(BaseModel):
    """Validated state path parameter."""
    state: str = Field(..., min_length=2, max_length=2, description="Two-letter state code")

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.upper().strip()


# =============================================
# Health & Core Endpoints
# =============================================

@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    county_lookup = get_county_lookup()
    return HealthResponse(
        status="healthy",
        version=__version__,
        llm_provider=settings.llm_provider,
    )


@app.post("/api/v1/clean", response_model=OCRResponse)
async def clean_ocr_text(input_data: OCRInput) -> OCRResponse:
    """
    Clean OCR text using LLM and validate the results.

    Args:
        input_data: OCR input with raw text and optional context/rules

    Returns:
        OCRResponse with cleaned data and validation results

    Raises:
        HTTPException: If processing fails
    """
    try:
        logger.info("api_request_received", text_length=len(input_data.raw_text))

        result = await service.process_ocr_text(
            raw_text=input_data.raw_text,
            context=input_data.context,
            validation_rules=input_data.validation_rules,
        )

        logger.info("api_request_completed", is_valid=result.validation.is_valid)
        return result

    except Exception as e:
        logger.error("api_request_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


# =============================================
# County Data Management Endpoints
# =============================================

@app.get("/api/v1/counties/status")
async def get_counties_status() -> dict:
    """
    Get status of county data.
    
    Returns information about loaded county data including
    source URL and county counts per state.
    """
    county_lookup = get_county_lookup()
    return {
        "current_url": get_county_data_url(),
        **county_lookup.get_stats(),
    }


@app.post("/api/v1/counties/load")
async def load_counties(url: str | None = None) -> dict:
    """
    Load county data from Census Bureau or custom URL.
    
    If no URL provided, uses the configured default or Census Bureau URL.
    """
    try:
        county_lookup = get_county_lookup()
        result = await county_lookup.load(url)
        return result
    except Exception as e:
        logger.error("county_load_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load county data: {str(e)}")


@app.put("/api/v1/counties/url")
async def set_counties_url(request: CountyUrlRequest) -> dict:
    """
    Set a custom URL for county data.
    
    The new URL will be used on the next load.
    This is useful for using local/cached copies or alternative data sources.
    """
    set_county_data_url(request.url)
    return {
        "success": True,
        "message": f"County data URL set to: {request.url}",
        "note": "Call POST /api/v1/counties/load to reload data from new URL",
    }


@app.post("/api/v1/counties/lookup")
async def lookup_county(request: CountyLookupRequest) -> dict:
    """
    Look up a county FIPS code.
    
    Supports fuzzy matching and AI-suggested variations for OCR errors.
    """
    county_lookup = get_county_lookup()
    
    if not county_lookup.is_loaded:
        raise HTTPException(
            status_code=400,
            detail="County data not loaded. Call POST /api/v1/counties/load first.",
        )
    
    result = county_lookup.lookup_with_variations(
        state=request.state,
        county=request.county,
        ai_variations=request.ai_variations,
    )
    
    return result


@app.get("/api/v1/counties/{state}")
async def get_state_counties(
    state: str = Path(..., min_length=2, max_length=2, description="Two-letter state code"),
) -> dict:
    """
    Get all counties for a state.
    
    Useful for providing context to AI for variation matching.
    """
    state = state.upper().strip()
    county_lookup = get_county_lookup()
    
    if not county_lookup.is_loaded:
        raise HTTPException(
            status_code=400,
            detail="County data not loaded. Call POST /api/v1/counties/load first.",
        )
    
    counties = county_lookup.get_all_counties_for_state(state)
    
    if not counties:
        raise HTTPException(status_code=404, detail=f"State '{state}' not found")
    
    return {
        "state": state.upper(),
        "county_count": len(counties),
        "counties": counties,
    }


# =============================================
# Root & Info Endpoints
# =============================================

@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the Paranoid AI home page."""
    from paranoid_ai.templates import HOME_PAGE_HTML
    
    # Inject version and provider into template
    html = HOME_PAGE_HTML.replace("{{ version }}", __version__)
    html = html.replace("{{ provider }}", settings.llm_provider.upper())
    
    return HTMLResponse(content=html)


@app.get("/api/v1/info")
async def api_info() -> dict[str, str]:
    """API information endpoint (JSON version of root)."""
    return {
        "name": "Paranoid AI - OCR Cleaning API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
        "counties": "/api/v1/counties/status",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "paranoid_ai.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
        log_level=settings.log_level.lower(),
    )
