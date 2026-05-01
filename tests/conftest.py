"""Shared fixtures for arquivo-pt-mcp tests."""

import json

import pytest


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear module-level caches before every test to prevent cross-test leakage."""
    from arquivo_pt_mcp import clear_cache

    clear_cache()


@pytest.fixture
def mock_search_response():
    """Sample text search API response."""
    return {
        "response_items": [
            {
                "title": "Eleições 2005 - Resultados",
                "originalURL": "http://www.publico.pt/politica/eleicoes2005",
                "tstamp": "20050315120000",
                "linkToArchive": "https://arquivo.pt/wayback/20050315120000/http://www.publico.pt/politica/eleicoes2005",
                "linkToScreenshot": "https://arquivo.pt/wayback/20050315120000/http://www.publico.pt/politica/eleicoes2005?id=screen",
                "linkToNoFrame": "https://arquivo.pt/wayback/noFrame/20050315120000/http://www.publico.pt/politica/eleicoes2005",
                "linkToExtractedText": "https://arquivo.pt/wayback/20050315120000id_/http://www.publico.pt/politica/eleicoes2005",
                "snippet": (
                    "Resultados das <span class='highlight'>eleições</span> legislativas 2005"
                ),
                "mimeType": "text/html",
                "statusCode": "200",
                "contentLength": 12345,
                "encoding": "UTF-8",
                "digest": "SHA1:abc123",
            }
        ],
        "estimated_nr_results": 42,
    }


@pytest.fixture
def mock_image_search_response():
    """Sample image search API response."""
    return {
        "response_items": [
            {
                "title": "Lisboa - Praça do Comércio",
                "originalURL": "http://www.lisboa.pt/praca-comercio",
                "tstamp": "20050601120000",
                "linkToArchive": "https://arquivo.pt/wayback/20050601120000/http://www.lisboa.pt/praca-comercio",
                "linkToScreenshot": "https://arquivo.pt/wayback/20050601120000/http://www.lisboa.pt/praca-comercio?id=screen",
                "linkToNoFrame": "https://arquivo.pt/wayback/noFrame/20050601120000/http://www.lisboa.pt/praca-comercio",
                "snippet": "Foto da <span class='highlight'>Praça do Comércio</span>",
                "mimeType": "image/jpeg",
            }
        ],
        "estimated_nr_results": 15,
    }


@pytest.fixture
def mock_cdx_json_response():
    """Sample CDX JSON array-of-arrays response."""
    return json.dumps(
        [
            ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
            ["20050315120000", "http://publico.pt/", "text/html", "200", "SHA1:abc", "12345"],
            ["20060420150000", "http://publico.pt/", "text/html", "200", "SHA1:def", "12346"],
        ]
    )


@pytest.fixture
def mock_cdx_text_response():
    """Sample CDX space-separated text response."""
    return "pt,publico)/ 20050315120000 http://publico.pt/ text/html 200 SHA1:abc 12345"


@pytest.fixture
def mock_html_response():
    """Sample HTML page for text extraction."""
    return """<html><head><title>Test Page</title>
<style>body { color: red; }</style></head>
<body><h1>Hello Arquivo</h1><p>This is test content from 2005.</p>
<script>alert('hello');</script></body></html>"""
