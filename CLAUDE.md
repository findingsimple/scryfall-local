# Scryfall Local - Claude Code Instructions

## Project Overview

A local MCP server that caches Scryfall's Magic: The Gathering card data, enabling Claude to answer questions about MTG cards without hitting Scryfall's rate limits.

- **Primary User**: Claude/AI agents (optimized for agentic use)
- **Data**: ~37,000 unique cards from Scryfall oracle_cards bulk data
- **Storage**: SQLite with FTS5 for fast text search

## Architecture

```
src/
├── server.py        # MCP server (low-level Server class)
├── cli.py           # CLI for download/import/status
├── card_store.py    # SQLite storage with FTS5
├── query_parser.py  # Scryfall syntax parser
├── data_manager.py  # Bulk data download/caching
└── import_utils.py  # Streaming import with atomic DB swap
```

## Key Commands

```bash
# Install dependencies (from uv.lock — reproducible)
uv sync

# Run tests
uv run pytest -v

# Check data status
uv run python -m src.cli status

# Download/update card data
uv run python -m src.cli download

# Import JSON into database
uv run python -m src.cli import

# Run MCP server manually (for testing only)
uv run python -m src.server
```

## MCP Server Setup

Register with Claude Code CLI (no manual server start needed):

```bash
# Add for all projects (uses cd wrapper — VS Code extension ignores cwd field)
claude mcp add scryfall-local --scope user -- /bin/bash -c "cd /path/to/scryfall-local && .venv/bin/python -m src.server"

# Verify connection
claude mcp list
```

Claude Code automatically starts the server - no need to run it manually.

## Running Tests

Tests are written TDD-style with pytest:
- `tests/test_query_parser.py` - Query syntax parsing
- `tests/test_card_store.py` - SQLite storage (110+ tests)
- `tests/test_data_manager.py` - Download/caching
- `tests/test_server.py` - MCP server tools
- `tests/test_cli.py` - CLI commands
- `tests/test_import_utils.py` - Streaming import and atomic DB swap

```bash
uv run pytest -v                           # Run all tests
uv run pytest --cov=src                    # With coverage
uv run pytest tests/test_query_parser.py   # Single file
```

## Query Syntax

Supported Scryfall syntax:
- **Name**: `bolt` / `"lightning bolt"` (substring), `!"Lightning Bolt"` (exact, case-insensitive)
- **Name**: `'Ach! Hans, Run!'` (single quotes for `!?()`), `Séance` (accented chars), `Urza's` (apostrophes)
- **Colors**: `c:blue`, `c:urg` (at least), `c=rg` (exactly), `c>=rg`
- **Mana Value**: `cmc:3`, `cmc>=5`, `cmc<2`
- **Type**: `t:creature`, `t:"legendary creature"`
- **Oracle Text**: `o:flying`, `o:"enters the battlefield"`
- **Set**: `set:neo`, `e:m19`
- **Rarity**: `r:mythic`, `r:rare`
- **Layout**: `layout:transform`, `layout:adventure`, `layout:modal_dfc`
- **Produces Token**: `pt:zombie`, `produces_token:"Goblin Token"`
- **Card Properties**: `is:dfc`, `is:mdfc`, `is:split`, `is:adventure`, `is:permanent`, `is:spell`
- **Boolean**: implicit AND, `OR`, `-` (negation)

See `SUPPORTED_SYNTAX.md` for full documentation.

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_cards` | Search with Scryfall syntax |
| `get_card` | Get card by name or ID |
| `get_cards_batch` | Get multiple cards at once |
| `random_card` | Random card (optionally filtered) |
| `data_status` | Check cache status |
| `refresh_data` | Trigger data refresh |

## Data Files

- `data/cards.db` - SQLite database (~300 MB for oracle_cards)
- `data/*.json` - Downloaded bulk JSON (~160 MB for oracle_cards)
- `data/metadata.json` - Cache metadata

The `data/` directory is gitignored.

## Database Design Principles

**All queried fields are stored as dedicated columns.**

Every field used for filtering or returned in search results has its own column in the `cards` table. There is no `raw_data` fallback column — if a new field is needed, add a dedicated column for it.

Current columns include: `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`, `power`, `toughness`, `colors`, `color_identity`, `keywords`, `set_code`, `rarity`, `artist`, `released_at`, `loyalty`, `flavor_text`, `collector_number`, `layout`, `produced_mana`, `watermark`, `produces_tokens`.

## Query Execution

Queries use two paths depending on filter types:

- **FTS5 path** — `oracle_text` (`o:`) and `type` (`t:`) positive filters use `JOIN cards_fts` with FTS5 MATCH. Results ranked by BM25 relevance (`ORDER BY rank`).
- **SQL path** — All other filters (name, colors, cmc, rarity, etc.) use standard SQL with LIKE/exact match. Results ordered alphabetically (`ORDER BY name`).

Fallbacks to SQL LIKE:
- Negated text filters (`-o:flying`, `-t:creature`) — FTS5 can't do standalone NOT
- OR groups (`t:creature OR t:instant`) — FTS5 allows only one MATCH per query

Mixed queries (e.g., `o:flying c:blue cmc:3`) use the FTS5 JOIN for text filters and standard WHERE conditions for the rest, all in a single query.

Security measures:
- All queries use parameterised SQL (`?` placeholders)
- LIKE wildcards (`%`, `_`) in user input are escaped via `_escape_like()`
- Query strings are limited to 1,000 characters (`MAX_QUERY_LENGTH`)

## Future Enhancements

Optional improvements to consider:
- **ruff** - Fast linting and formatting (replaces flake8/isort/black)
- **mypy** - Type checking (project already has type hints)
- **GitHub Actions** - CI workflow for PRs
