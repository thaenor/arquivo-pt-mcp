"""Tests for Pydantic input validation models."""

import pytest
from pydantic import ValidationError

from arquivo_pt_mcp.models import (
    ExtractTextParams,
    GetSnapshotParams,
    ImageSearchParams,
    ListVersionsParams,
    SearchParams,
)


def test_search_params_valid():
    p = SearchParams(query="test")
    assert p.query == "test"
    assert p.max_items == 10


def test_search_params_clamps_max_items():
    with pytest.raises(ValidationError):
        SearchParams(query="test", max_items=0)
    with pytest.raises(ValidationError):
        SearchParams(query="test", max_items=51)


def test_search_params_missing_query():
    with pytest.raises(ValidationError):
        SearchParams()


def test_image_search_params_valid():
    p = ImageSearchParams(query="lisboa")
    assert p.query == "lisboa"
    assert p.max_items == 10
    assert p.image_type is None


def test_image_search_params_with_type():
    p = ImageSearchParams(query="porto", image_type="jpeg")
    assert p.image_type == "jpeg"


def test_image_search_params_invalid_max():
    with pytest.raises(ValidationError):
        ImageSearchParams(query="test", max_items=-1)


def test_list_versions_params_valid():
    p = ListVersionsParams(url="publico.pt")
    assert p.url == "publico.pt"
    assert p.limit == 50
    assert p.offset == 0


def test_list_versions_params_limit_range():
    with pytest.raises(ValidationError):
        ListVersionsParams(url="publico.pt", limit=0)
    with pytest.raises(ValidationError):
        ListVersionsParams(url="publico.pt", limit=501)


def test_list_versions_params_negative_offset():
    with pytest.raises(ValidationError):
        ListVersionsParams(url="publico.pt", offset=-1)


def test_list_versions_params_missing_url():
    with pytest.raises(ValidationError):
        ListVersionsParams()


def test_get_snapshot_params_valid():
    p = GetSnapshotParams(url="publico.pt")
    assert p.url == "publico.pt"
    assert p.timestamp is None


def test_get_snapshot_params_with_timestamp():
    p = GetSnapshotParams(url="publico.pt", timestamp="2010")
    assert p.timestamp == "2010"


def test_get_snapshot_params_missing_url():
    with pytest.raises(ValidationError):
        GetSnapshotParams()


def test_extract_text_params_valid():
    p = ExtractTextParams(url="publico.pt")
    assert p.url == "publico.pt"
    assert p.max_chars == 8000


def test_extract_text_params_max_chars_range():
    with pytest.raises(ValidationError):
        ExtractTextParams(url="publico.pt", max_chars=499)
    with pytest.raises(ValidationError):
        ExtractTextParams(url="publico.pt", max_chars=50001)


def test_extract_text_params_missing_url():
    with pytest.raises(ValidationError):
        ExtractTextParams()
