# arquivo-pt-mcp

[![PyPI](https://img.shields.io/pypi/v/arquivo-pt-mcp)](https://pypi.org/project/arquivo-pt-mcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/arquivo-pt-mcp)](https://pypi.org/project/arquivo-pt-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/thaenor/arquivo-pt-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/thaenor/arquivo-pt-mcp/actions/workflows/ci.yml)

Um servidor **Model Context Protocol (MCP)** para o **[Arquivo.pt](https://arquivo.pt)** — o arquivo web português. Permite que o Claude (ou qualquer outro LLM compatível com MCP) pesquise e leia conteúdo web português arquivado.

---

## 🇵🇹 Em Português

### O que faz

O `arquivo-pt-mcp` expõe cinco **ferramentas** ao modelo de linguagem, permitindo-lhe consultar o Arquivo.pt como se fosse uma base de dados nativa:

| Ferramenta | Descrição |
|------------|-----------|
| **`search`** | Pesquisa em texto integral no arquivo, com filtros opcionais de intervalo de datas e site |
| **`image_search`** | Pesquisa em mais de 1,8 mil milhões de imagens arquivadas |
| **`list_versions`** | Lista todas as capturas de um determinado URL através do servidor CDX |
| **`get_snapshot`** | Obtém uma página arquivada específica a partir de um URL + timestamp |
| **`extract_text`** | Obtém uma página arquivada e devolve o texto legível (HTML removido) |

### Instalação

```bash
pip install arquivo-pt-mcp
```

Ou, se preferir usar o `uv`:

```bash
uv pip install arquivo-pt-mcp
```

### Configuração

#### Claude Desktop

Adicione ao ficheiro `claude_desktop_config.json`:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "arquivo-pt": {
      "command": "uv",
      "args": ["run", "arquivo-pt-mcp"]
    }
  }
}
```

#### Cursor

No Cursor, vá a **Settings → MCP**, adicione um novo servidor e defina:

- **Name**: `arquivo-pt`
- **Command**: `uv run arquivo-pt-mcp`

#### Zed, Cline, e outros

Consulte a [documentação do MCP](https://modelcontextprotocol.io/quickstart) do seu editor. Em qualquer cliente MCP, basta apontar o comando para o pacote `arquivo-pt-mcp`.

### Exemplos de utilização

Uma vez configurado, pode pedir ao Claude coisas como:

- *“Pesquisa no Arquivo.pt por ‘eleições 2005’ e mostra-me os primeiros três resultados.”*
- *“Mostra-me como a página inicial do Público era a 1 de janeiro de 2010.”*
- *“Quantas vezes foi o Expresso arquivado em 2008?”*
- *“Extrai o texto do snapshot mais antigo do sapo.pt.”*
- *“Procura imagens do Terreiro do Paço arquivadas antes de 2010.”*

### Endpoints da API utilizados

- `https://arquivo.pt/textsearch` — pesquisa em texto
- `https://arquivo.pt/imagesearch` — pesquisa de imagens
- `https://arquivo.pt/wayback/cdx` — índice de capturas (CDX)
- `https://arquivo.pt/wayback/{timestamp}/{url}` — obtenção de snapshots
- `https://arquivo.pt/wayback/noFrame/{timestamp}/{url}` — snapshot limpo para extração de texto

Documentação oficial: <https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API>

### Desenvolvimento

```bash
git clone https://github.com/thaenor/arquivo-pt-mcp.git
cd arquivo-pt-mcp
uv sync --extra dev
pytest -q
```

O projeto usa:

- **pytest + pytest-asyncio** para testes
- **pytest-cov** para cobertura
- **ruff** para lint e formatação

```bash
ruff check src tests
ruff format src tests
pytest --cov=arquivo_pt_mcp
```

#### Testes de integração

Opcionalmente, pode executar os testes de integração contra a API real do Arquivo.pt:

```bash
RUN_INTEGRATION=1 pytest -m integration -v
```

Estes testes estão marcados com `@pytest.mark.integration` e são ignorados por
padrão. Apenas executam quando a variável de ambiente `RUN_INTEGRATION=1` está
definida. No GitHub Actions correm automaticamente uma vez por dia (agendamento
noturno) e também podem ser disparados manualmente via `workflow_dispatch` — não
bloqueiam PRs.

**Nota sobre o GitHub Actions:** Os runners padrão do GitHub estão alojados nos
EUA. A conectividade TCP transatlântica para `arquivo.pt` (alojado em Portugal)
é por vezes pouco fiável — os testes podem falhar com `httpx.ConnectError` ou
`httpx.ConnectTimeout` independentemente da qualidade do código. O projeto usa
`MAX_RETRIES=5` com backoff exponencial para mitigar este problema, mas uma
falha ocasional no CI noturno é esperada e não indica uma regressão. Para
execuções locais (a partir de qualquer localização na Europa) os testes passam
de forma consistente.

### Prémio Arquivo.pt

Este projeto foi desenvolvido para participar no **[Prémio Arquivo.pt](https://sobre.arquivo.pt/pt/areas-de-intervencao/premio-arquivo-pt/)**, que incentiva a criação de ferramentas e aplicações que aproveitam o arquivo web português para fins educativos, científicos, culturais e técnicos.

### Roadmap

- [ ] **Guardar Página Agora** (*Save Page Now*) — requer credenciais de API
- [x] Cache com TTL para reduzir chamadas ao Arquivo.pt
- [x] Gestão de *rate limits* com retentativas exponenciais
- [x] Suporte para pesquisa avançada por domínio e coleção
- [x] Integração com outros clientes MCP (Zed, Cline, Windsurf)

### Licença

[MIT](LICENSE)

---

## 🇬🇧 In English

### What it does

`arquivo-pt-mcp` exposes five **tools** to the language model, letting it query Arquivo.pt as if it were a native data source:

| Tool | Description |
|------|-------------|
| **`search`** | Full-text search across the archive, with optional date range and site filters |
| **`image_search`** | Search across 1.8B+ archived images |
| **`list_versions`** | Every capture of a given URL, via the CDX server |
| **`get_snapshot`** | Resolve a URL + timestamp to a specific archived page |
| **`extract_text`** | Fetch an archived page and return its readable text (HTML stripped) |

### Installation

```bash
pip install arquivo-pt-mcp
```

Or with `uv`:

```bash
uv pip install arquivo-pt-mcp
```

### Configuration

#### Claude Desktop

Add to your `claude_desktop_config.json`:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "arquivo-pt": {
      "command": "uv",
      "args": ["run", "arquivo-pt-mcp"]
    }
  }
}
```

#### Cursor

In Cursor, go to **Settings → MCP**, add a new server, and set:

- **Name**: `arquivo-pt`
- **Command**: `uv run arquivo-pt-mcp`

#### Zed, Cline, and others

Refer to your editor's [MCP documentation](https://modelcontextprotocol.io/quickstart). In any MCP client, simply point the command at the `arquivo-pt-mcp` package.

### Usage examples

Once connected, you can ask Claude things like:

- *“Search Arquivo.pt for ‘eleições 2005’ and show me the first three results.”*
- *“Show me how publico.pt’s homepage looked on January 1, 2010.”*
- *“How many times was expresso.pt archived in 2008?”*
- *“Extract the text from the earliest snapshot of sapo.pt.”*
- *“Search for archived images of Terreiro do Paço from before 2010.”*

### API endpoints used

- `https://arquivo.pt/textsearch` — text search
- `https://arquivo.pt/imagesearch` — image search
- `https://arquivo.pt/wayback/cdx` — capture index (CDX)
- `https://arquivo.pt/wayback/{timestamp}/{url}` — snapshot retrieval
- `https://arquivo.pt/wayback/noFrame/{timestamp}/{url}` — clean snapshot for text extraction

Official docs: <https://github.com/arquivo/pwa-technologies/wiki/Arquivo.pt-API>

### Development

```bash
git clone https://github.com/thaenor/arquivo-pt-mcp.git
cd arquivo-pt-mcp
uv sync --extra dev
pytest -q
```

The project uses:

- **pytest + pytest-asyncio** for testing
- **pytest-cov** for coverage
- **ruff** for linting and formatting

```bash
ruff check src tests
ruff format src tests
pytest --cov=arquivo_pt_mcp
```

#### Integration tests

Optionally, run integration tests against the live Arquivo.pt API:

```bash
RUN_INTEGRATION=1 pytest -m integration -v
```

These tests are marked with `@pytest.mark.integration` and skipped by default.
They only run when the `RUN_INTEGRATION=1` environment variable is set. On
GitHub Actions they run automatically once per day (nightly schedule) and can
also be triggered manually via `workflow_dispatch` — they never block PRs.

**GitHub Actions note:** Standard GitHub-hosted runners are US-based.
Transatlantic TCP connectivity to `arquivo.pt` (hosted in Portugal) is
sometimes unreliable — tests may fail with `httpx.ConnectError` or
`httpx.ConnectTimeout` regardless of code quality. The project uses
`MAX_RETRIES=5` with exponential backoff to mitigate this, but an occasional
failure in the nightly CI run is expected and does not indicate a regression.
When run locally from a European location the tests pass consistently.

### Prémio Arquivo.pt

This project was built for the **[Prémio Arquivo.pt](https://sobre.arquivo.pt/pt/areas-de-intervencao/premio-arquivo-pt/)**, a Portuguese contest that encourages the creation of tools and applications leveraging the Portuguese Web Archive for educational, scientific, cultural, and technical purposes.

### Roadmap

- [ ] **Save Page Now** — requires API credentials
- [x] TTL caching to reduce calls to Arquivo.pt
- [x] Rate-limit handling with exponential backoff
- [x] Advanced search by domain and collection
- [x] Integration with additional MCP clients (Zed, Cline, Windsurf)

### License

[MIT](LICENSE)
