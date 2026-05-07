# Arquivo.pt API Reference

> Comprehensive reference for all Arquivo.pt public APIs. Sources: [APIs index](https://github.com/arquivo/pwa-technologies/wiki/APIs), [TextSearch wiki](https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API), [CDX server wiki](https://github.com/arquivo/pwa-technologies/wiki/URL-search:-CDX-server-API), [ImageSearch v1.1 wiki](https://github.com/arquivo/pwa-technologies/wiki/ImageSearch-API-v1.1), [Memento wiki](https://github.com/arquivo/pwa-technologies/wiki/Memento--API), [pywb CDX docs](https://pywb.readthedocs.io/en/master/manual/cdxserver_api.html), and live endpoint testing against `arquivo.pt` (May 2026).

---

## Rate Limits (officially documented)

Hitting any limit returns HTTP 429; sustained abuse can result in **permanent IP block**.

| API | Limit (per IP) |
|-----|----------------|
| TextSearch (full-text + URL) | 250 req / 180 s |
| CDX server | 250 req / 180 s |
| ImageSearch v1.1 | 400 req / 180 s |
| Memento | 400 req / 180 s |
| Wayback replay / direct download | 1000 req / 180 s |

Source: <https://github.com/arquivo/pwa-technologies/wiki/APIs>.

---

## 1. Full-Text Search API

**Official docs:** <https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API>

**Endpoint:** `GET https://arquivo.pt/textsearch`
**Output:** JSON

Searches the full text of archived Portuguese web pages. Also serves URL-version-history queries via the `versionHistory` parameter.

### Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `q` | string | *required for full-text* | — | Search terms. Supports `" "` for phrases and `-` to exclude. **Cannot contain URLs** — use `versionHistory` for URL queries. |
| `from` | string | `1996` | — | Start date: `YYYY`, `YYYYMMDD`, or `YYYYMMDDHHMMSS` (shorter forms padded to bounds) |
| `to` | string | current year − 1 | — | End date (same format as `from`) |
| `maxItems` | integer | 50 | **500** | Number of results to return |
| `offset` | integer | 0 | — | Pagination offset |
| `siteSearch` | string | all | — | Restrict to domain (e.g., `publico.pt`) |
| `collection` | string | all | — | Comma-separated collection IDs (e.g., `EAWP33`) |
| `type` | string | all | — | MIME subtype filter (`pdf`, `html`, `doc`, `xls`, `ppt`, `rtf`, …) |
| `dedupField` | string | `site` | — | Field for deduplication (e.g., `site`, `url`, `title`) |
| `dedupValue` | integer | — | — | Max items per `dedupField` value (replaces deprecated `itemsPerSite`) |
| `fields` | string | all | — | Comma-separated list of response fields to include |
| `prettyPrint` | boolean | `true` | — | Human-readable indented JSON |
| `callback` | string | — | — | JSONP callback function name |
| `versionHistory` | string | — | — | Percent-encoded URL — returns all preserved versions newest-to-oldest. Mutually exclusive with `q`. |

### Response Format

The top-level object wraps the result list with metadata fields:

```json
{
  "serviceName": "Arquivo.pt - the Portuguese web-archive",
  "linkToService": "https://arquivo.pt",
  "request_parameters": { "q": "...", "maxItems": 50, "offset": 0, "...": "..." },
  "next_page": "https://arquivo.pt/textsearch?...&offset=50",
  "previous_page": "https://arquivo.pt/textsearch?...&offset=0",
  "estimated_nr_results": 1234,
  "response_items": [
    {
      "title": "Page Title",
      "originalURL": "http://example.pt/page.html",
      "linkToArchive": "https://arquivo.pt/wayback/20050315120000/http://example.pt/page.html",
      "tstamp": "20050315120000",
      "date": "1110888000",
      "contentLength": 12345,
      "digest": "MD5_HASH",
      "mimeType": "text/html",
      "encoding": "UTF-8",
      "linkToScreenshot": "https://arquivo.pt/screenshot?url=https%3A%2F%2Farquivo.pt%2FnoFrame%2Freplay%2F20050315120000%2Fhttp%3A%2F%2Fexample.pt%2Fpage.html",
      "linkToNoFrame": "https://arquivo.pt/noFrame/replay/20050315120000/http://example.pt/page.html",
      "linkToOriginalFile": "https://arquivo.pt/noFrame/replay/20050315120000id_/http://example.pt/page.html",
      "linkToExtractedText": "https://arquivo.pt/textextracted?m=http%3A%2F%2Fexample.pt%2Fpage.html%2F20050315120000",
      "linkToMetadata": "https://arquivo.pt/textsearch?metadata=http%3A%2F%2Fexample.pt%2Fpage.html%2F20050315120000",
      "snippet": "...matching <em>terms</em> with<span class=\"ellipsis\"> ... </span>HTML entities&hellip;",
      "collection": "AWP4",
      "statusCode": "200",
      "fileName": "IAH-20090523070559-03202-awp01.fccn.pt",
      "offset": 16800267
    }
  ]
}
```

`fileName` and the per-item `offset` are populated for metadata-mode requests; they may be empty in regular searches.

### Per-Item Response Fields

| Field | Description |
|-------|-------------|
| `title` | Page `<title>` value |
| `originalURL` | Live URL at capture time |
| `linkToArchive` | Wayback replay URL (with sidebar/frame) |
| `tstamp` | Crawl timestamp `YYYYMMDDHHMMSS` — **when archived, not when published** |
| `date` | Crawl time as Unix epoch (string) |
| `contentLength` | Bytes (integer) |
| `digest` | MD5 hash of bytes |
| `mimeType` | Captured content type |
| `encoding` | Charset (may be empty) |
| `linkToScreenshot` | PNG render of the archived page |
| `linkToNoFrame` | Replay without Arquivo.pt sidebar |
| `linkToOriginalFile` | Raw preserved file (no rewriting, `id_` variant) |
| `linkToExtractedText` | Pre-extracted plaintext URL |
| `linkToMetadata` | Per-capture metadata query URL |
| `snippet` | HTML excerpt; matches wrapped in `<em>…</em>`, omitted ranges shown as `<span class="ellipsis"> ... </span>`. Body uses HTML entities (e.g., `&aacute;`). |
| `collection` | Crawl collection ID (may be empty) |
| `statusCode` | Original HTTP status code |
| `fileName` | ARC/WARC filename (metadata mode) |
| `offset` | Byte offset inside the ARC/WARC (metadata mode) |

### Example

```bash
curl "https://arquivo.pt/textsearch?q=elei%C3%A7%C3%B5es+2005&maxItems=5&from=2004&to=2006&prettyPrint=true"
```

---

## 2. CDX Server API

**Official docs:** <https://github.com/arquivo/pwa-technologies/wiki/URL-search:-CDX-server-API> · **Upstream (pywb):** <https://pywb.readthedocs.io/en/master/manual/cdxserver_api.html>

**Endpoint:** `GET https://arquivo.pt/wayback/cdx`
**Output:** CDXJ text (default) or JSON-lines

Lists all archived captures of a URL. Implementation is pywb's CDX server; mostly compatible with the Internet Archive CDX API.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | *required* | URL to query (URL-encoded) |
| `output` | string | (CDXJ text) | `json` for one JSON object per line; omitted for default text |
| `limit` | integer | **100,000** | Max captures to return (also the documented hard cap) |
| `sort` | string | (chronological) | `reverse` (newest first) or `closest` (use with `closest=<ts>`) |
| `closest` | string | — | Timestamp (`YYYYMMDDHHMMSS`); pairs with `sort=closest` to rank by time-distance |
| `fields` | string | all | Comma-separated subset of fields to emit |
| `matchType` | string | `exact` | `exact`, `prefix`, `host`, `domain` (or use `*` wildcards in `url`) |
| `filter` | string (repeatable) | — | Field filter, e.g. `=status:200`, `!=mime:text/html`, `~url:.*\.pdf$`. Modifiers: `=` exact, `~` regex, `!` negation. |
| `from` | string | — | Start timestamp (`YYYYMMDDHHMMSS`, shorter forms padded) |
| `to` | string | — | End timestamp |

### Output Formats

**Default (CDXJ)** — one capture per line, `<urlkey> <timestamp> <json-blob>`:
```
pt,publico)/ 19961013182712 {"status": "200", "url": "http://www.publico.pt/", "filename": "AWP-Roteiro-...arc.gz", "length": "0", "mime": "text/html", "offset": "14049529", "digest": "HLKEOU75YEIIHLBIGLW2L6LHVAOK33LN", "collection": "Roteiro", "source": "$root:Roteiro.cdxj", "source-coll": "$root"}
```

**JSON mode** (`output=json`) — each line is a complete JSON object including `urlkey` and `timestamp`:
```json
{"urlkey": "pt,publico)/", "timestamp": "19961013182712", "status": "200", "url": "http://www.publico.pt/", "filename": "...", "length": "0", "mime": "text/html", "offset": "14049529", "digest": "...", "collection": "Roteiro", "source": "$root:Roteiro.cdxj", "source-coll": "$root"}
```

### CDX Fields

Documented standard fields: `urlkey`, `timestamp`, `url`, `mime`, `status`, `digest`, `length`, `offset`, `filename`. Live responses additionally surface `collection`, `source`, and `source-coll`.

| Field | Description |
|-------|-------------|
| `urlkey` | SURT-canonicalized URL (e.g., `pt,publico)/`) |
| `timestamp` | Capture time (`YYYYMMDDHHMMSS`) |
| `url` | Original URL |
| `mime` | MIME type at capture |
| `status` | Original HTTP status code |
| `digest` | Content hash |
| `length` | Compressed length in the ARC/WARC (bytes; may be `0` for older indexes) |
| `offset` | Byte offset inside the ARC/WARC |
| `filename` | ARC/WARC filename |
| `collection` | Crawl collection identifier |
| `source` / `source-coll` | Internal pywb routing fields |

### Examples

```bash
# Latest capture of publico.pt
curl "https://arquivo.pt/wayback/cdx?url=publico.pt&output=json&limit=1&sort=reverse"

# All captures from 2008
curl "https://arquivo.pt/wayback/cdx?url=publico.pt&output=json&from=20080101000000&to=20081231235959&limit=500"

# Only HTML 200s, prefix match
curl "https://arquivo.pt/wayback/cdx?url=publico.pt/*&matchType=prefix&filter==status:200&filter==mime:text/html&output=json&limit=100"
```

---

## 3. Image Search API v1.1 (Dionisius)

**Official docs:** <https://github.com/arquivo/pwa-technologies/wiki/ImageSearch-API-v1.1>

**Endpoint:** `GET https://arquivo.pt/imagesearch`
**Output:** JSON
**Source code:** [github.com/arquivo/image-search-api](https://github.com/arquivo/image-search-api)

Searches **584 million+ images** indexed across 1,800 million+ archived pages (figures from the v1.1 wiki, March 2021). Powered by Apache Solr.

### Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `q` | string | *required* | — | Search terms. Supports `" "` for phrases, `-` to exclude. |
| `from` | string | `1996` | — | Start date (same formats as text search) |
| `to` | string | current year − 1 | — | End date |
| `type` | string | all | — | Image format: `png`, `jpeg`, `gif`, `tiff`, … |
| `size` | string | all | — | Image dimensions: `sm` (≤65,536 px²), `md` (65,537–810,000 px²), `lg` (>810,000 px²) |
| `siteSearch` | string | all | — | Domain filter (comma-separated, supports wildcard subdomains) |
| `safeSearch` | string | `on` | — | NSFW filter; `off` to disable. Backed by the `safe` field. |
| `collection` | string | all | — | Restrict to collection ID |
| `maxItems` | integer | 50 | **200** | Results per response (note: lower than text search's 500) |
| `offset` | integer | 0 | — | Pagination offset |
| `fields` | string | default | — | Comma-separated subset of response fields |
| `more` | string | — | — | Surface hidden fields. Documented values: `imgDigest`, `pageHost`, `pageImages`, `safe`. (`imageMetadataChanges`, `pageMetadataChanges`, `matchingImages`, `matchingPages` are also referenced in the wiki.) |
| `prettyPrint` | boolean | `false` | — | Human-readable JSON |

### Response Format

Top-level wrapper:
```json
{
  "serviceName": "Arquivo.pt - image search service.",
  "linkToService": "https://arquivo.pt/images.jsp",
  "linkToDocumentation": "https://github.com/arquivo/pwa-technologies/wiki/ImageSearch-API-v1.1-(beta)",
  "linkToMoreFields": "https://arquivo.pt/imagesearch?...&more=pageHost,matchingImages,safe",
  "nextPage": "...",
  "previousPage": "...",
  "totalItems": 10235490,
  "numberOfResponseItems": 1,
  "offset": 0,
  "responseItems": [ { "...": "..." } ]
}
```

### Per-Item Fields

**Default fields:**

| Field | Description |
|-------|-------------|
| `imgSrc` | Original image URL |
| `imgLinkToArchive` | Archived image URL |
| `imgWidth`, `imgHeight` | Dimensions in pixels |
| `imgMimeType` | Image MIME type |
| `imgTitle` | Image `title` attribute (multivalued) |
| `imgAlt` | `alt` text (multivalued, often multilingual) |
| `imgCaption` | Surrounding caption text (multivalued) |
| `imgTstamp` | Image capture timestamp |
| `pageURL` | Host page URL |
| `pageTitle` | Host page title |
| `pageTstamp` | Host page capture timestamp |
| `pageLinkToArchive` | Archived host page URL |
| `collection` | Crawl collection (multivalued) |

**Hidden fields (request via `more=`):**

| Field | Description |
|-------|-------------|
| `imgDigest` | MD5 hash of image bytes |
| `pageHost` | Host of the source page |
| `pageImages` | Image count on the source page |
| `safe` | NSFW score, `0.000`–`1.000` (**`<0.500` indicates unsafe** — must be surfaced explicitly when `safeSearch=off`) |
| `imageMetadataChanges`, `pageMetadataChanges` | Historical change counts |
| `matchingImages`, `matchingPages` | Aggregate match counts |

> **Note:** an `imgThumbnailBase64` field is sometimes referenced informally but is **not** supported by the live API — requesting it via `more=imgThumbnailBase64` returns no such field, and it is not advertised in the `linkToMoreFields` URL.

### Example

```bash
curl "https://arquivo.pt/imagesearch?q=lisboa&maxItems=5&size=md&from=2010&to=2015&more=safe&prettyPrint=true"
```

---

## 4. Wayback / Memento API (Snapshot Retrieval)

**Official docs:** <https://github.com/arquivo/pwa-technologies/wiki/Memento--API>

### Replay URL Patterns

| Pattern | Description |
|---------|-------------|
| `https://arquivo.pt/wayback/{timestamp}/{url}` | Standard Wayback replay (with Arquivo.pt sidebar/frame) |
| `https://arquivo.pt/noFrame/replay/{timestamp}/{url}` | Clean replay; internal links rewritten, no sidebar |
| `https://arquivo.pt/noFrame/replay/{timestamp}id_/{url}` | Raw original file (no rewriting, no banner) |

Verified against live `linkToNoFrame` / `linkToOriginalFile` values returned by the TextSearch API. The previously-published `https://arquivo.pt/wayback/noFrame/...` and `https://arquivo.pt/wayback/{ts}id_/...` patterns return **HTTP 404** and should not be used.

### Auxiliary Endpoints

| Endpoint | Pattern | Returns |
|----------|---------|---------|
| Screenshot | `https://arquivo.pt/screenshot?url={percent-encoded noFrame replay URL}` | PNG |
| Extracted text | `https://arquivo.pt/textextracted?m={percent-encoded url}/{timestamp}` | text/plain (server-side extraction) |
| Per-capture metadata | `https://arquivo.pt/textsearch?metadata={percent-encoded url}/{timestamp}` | JSON (TextSearch metadata mode) |

### Timestamp Format

`YYYYMMDDHHMMSS` — 14-digit string. Shorter forms are padded to bounds:
- `2005` → matches earliest 2005 capture
- `20050315` → matches first capture on March 15, 2005
- `20050315120000` → exact second

### Memento Protocol (RFC 7089)

Arquivo.pt is a registered Memento provider.

| Capability | Endpoint |
|------------|----------|
| TimeGate | `https://arquivo.pt/wayback/{url}` — pass `Accept-Datetime` header to get the closest capture |
| TimeMap (link format) | `https://arquivo.pt/wayback/timemap/link/{url}` — RFC 7089 application/link-format |
| TimeMap (CDXJ) | `https://arquivo.pt/wayback/timemap/cdxj/{url}` — native CDXJ |
| TimeMap (NDJSON) | `https://arquivo.pt/wayback/timemap/json/{url}` — newline-delimited JSON |

Standard Memento negotiation uses the `Accept-Datetime` request header on the TimeGate; there is no special media-type Accept value.

---

## 5. Save Page Now (ArchivePageNow)

User-triggered on-demand capture, built on pywb's recording mode.

| Surface | URL | Notes |
|---------|-----|-------|
| API | `https://arquivo.pt/save/now/record/<URI>` | HEAD or GET; live test returns HTTP 307 (redirect into the recorder) |
| Web UI | `https://arquivo.pt/services/savepagenow` | Browser form; not an API endpoint (POST returns 404; GET 302 to UI) |
| About | <https://sobre.arquivo.pt/en/savepagenow-to-record-webpages-immediately-on-arquivo-pt/> | |

### Constraints

- Captures are slow (seconds to tens of seconds per URL).
- No publicly documented authentication or quota model — anonymous use only.
- Arquivo.pt's terms of service ask users not to abuse the service; bulk archival is discouraged.

---

## 6. Link Graph Dataset

**Access:** Downloadable dataset (not a queryable API)

| Property | Value |
|----------|-------|
| Size | 139+ million URLs with anchor text |
| Format | SURT-encoded JSONL |
| Coverage | Links extracted from archived Portuguese web pages |
| Download | Available via [Arquivo.pt open datasets](https://arquivo.pt/dadosabertos) |

Requires local processing — cannot be queried via a REST endpoint.

---

## 7. CDXJ Bulk Index Files

Per-collection gzipped CDXJ indexes for offline analysis.

- Docs: <https://sobre.arquivo.pt/en/cdxj-index-files-are-available-to-suppport-bulk-access/>
- Format: gzipped CDXJ, one file per collection
- Use case: training-corpus assembly, large-scale link/temporal analysis

Not queryable; download-only.

---

## 8. Special Collections

Pre-curated datasets selectable via the `collection` parameter on TextSearch and ImageSearch. Examples observed in the live index include `AWP4`, `Roteiro`, `Memorial`, plus many `EAWP*`-prefixed event collections (e.g., `EAWP33` for COVID-19, `EAWP43` for RCAAP). The full registry is maintained in the [Arquivo.pt collections spreadsheet](https://docs.google.com/spreadsheets/d/e/2PACX-1vSwVV3LqlmS7Ia4cFEO85cWr8Ip16TxMXCWFGPxVBCJhlpfkdqT45ykjDx3zLiYXsL3mC6OZuVyqwYS/pubhtml). IDs change over time — always cross-check against the spreadsheet before relying on a specific code.

---

## General Notes

- **Embargo period.** Archived content becomes searchable after a **~1-year minimum delay** from capture, "to prevent the possibility of concurrent access with the original publishing web sites." Source: <https://sobre.arquivo.pt/en/help/access-to-archived-contents/>. The same embargo applies to text and images.
- **Character encoding.** Most content is UTF-8; older captures may be ISO-8859-1. The TextSearch `encoding` field reflects the original.
- **Citation.** If publishing on top of Arquivo.pt, cite: Gomes, D. et al., "Arquivo.pt: The Portuguese Web Archive" — <https://arquivo.pt>.
- **Etiquette.** Set a descriptive `User-Agent` that includes a contact URL. The Arquivo.pt team uses it to reach out before blocking misbehaving clients.

---

*Last verified against live endpoints and official wiki: 2026-05-07*
