"""Shared fixtures for arquivo-pt-mcp tests.

Fixture shapes mirror the real Arquivo.pt API responses (verified 2026-05-02
against textsearch / imagesearch / wayback/cdx). Keeping mocks faithful to the
live wire format means a unit-test failure is also a meaningful real-world
regression.
"""

import json

import pytest


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear module-level caches before every test to prevent cross-test leakage."""
    from arquivo_pt_mcp import clear_cache

    clear_cache()


@pytest.fixture
def mock_search_response():
    """Sample /textsearch response. Keys match the real API."""
    return {
        "serviceName": "Arquivo.pt - Search Service v1.1",
        "linkToService": "https://arquivo.pt/textsearch",
        "next_page": "",
        "estimated_nr_results": 42,
        "request_parameters": {"q": "eleicoes"},
        "response_items": [
            {
                "title": "Eleições 2005 - Resultados",
                "originalURL": "http://www.publico.pt/politica/eleicoes2005",
                "linkToArchive": "https://arquivo.pt/wayback/20050315120000/http://www.publico.pt/politica/eleicoes2005",
                "tstamp": "20050315120000",
                "contentLength": 12345,
                "digest": "SHA1:abc123",
                "mimeType": "text/html",
                "encoding": "UTF-8",
                "date": "2005-03-15",
                "linkToScreenshot": "https://arquivo.pt/wayback/20050315120000/http://www.publico.pt/politica/eleicoes2005?id=screen",
                "linkToNoFrame": "https://arquivo.pt/wayback/noFrame/20050315120000/http://www.publico.pt/politica/eleicoes2005",
                "linkToExtractedText": "https://arquivo.pt/wayback/20050315120000id_/http://www.publico.pt/politica/eleicoes2005",
                "linkToMetadata": "https://arquivo.pt/textsearch?metadata=...",
                "linkToOriginalFile": "https://arquivo.pt/wayback/20050315120000id_/http://www.publico.pt/politica/eleicoes2005",
                "snippet": "Resultados das <span class='highlight'>eleições</span> legislativas 2005",  # noqa: E501
                "fileName": "AWP-Roteiro-...arc.gz",
                "collection": "Roteiro",
                "offset": "12355328",
            }
        ],
    }


@pytest.fixture
def mock_image_search_response():
    """Sample /imagesearch response. Note camelCase 'responseItems' and image-specific fields."""
    return {
        "serviceName": "Arquivo.pt - Image Search Service v1.1 (Dionisius)",
        "linkToService": "https://arquivo.pt/imagesearch",
        "linkToMoreFields": "https://arquivo.pt/imagesearch?...",
        "nextPage": "",
        "previousPage": "",
        "totalItems": 15,
        "numberOfResponseItems": 1,
        "offset": 0,
        "fieldReturnability": {},
        "responseItems": [
            {
                "imgDigest": "072507b30e7d200741e5ab194b93ad62cb9fa384d3ba7594417756e14a1f8a10",
                "imgSrc": "https://arquivo.pt/wayback/20050601120000im_/http://www.lisboa.pt/img/praca-comercio.jpg",
                "pageTitle": "Lisboa - Praça do Comércio",
                "imgHeight": 200,
                "imgWidth": 320,
                "imgMimeType": "image/jpeg",
                "pageURL": "http://www.lisboa.pt/praca-comercio",
                "imgTstamp": "20050601120000",
                "pageTstamp": "20050601120000",
                "imgCaption": [],
                "imgAlt": ["Praça do Comércio"],
                "imgTitle": ["Foto da Praça do Comércio"],
                "collection": ["Roteiro"],
                "imgLinkToArchive": "https://arquivo.pt/wayback/20050601120000/http://www.lisboa.pt/img/praca-comercio.jpg",
                "pageLinkToArchive": "https://arquivo.pt/wayback/20050601120000/http://www.lisboa.pt/praca-comercio",
            }
        ],
    }


@pytest.fixture
def mock_cdx_jsonl_response():
    """Sample /wayback/cdx response in real JSON-Lines format (one JSON object per line)."""
    return "\n".join(
        [
            json.dumps(
                {
                    "urlkey": "pt,publico)/",
                    "timestamp": "20050315120000",
                    "url": "http://publico.pt/",
                    "mime": "text/html",
                    "status": "200",
                    "digest": "SHA1ABCDEF",
                    "length": "12345",
                    "offset": "100",
                    "filename": "AWP-2005.arc.gz",
                    "collection": "Roteiro",
                }
            ),
            json.dumps(
                {
                    "urlkey": "pt,publico)/",
                    "timestamp": "20060420150000",
                    "url": "http://publico.pt/",
                    "mime": "text/html",
                    "status": "200",
                    "digest": "SHA1GHIJKL",
                    "length": "12346",
                    "offset": "200",
                    "filename": "AWP-2006.arc.gz",
                    "collection": "Roteiro",
                }
            ),
        ]
    )


@pytest.fixture
def mock_html_response():
    """Sample HTML page for text extraction (the regex stripper doesn't depend on real archive HTML)."""  # noqa: E501
    return """<html><head><title>Test Page</title>
<style>body { color: red; }</style></head>
<body><h1>Hello Arquivo</h1><p>This is test content from 2005.</p>
<script>alert('hello');</script></body></html>"""
