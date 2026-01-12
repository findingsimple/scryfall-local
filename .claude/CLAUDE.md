# Scryfall Local - Claude Code Instructions

## Project Overview

A local MCP server that caches Scryfall's Magic: The Gathering card data, enabling Claude to answer questions about MTG cards without hitting Scryfall's rate limits.

- **Primary User**: Claude/AI agents (optimized for agentic use)
- **Data**: 520,000+ cards from Scryfall bulk data
- **Storage**: SQLite with FTS5 for fast text search

## Architecture

```
src/
├── server.py        # MCP server (low-level Server class)
├── cli.py           # CLI for download/import/status
├── card_store.py    # SQLite storage with FTS5
├── query_parser.py  # Scryfall syntax parser
└── data_manager.py  # Bulk data download/caching
```

## Key Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Run tests
pytest -v

# Check data status
python -m src.cli status

# Download/update card data
python -m src.cli download

# Import JSON into database
python -m src.cli import

# Run MCP server manually (for testing only)
python -m src.server
```

## MCP Server Setup

Register with Claude Code CLI (no manual server start needed):

```bash
# Add for all projects
claude mcp add scryfall-local -s user -- /path/to/.venv/bin/python -m src.server

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

```bash
pytest -v                           # Run all tests
pytest --cov=src                    # With coverage
pytest tests/test_query_parser.py   # Single file
```

## Query Syntax

Supported Scryfall syntax:
- **Name**: `"Lightning Bolt"` (exact), `'Ach! Hans, Run!'` (single quotes for `!?()`)
- **Name**: `bolt` (partial), `Séance` (accented chars), `Urza's` (apostrophes)
- **Colors**: `c:blue`, `c:urg`, `c>=rg`
- **Mana Value**: `cmc:3`, `cmc>=5`, `cmc<2`
- **Type**: `t:creature`, `t:"legendary creature"`
- **Oracle Text**: `o:flying`, `o:"enters the battlefield"`
- **Set**: `set:neo`, `e:m19`
- **Rarity**: `r:mythic`, `r:rare`
- **Layout**: `layout:transform`, `layout:adventure`, `layout:modal_dfc`
- **Produces Token**: `pt:zombie`, `produces_token:"Goblin Token"`
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

- `data/cards.db` - SQLite database (~4 GB)
- `data/*.json` - Downloaded bulk JSON (~2.3 GB)
- `data/metadata.json` - Cache metadata

The `data/` directory is gitignored.

## Database Design Principles

**Favor separate columns over `raw_data` for queried fields.**

When a field is used for filtering or should appear in search results, add it as a dedicated column in the `cards` table rather than relying on `json_extract(raw_data, ...)`. This provides:
- Better query performance (can be indexed)
- Fields visible in search results
- Cleaner filter code

Current top-level columns include: `name`, `cmc`, `type_line`, `oracle_text`, `power`, `toughness`, `colors`, `color_identity`, `keywords`, `set_code`, `rarity`, `artist`, `released_at`, `loyalty`, `flavor_text`, `collector_number`, `layout`, `produced_mana`, `watermark`, `produces_tokens`.

The `raw_data` column stores the complete Scryfall JSON for any fields not yet promoted to columns.

## Context7 MCP Integration

Always use Context7 MCP when I need library/API documentation, code generation, setup or configuration steps without me having to explicitly ask.

**Use Context7 for:**
- Library/framework documentation lookups
- API reference documentation
- Code generation with specific libraries
- Setup and configuration steps for tools/frameworks
- Best practices for libraries and frameworks

**How to use it:**
1. Automatically resolve library IDs when a library is mentioned
2. Fetch documentation proactively when working with libraries
3. Don't wait for me to ask - use it when it would be helpful
