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


def test_list_versions_params_compact_default():
    p = ListVersionsParams(url="publico.pt")
    assert p.compact is False


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


# ── SearchParams new fields ──────────────────────────────────


def test_search_params_collection_accepted():
    p = SearchParams(query="test", collection="EAWP33")
    assert p.collection == "EAWP33"


def test_search_params_mime_type_valid():
    p = SearchParams(query="test", mime_type="pdf")
    assert p.mime_type == "pdf"


def test_search_params_mime_type_rejects_invalid():
    with pytest.raises(ValidationError):
        SearchParams(query="test", mime_type="xml")


def test_search_params_offset_rejects_negative():
    with pytest.raises(ValidationError):
        SearchParams(query="test", offset=-1)


def test_search_params_offset_default_zero():
    p = SearchParams(query="test")
    assert p.offset == 0


# ── ImageSearchParams new fields ─────────────────────────────


def test_image_search_params_size_accepted():
    p = ImageSearchParams(query="test", size="large")
    assert p.size == "large"


def test_image_search_params_safe_search_default_on():
    p = ImageSearchParams(query="test")
    assert p.safe_search == "on"


def test_image_search_params_safe_search_off():
    p = ImageSearchParams(query="test", safe_search="off")
    assert p.safe_search == "off"


def test_image_search_params_collection_accepted():
    p = ImageSearchParams(query="test", collection="EAWP33")
    assert p.collection == "EAWP33"


def test_image_search_params_more_default_empty():
    p = ImageSearchParams(query="test")
    assert p.more == []


def test_image_search_params_more_with_safe():
    p = ImageSearchParams(query="test", more=["safe", "imgDigest"])
    assert p.more == ["safe", "imgDigest"]


def test_image_search_params_more_rejects_invalid():
    with pytest.raises(ValidationError):
        ImageSearchParams(query="test", more=["invalidField"])


# ── ListVersionsParams new fields ────────────────────────────


def test_list_versions_params_filter_valid():
    p = ListVersionsParams(url="publico.pt", filter=["=status:200"])
    assert p.filter == ["=status:200"]


def test_list_versions_params_filter_rejects_missing_operator():
    with pytest.raises(ValidationError, match="filter expressions must look like"):
        ListVersionsParams(url="publico.pt", filter=["status:200"])


def test_list_versions_params_filter_rejects_empty():
    p = ListVersionsParams(url="publico.pt")
    assert p.filter == []


def test_list_versions_params_match_type_default():
    p = ListVersionsParams(url="publico.pt")
    assert p.match_type == "exact"


def test_list_versions_params_match_type_domain():
    p = ListVersionsParams(url="publico.pt", match_type="domain")
    assert p.match_type == "domain"


def test_list_versions_params_closest_auto_sets_sort():
    p = ListVersionsParams(url="publico.pt", closest="20050315120000")
    assert p.sort == "closest"
    assert p.closest == "20050315120000"


def test_list_versions_params_closest_with_explicit_sort():
    p = ListVersionsParams(url="publico.pt", sort="closest", closest="20050315120000")
    assert p.sort == "closest"


def test_list_versions_params_sort_closest_requires_closest():
    with pytest.raises(ValidationError, match="sort='closest' requires a 'closest' timestamp"):
        ListVersionsParams(url="publico.pt", sort="closest")


def test_list_versions_params_from_date_accepted():
    p = ListVersionsParams(url="publico.pt", from_date="2005")
    assert p.from_date == "2005"


def test_list_versions_params_to_date_accepted():
    p = ListVersionsParams(url="publico.pt", to_date="2006")
    assert p.to_date == "2006"
