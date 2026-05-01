# Arquivo.pt API Reference

> Comprehensive reference for all Arquivo.pt public APIs. Source: [official wiki](https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API), [image-search-api repo](https://github.com/arquivo/image-search-api), [pywb CDX docs](https://pywb.readthedocs.io/en/master/manual/cdxserver_api.html), and live endpoint testing.

---

## 1. Full-Text Search API

**Endpoint:** `GET https://arquivo.pt/textsearch`

Searches the full text of archived Portuguese web pages.

### Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `q` | string | *required* | — | Search terms. Supports `" "` for phrases, `-` to exclude. **Do not input URLs** (use `versionHistory` instead — URL in `q` returns HTTP 400). |
| `from` | string | `1996` | — | Start date: `YYYY`, `YYYYMM`, `YYYYMMDD`, or `YYYYMMDDHHMMSS` |
| `to` | string | current-1 | — | End date (same format as `from`) |
| `maxItems` | integer | 50 | **500** | Number of results to return |
| `offset` | integer | 0 | — | Pagination offset |
| `siteSearch` | string | all | — | Restrict to domain (e.g., `publico.pt`) |
| `collection` | string | all | — | Limit to specific Arquivo.pt collection ID (e.g., `EAWP33` for COVID-19) |
| `type` | string | all | — | Filter by MIME/extension (e.g., `pdf`, `html`, `doc`) |
| `dedupField` | string | `site` | — | Field for deduplication: `site` or `url` |
| `dedupValue` | integer | — | — | Max items per `dedupField` value |
| `fields` | string | all | — | Comma-separated list of fields to include |
| `prettyPrint` | boolean | `true` | — | Human-readable indented JSON |
| `callback` | string | — | — | JSONP callback function name |
| `versionHistory` | string | — | — | URL to search all preserved versions of (URL-encoded). e.g., `versionHistory=http%3A%2F%2Fpublico.pt` |

### Response Format

```json
{
  "response_items": [
    {
      "title": "Page Title",
      "originalURL": "http://example.pt/page.html",
      "tstamp": "20050315120000",
      "contentLength": 12345,
      "mimeType": "text/html",
      "encoding": "UTF-8",
      "digest": "MD5_HASH",
      "linkToArchive": "https://arquivo.pt/wayback/20050315120000/http://example.pt/page.html",
      "linkToScreenshot": "https://arquivo.pt/wayback/20050315120000/http://example.pt/page.html?id=screen",
      "linkToNoFrame": "https://arquivo.pt/wayback/noFrame/20050315120000/http://example.pt/page.html",
      "linkToOriginalFile": "https://arquivo.pt/wayback/20050315120000id_/http://example.pt/page.html",
      "linkToExtractedText": "https://arquivo.pt/wayback/20050315120000id_/http://example.pt/page.html",
      "snippet": "...highlighted <span class=\"highlight\">search terms</span>...",
      "collection": "EAWP_NN",
      "statusCode": "200"
    }
  ],
  "estimated_nr_results": 1234,
  "total_items": 50
}
```

### Key Response Fields

| Field | Description |
|-------|-------------|
| `tstamp` | Crawl timestamp (YYYYMMDDHHMMSS) — **when archived, not when published** |
| `linkToArchive` | Wayback replay URL (with sidebar/frame) |
| `linkToNoFrame` | Replay URL without Arquivo.pt sidebar |
| `linkToOriginalFile` | Raw preserved file (no rewriting) |
| `linkToExtractedText` | Text-only extraction |
| `linkToScreenshot` | Screenshot/image of the page |
| `snippet` | HTML with `<span class="highlight">` matching terms |
| `statusCode` | Original HTTP status code |

### Example

```bash
curl "https://arquivo.pt/textsearch?q=elei%C3%A7%C3%B5es+2005&maxItems=5&from=2004&to=2006&prettyPrint=true"
```

### Rate Limits

- Default: ~250-400 requests/minute (not officially documented; inferred from production behavior)
- `maxItems=500` returns the maximum allowed per query
- Use `prettyPrint=false` in production for smaller payloads

---

## 2. CDX Server API

**Endpoint:** `GET https://arquivo.pt/wayback/cdx`

Lists all archived captures of a URL. Based on pywb CDXJ Server API (compatible with Internet Archive CDX).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | URL to query (URL-encoded) |
| `output` | string | — | Output format: `json` (JSON array of arrays) or omitted (space-separated text) |
| `limit` | integer | — | Max number of captures to return |
| `sort` | string | `normal` (ascending) | Sort order: `normal` (oldest first) or `reverse` (newest first) |
| `fl` | string | all fields | Comma-separated list of fields to include |
| `matchType` | string | `exact` | URL matching: `exact`, `prefix`, `host`, `domain` |
| `filter` | string | — | Filter expression (e.g., `statuscode:200`) |
| `from` | string | — | Start timestamp (YYYYMMDDHHMMSS) |
| `to` | string | — | End timestamp |
| `showNumPages` | boolean | — | Return number of pages instead of results |
| `showPagedIndex` | boolean | — | Return indexed pages for paginated access |

### Output Formats

**JSON mode** (`output=json`):
```json
[
  ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
  ["20050315120000", "http://example.pt/", "text/html", "200", "SHA1:abc...", "12345"],
  ["20060420150000", "http://example.pt/", "text/html", "200", "SHA1:def...", "12346"]
]
```
First row = column headers, subsequent rows = data.

**Text mode** (default, space-separated):
```
pt,example)/ 20050315120000 http://example.pt/ text/html 200 SHA1:abc... 12345
```

### CDX Fields (standard pywb)

| Field | Description |
|-------|-------------|
| `timestamp` | Capture time (YYYYMMDDHHMMSS) |
| `original` | Original URL |
| `mimetype` | MIME type of captured content |
| `statuscode` | Original HTTP status code |
| `digest` | Content hash (SHA1) |
| `length` | Content length in bytes |

### Example

```bash
# Latest capture of publico.pt
curl "https://arquivo.pt/wayback/cdx?url=publico.pt&output=json&limit=1&sort=reverse"

# All captures from 2008
curl "https://arquivo.pt/wayback/cdx?url=publico.pt&output=json&from=20080101000000&to=20081231235959&limit=500"
```

---

## 3. Image Search API (Dionisius)

**Endpoint:** `GET https://arquivo.pt/imagesearch`

Searches 1.8+ billion archived images from the Portuguese web. Powered by Apache Solr.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | *required* | Search terms for image content |
| `from` | string | — | Start date (same format as text search) |
| `to` | string | — | End date |
| `siteSearch` | string | — | Restrict to domain |
| `maxItems` | integer | 50 | Results per page |
| `offset` | integer | 0 | Pagination offset |
| `type` | string | — | Image format filter (e.g., `jpeg`, `png`, `gif`) |
| `width` / `height` | string | — | Dimension filters |
| `safeSearch` | boolean | `true` | Filter NSFW content |

### Response Format

Image search returns results including:

| Field | Description |
|-------|-------------|
| Image URL (within archive) | Direct link to archived image |
| Source page URL | Page containing the image |
| Timestamp | When the page was crawled |
| Dimensions | Image width/height |
| File type | MIME type |

### Note

The image search API is distinct from the text search API. The endpoint is `https://arquivo.pt/imagesearch` (not `/textsearch`). Images have a **1-year embargo** — newly archived images become searchable after one year.

### Source Code

The image search API is a Java/Solr application: [github.com/arquivo/image-search-api](https://github.com/arquivo/image-search-api)

---

## 4. Wayback / Memento API (Snapshot Retrieval)

### URL Patterns

| Pattern | Description |
|---------|-------------|
| `https://arquivo.pt/wayback/{timestamp}/{url}` | Standard Wayback replay (with sidebar/frame) |
| `https://arquivo.pt/wayback/noFrame/{timestamp}/{url}` | Clean replay without Arquivo.pt sidebar |
| `https://arquivo.pt/wayback/{timestamp}id_/{url}` | Raw original file (no rewriting, no banner) |

### Derived Endpoints

| Endpoint | Description |
|----------|-------------|
| `linkToScreenshot` | Screenshot/image of archived page |
| `linkToExtractedText` | Text-only extraction of archived page |
| `linkToOriginalFile` | Raw preserved file (id_ variant) |
| `linkToNoFrame` | Replay without Wayback UI chrome |

### Timestamp Format

`YYYYMMDDHHMMSS` — 14-digit string. Can be shortened:
- `2005` → matches first capture in 2005
- `20050315` → matches March 15, 2005
- `20050315120000` → exact time

### Memento Compatibility

Arquivo.pt implements the Memento protocol (RFC 7089):
- `Accept: application/vnd.archive.memento.headers` → Memento response
- TimeGate: `https://arquivo.pt/wayback/{url}` with `Accept-Datetime` header
- TimeMap: `https://arquivo.pt/wayback/timemap/link/{url}`

---

## 5. Save Page Now API

**Endpoint:** `POST https://arquivo.pt/services/savepagenow`

Requests a new capture of a live URL.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | string | URL to archive (required) |

### Authentication

Requires API credentials (not documented publicly). Contact arquivo.pt for access.

### Rate Limits

Strict rate limiting — must respect `robots.txt` and crawl delays. Not suitable for bulk archiving.

---

## 6. Link Graph Dataset

**Access:** Downloadable dataset (not a queryable API)

| Property | Value |
|----------|-------|
| Size | 139+ million URLs with anchor text |
| Format | SURT-encoded JSONL |
| Coverage | Links extracted from archived Portuguese web pages |
| Download | Available via [Arquivo.pt open datasets](https://arquivo.pt/dadosabertos) |

### Potential Uses for MCP

- Build a web genealogy / link topology explorer
- Map diaspora community networks
- Trace disinformation propagation paths

Note: Requires local processing — cannot be queried via a simple REST endpoint.

---

## 7. Special Collections

Pre-curated datasets available via `collection` parameter in text search:

| Collection ID | Description |
|---------------|-------------|
| `EAWP7` | Legislative Elections 2015 |
| `EAWP26` | Legislative Elections 2019 |
| `EAWP33` | COVID-19 |
| `EAWP43` | RCAAP (academic repositories) |
| `EAWP45` | Legislative Elections 2024 |

Full list: [Arquivo.pt collections spreadsheet](https://docs.google.com/spreadsheets/d/e/2PACX-1vSwVV3LqlmS7Ia4cFEO85cWr8Ip16TxMXCWFGPxVBCJhlpfkdqT45ykjDx3zLiYXsL3mC6OZuVyqwYS/pubhtml)

---

## General Notes

- **Embargo period:** Archived content is available after a 1-year embargo from the original capture date
- **Character encoding:** Most content is UTF-8; older content may use ISO-8859-1 (Western European)
- **Rate limiting:** ~250-400 req/min (inferred; not officially documented)
- **Citation:** If building on Arquivo.pt, cite: Gomes, D. et al. "Arquivo.pt: The Portuguese Web Archive" — [arquivo.pt](https://arquivo.pt)

---

*Last updated: 2026-05-01*