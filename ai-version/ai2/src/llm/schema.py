from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import List


class CategoryEnum(str, Enum):
    fiction = "fiction"
    poetry = "poetry"
    nonfiction = "nonfiction"
    children = "children"
    academic = "academic"
    other = "other"


class QualityFlagEnum(str, Enum):
    missing_description = "missing_description"
    duplicate_description = "duplicate_description"
    short_description = "short_description"
    suspicious_price = "suspicious_price"
    no_flags = "no_flags"


class EnrichResponse(BaseModel):
    category: CategoryEnum
    summary: str = Field(max_length=220)
    quality_flags: List[QualityFlagEnum] = Field(min_length=1, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags(cls, v: List[QualityFlagEnum]) -> List[QualityFlagEnum]:
        if len(v) < 1 or len(v) > 3:
            raise ValueError("quality_flags must have 1-3 items")
        if QualityFlagEnum.no_flags in v and len(v) > 1:
            raise ValueError("no_flags cannot be combined with other flags")
        return v
