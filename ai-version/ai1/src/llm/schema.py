from enum import Enum
from typing import List

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


class EnrichmentResponse(BaseModel):
    category: Category
    summary: str = Field(max_length=220)
    quality_flags: List[QualityFlag] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
