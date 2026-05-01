"""Tests for helper utilities."""

import pytest

from arquivo_pt_mcp import _normalize_date, _strip_html, _ts_to_iso


class TestNormalizeDate:
    def test_year_only(self):
        assert _normalize_date("2005") == "20050000000000"

    def test_year_month(self):
        assert _normalize_date("2005-03") == "20050300000000"

    def test_year_month_day(self):
        assert _normalize_date("2005-03-15") == "20050315000000"

    def test_full_timestamp(self):
        assert _normalize_date("20050315120000") == "20050315120000"

    def test_none_returns_none(self):
        assert _normalize_date(None) is None

    def test_empty_returns_none(self):
        assert _normalize_date("") is None

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="4-digit year"):
            _normalize_date("200")

    def test_extra_chars_stripped(self):
        assert _normalize_date("2005/03/15") == "20050315000000"


class TestTsToIso:
    def test_full_timestamp(self):
        result = _ts_to_iso("20050315120000")
        assert result == "2005-03-15T12:00:00"

    def test_date_only_padded(self):
        result = _ts_to_iso("20050315")
        assert result == "2005-03-15T00:00:00"

    def test_none_returns_none(self):
        assert _ts_to_iso(None) is None

    def test_short_returns_none(self):
        assert _ts_to_iso("2005") is None

    def test_invalid_returns_raw(self):
        assert _ts_to_iso("99999999") == "99999999"


class TestStripHtml:
    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_plain_text(self):
        assert _strip_html("hello world") == "hello world"

    def test_nested_tags(self):
        html = "<div><p>Line 1</p><p>Line 2</p></div>"
        result = _strip_html(html)
        assert "Line 1" in result
        assert "Line 2" in result
