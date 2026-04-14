"""Common shared response schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class BaseResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error:   str
    detail:  Optional[str] = None
    code:    Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    items:       List[T]
    total:       int
    page:        int = 1
    page_size:   int = 20
    has_more:    bool = False
