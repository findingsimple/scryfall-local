# Scryfall Local MCP Server

A local MCP (Model Context Protocol) server that caches Scryfall's Magic: The Gathering card data, enabling Claude to answer questions about MTG cards with up-to-date information without hitting Scryfall's rate limits.

## Features

- **6 MCP Tools**: search_cards, get_card, get_cards_batch, random_card, data_status, refresh_data
- **Scryfall Query Syntax**: Supports colors, mana value, type, oracle text, set, rarity, and boolean operators
- **SQLite Storage**: Efficient ~500MB database with FTS5 for fast text search
- **Security-First**: Parameterized queries, URL validation, path traversal prevention
- **Agentic-Optimized**: Structured JSON responses, batch operations, helpful error messages

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd scryfall-local

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Running the Server

```bash
# Run the MCP server
source .venv/bin/activate
python -m src.server
```

### Adding to Claude Code

Add to your Claude Code MCP configuration (`~/.config/claude/mcp_servers.json`):

```json
{
  "scryfall-local": {
    "command": "python",
    "args": ["-m", "src.server"],
    "cwd": "/path/to/scryfall-local",
    "env": {
      "VIRTUAL_ENV": "/path/to/scryfall-local/.venv"
    }
  }
}
```

### Downloading Card Data

Before using the server, download the bulk card data:

```bash
# Download all cards (2.29 GB) - run in Python
python -c "
import asyncio
from pathlib import Path
from src.data_manager import DataManager

async def download():
    manager = DataManager(Path('./data'))
    await manager.download_bulk_data('all_cards')

asyncio.run(download())
"
```

## MCP Tools

### search_cards
Search for cards using Scryfall syntax.
```
{"query": "c:blue t:instant cmc<=2", "limit": 10}
```

### get_card
Get a single card by exact name or Scryfall ID.
```
{"name": "Lightning Bolt"}
{"id": "e2d1f479-..."}
```

### get_cards_batch
Get multiple cards in a single call.
```
{"names": ["Lightning Bolt", "Counterspell", "Giant Growth"]}
```

### random_card
Get a random card, optionally filtered.
```
{"query": "t:dragon o:flying"}
```

### data_status
Check the status of the local data cache.

### refresh_data
Trigger a data refresh if updates are available.

## Query Syntax

See [SUPPORTED_SYNTAX.md](SUPPORTED_SYNTAX.md) for full documentation.

**Supported:**
- Name: `"Lightning Bolt"` (exact), `bolt` (partial)
- Colors: `c:blue`, `c:urg`, `c>=rg`, `c<=w`
- Mana Value: `cmc:3`, `cmc>=5`, `cmc<2`
- Type: `t:creature`, `t:"legendary creature"`
- Oracle Text: `o:flying`, `o:"enters the battlefield"`
- Set: `set:neo`, `e:m19`
- Rarity: `r:mythic`, `r:rare`
- Boolean: implicit AND, `OR`, `-` (negation)

## Development

### Running Tests

```bash
source .venv/bin/activate
pytest -v
```

### Test Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

## Architecture

```
scryfall-local/
├── src/
│   ├── server.py          # MCP server (low-level Server class)
│   ├── data_manager.py    # Download/cache bulk data
│   ├── query_parser.py    # Scryfall syntax parser
│   └── card_store.py      # Card storage (SQLite + FTS5)
├── tests/                  # Unit and integration tests
├── data/                   # Cached bulk data (gitignored)
└── pyproject.toml
```

## License

MIT
