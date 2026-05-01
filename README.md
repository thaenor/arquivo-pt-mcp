# arquivo-pt-mcp

A Model Context Protocol server for **Arquivo.pt**, the Portuguese Web Archive — letting Claude (and any other MCP-compatible LLM) search and read archived Portuguese web content.

## What it does

Four tools:

- **`search`** — full-text search across the archive, with optional date range and site filters
- **`list_versions`** — every capture of a given URL, via the CDX server
- **`get_snapshot`** — resolve a URL + timestamp to a specific archived page
- **`extract_text`** — fetch an archived page and return its readable text (HTML stripped)

## Install

```bash
pip install -e .
```

Or run directly with `uv`:

```bash
uv run server.py
```

## Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "arquivo-pt": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/arquivo-pt-mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop.

## Try it

Once connected, ask Claude:

- *“Search arquivo.pt for ‘eleições 2005’ and show me the first three results.”*
- *“Show me how publico.pt’s homepage looked on January 1, 2010.”*
- *“How many times has expresso.pt been archived in 2008?”*
- *“Extract the text from the earliest snapshot of sapo.pt.”*

## API endpoints used

- `https://arquivo.pt/textsearch` — search
- `https://arquivo.pt/wayback/cdx` — capture index
- `https://arquivo.pt/wayback/{timestamp}/{url}` — snapshot retrieval
- `https://arquivo.pt/wayback/noFrame/{timestamp}/{url}` — clean snapshot for text extraction

Documentation: <https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API>

## Not yet implemented

- Save Page Now (requires API credentials)
- Image search (Dionisius)
- Caching (every call hits arquivo.pt — fine for dev, add a TTL cache before serious use)
- Rate-limit handling beyond surfacing HTTP errors

## License

MIT
