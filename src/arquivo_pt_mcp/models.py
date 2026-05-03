"""Pydantic models for tool parameter validation."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_FILTER_RE = re.compile(r"^[!=~]{1,2}[A-Za-z]+:.+$")


class SearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None
    collection: str | None = None
    mime_type: Literal["pdf", "html", "doc", "xls", "ppt", "rtf"] | None = None
    offset: int = Field(default=0, ge=0)


class ImageSearchParams(BaseModel):
    query: str
    max_items: int = Field(default=10, ge=1, le=50)
    from_date: str | None = None
    to_date: str | None = None
    site_search: str | None = None
    image_type: str | None = None
    size: Literal["small", "medium", "large"] | None = None
    safe_search: Literal["on", "off"] = "on"
    collection: str | None = None
    offset: int = Field(default=0, ge=0)
    more: list[Literal["imgDigest", "pageHost", "pageImages", "safe"]] = Field(
        default_factory=list
    )


class ListVersionsParams(BaseModel):
    url: str
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    compact: bool = False
    filter: list[str] = Field(default_factory=list)
    match_type: Literal["exact", "prefix", "host", "domain"] = "exact"
    from_date: str | None = None
    to_date: str | None = None
    sort: Literal["default", "reverse", "closest"] = "default"
    closest: str | None = None

    @field_validator("filter")
    @classmethod
    def _check_filter_syntax(cls, v: list[str]) -> list[str]:
        bad = [f for f in v if not _FILTER_RE.match(f)]
        if bad:
            raise ValueError(
                f"filter expressions must look like '=field:value' or '~field:regex'; bad: {bad}"
            )
        return v

    @model_validator(mode="after")
    def _closest_implies_closest_sort(self) -> "ListVersionsParams":
        if self.closest and self.sort == "default":
            self.sort = "closest"
        if self.sort == "closest" and not self.closest:
            raise ValueError("sort='closest' requires a 'closest' timestamp")
        return self


class GetSnapshotParams(BaseModel):
    url: str
    timestamp: str | None = None


class ExtractTextParams(BaseModel):
    url: str
    timestamp: str | None = None
    max_chars: int = Field(default=8000, ge=500, le=50000)
