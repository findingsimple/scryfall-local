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

### Adding to Claude Code

Register the MCP server using the Claude Code CLI:

```bash
# Add for all projects (user scope)
claude mcp add scryfall-local -s user -- /path/to/scryfall-local/.venv/bin/python -m src.server

# Or add for current project only (local scope)
claude mcp add scryfall-local -- /path/to/scryfall-local/.venv/bin/python -m src.server
```

Replace `/path/to/scryfall-local` with the actual path to this repository.

**Important notes:**
- You do **not** need to manually start the server - Claude Code automatically starts MCP servers when it launches
- After adding, restart Claude Code for the server to be available
- Verify the server is connected with `claude mcp list`

### Running the Server Manually (Development/Testing)

For development or testing outside of Claude Code:

```bash
source .venv/bin/activate
python -m src.server
```

### CLI Commands

The CLI tool manages downloading and importing card data:

```bash
source .venv/bin/activate

# Check current data status
python -m src.cli status

# Download bulk card data (~2.3 GB for all_cards)
python -m src.cli download

# Download a smaller dataset (~160 MB)
python -m src.cli download --type oracle_cards

# Force re-download even if data is current
python -m src.cli download --force

# Import downloaded JSON into SQLite database
python -m src.cli import

# Import a specific JSON file
python -m src.cli import --file path/to/cards.json
```

#### Available Data Types

| Type | Size | Cards | Description |
|------|------|-------|-------------|
| `all_cards` | ~2.3 GB | ~521,000 | Every printing in every language (default) |
| `oracle_cards` | ~160 MB | ~37,000 | One card per Oracle ID (unique cards only) |
| `default_cards` | ~500 MB | ~100,000 | Every printing in English |

> **Note:** The default `all_cards` includes every printing of every card. For example, Lightning Bolt has 150+ printings across different sets, promos, and languages. If you only need unique cards (one per Oracle ID), use `oracle_cards` for a much smaller dataset:
> ```bash
> python -m src.cli download --type oracle_cards
> ```

#### Workflow

1. **Download**: Fetches bulk JSON from Scryfall with progress bar
2. **Import**: Loads JSON into SQLite database with FTS5 indexing

If you download data separately, run `import` to load it into the database:

```bash
python -m src.cli download   # Downloads JSON file
python -m src.cli import     # Imports into SQLite (auto-detects JSON file)
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

## Card Response Fields

Each card returned includes these fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Scryfall card ID |
| `oracle_id` | string | Oracle ID (same across printings) |
| `name` | string | Card name |
| `mana_cost` | string | Mana cost (e.g., "{2}{U}{U}") |
| `cmc` | number | Mana value |
| `type_line` | string | Full type line |
| `oracle_text` | string | Rules text |
| `power` | string | Power (creatures) |
| `toughness` | string | Toughness (creatures) |
| `loyalty` | string | Starting loyalty (planeswalkers) |
| `colors` | array | Card colors (W, U, B, R, G) |
| `color_identity` | array | Commander color identity |
| `keywords` | array | Keyword abilities |
| `set` | string | Set code |
| `set_name` | string | Full set name |
| `rarity` | string | common, uncommon, rare, mythic |
| `artist` | string | Card artist |
| `released_at` | string | Release date (YYYY-MM-DD) |
| `flavor_text` | string | Flavor text |
| `collector_number` | string | Collector number |
| `image_uris` | object | Image URLs (small, normal, large, etc.) |
| `legalities` | object | Format legality map |
| `prices` | object | Price data (usd, eur, tix) |

## Query Syntax

See [SUPPORTED_SYNTAX.md](SUPPORTED_SYNTAX.md) for full documentation.

**Supported (19 filter types):**
- Name: `"Lightning Bolt"` (exact), `!"Lightning Bolt"` (strict), `bolt` (partial)
- Colors: `c:blue`, `c:urg`, `c>=rg`, `c<=w`
- Color Identity: `id:esper`, `ci:rg`, `identity:gruul`
- Mana Value: `cmc:3`, `cmc>=5`, `mv<2`
- Type: `t:creature`, `t:"legendary creature"`
- Oracle Text: `o:flying`, `o:"enters the battlefield"`
- Flavor Text: `ft:"flavor text"`, `flavor:dragon`
- Keywords: `kw:flying`, `keyword:trample`
- Set: `set:neo`, `e:m19`
- Rarity: `r:mythic`, `r:rare`
- Format: `f:standard`, `f:modern`, `legal:commander`
- Power: `pow:3`, `pow>=4`, `power<2`
- Toughness: `tou:4`, `tou>=5`, `toughness<3`
- Loyalty: `loy:3`, `loy>=4`, `loyalty<5`
- Artist: `a:"Rebecca Guay"`, `artist:Seb`
- Year: `year:2023`, `year>=2020`, `year<2015`
- Collector Number: `cn:123`, `cn:1a`, `number:50`
- Price: `usd<1`, `eur>=10`, `tix<5`
- Boolean: implicit AND, `OR`, `-` (negation), `(` `)` grouping

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
