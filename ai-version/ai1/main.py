import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.llm.schema import EnrichmentResponse
from src.llm.service import LLMProviderError, enrich_record, stub_response

load_dotenv()

app = FastAPI()


@app.post("/enrich", response_model=EnrichmentResponse)
async def enrich(request: Request):
    if os.getenv("LLM_ENABLED", "true").lower() == "false":
        return JSONResponse(
            status_code=503,
            content={"error": "LLM enrichment disabled"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "body"})

    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "body"})

    title = body.get("title")
    description = body.get("description", "")
    price_gbp = body.get("price_gbp", 0.0)

    if not isinstance(title, str) or not title.strip():
        return JSONResponse(status_code=400, content={"error": "title"})
    if len(title.strip()) > 300:
        return JSONResponse(status_code=400, content={"error": "title"})

    if not isinstance(description, str) or len(description) > 6000:
        return JSONResponse(status_code=400, content={"error": "description"})

    if (
        isinstance(price_gbp, bool)
        or not isinstance(price_gbp, (int, float))
        or price_gbp < 0
    ):
        return JSONResponse(status_code=400, content={"error": "price_gbp"})

    record = {
        "title": title.strip(),
        "description": description,
        "price_gbp": float(price_gbp),
    }

    if os.getenv("LLM_STUB", "0") == "1":
        return stub_response(record)

    try:
        result = await enrich_record(record)
        return result
    except LLMProviderError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
