"""Output schema for the /enrich endpoint (W7 · A17).

The contract of the model's answer, written down before any model is called:
closed lists become enums, confidence is bounded, summary is capped at one
sentence. Nothing the model says gets past this module unvalidated.
"""

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    fiction = "fiction"
    poetry = "poetry"
    nonfiction = "nonfiction"
    children = "children"
    academic = "academic"
    other = "other"


class QualityFlag(str, Enum):
    missing_description = "missing_description"
    duplicate_description = "duplicate_description"
    short_description = "short_description"
    suspicious_price = "suspicious_price"
    no_flags = "no_flags"


class Enrichment(BaseModel):
    category: Category
    summary: str = Field(max_length=220)
    quality_flags: list[QualityFlag] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
