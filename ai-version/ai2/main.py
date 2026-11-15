from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from src.llm.schema import EnrichResponse, CategoryEnum, QualityFlagEnum
from src.llm.service import enrich_book
import os
import json
import time
from datetime import datetime

app = FastAPI(title="Book Enrichment API")

class EnrichRequest(BaseModel):
    title: str
    description: str = ""
    price_gbp: float = 0.0

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title must not be empty after strip")
        if len(stripped) > 300:
            raise ValueError("title must be at most 300 characters")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if len(v) > 6000:
            raise ValueError("description must be at most 6000 characters")
        return v

    @field_validator("price_gbp")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("price_gbp must be >= 0")
        return v


@app.post("/enrich", response_model=EnrichResponse)
async def enrich_endpoint(request: EnrichRequest):
    llm_enabled = os.getenv("LLM_ENABLED", "true").lower() == "true"
    if not llm_enabled:
        return JSONResponse(
            status_code=503,
            content={"error": "LLM service disabled", "code": "LLM_DISABLED"}
        )

    try:
        result = await enrich_book(
            title=request.title,
            description=request.description,
            price_gbp=request.price_gbp
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {str(e)}")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail} if isinstance(exc.detail, str) else exc.detail
    )
