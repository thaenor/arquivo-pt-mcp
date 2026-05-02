"""Pydantic models for tool parameter validation."""

from pydantic import BaseModel, Field


class SearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None


class ImageSearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None
    image_type: str | None = None


class ListVersionsParams(BaseModel):
    url: str
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class GetSnapshotParams(BaseModel):
    url: str
    timestamp: str | None = None


class ExtractTextParams(BaseModel):
    url: str
    timestamp: str | None = None
    max_chars: int = Field(default=8000, ge=500, le=50000)
