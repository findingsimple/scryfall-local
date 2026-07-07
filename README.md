# Scryfall Local MCP Server

A local MCP (Model Context Protocol) server that caches Scryfall's Magic: The Gathering card data, enabling Claude to answer questions about MTG cards with up-to-date information without hitting Scryfall's rate limits.

## Features

- **6 MCP Tools**: search_cards, get_card, get_cards_batch, random_card, data_status, refresh_data
- **Scryfall Query Syntax**: Supports colors, mana value, type, oracle text, set, rarity, and boolean operators
- **SQLite Storage**: Efficient database with FTS5 for fast text search (~300MB for oracle_cards)
- **Security-First**: Parameterized queries, URL validation, path traversal prevention
- **Agentic-Optimized**: Structured JSON responses, batch operations, helpful error messages

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Clone the repository
git clone <repo-url>
cd scryfall-local

# Install dependencies (including dev deps) from lockfile
uv sync
```

## Usage

### Adding to Claude Code

Register the MCP server using the Claude Code CLI:

```bash
# Add for all projects (user scope)
claude mcp add scryfall-local --scope user -- /bin/bash -c "cd /path/to/scryfall-local && .venv/bin/python -m src.server"

# Or add for current project only (local scope)
claude mcp add scryfall-local -- /bin/bash -c "cd /path/to/scryfall-local && .venv/bin/python -m src.server"
```

Replace `/path/to/scryfall-local` with the actual path to this repository.

This produces the following entry in `~/.claude.json` (or `.claude/settings.json` for local scope):

```json
"scryfall-local": {
  "command": "/bin/bash",
  "args": ["-c", "cd /path/to/scryfall-local && .venv/bin/python -m src.server"],
  "type": "stdio"
}
```

> **Note:** The `cd &&` wrapper is used instead of the `cwd` field because the VS Code extension [ignores `cwd`](https://github.com/anthropics/claude-code/issues/43422), causing module path collisions when multiple MCP servers share the same `-m src.server` entry point.

**Important notes:**
- You do **not** need to manually start the server - Claude Code automatically starts MCP servers when it launches
- After adding, restart Claude Code for the server to be available
- Verify the server is connected with `claude mcp list`

### Adding via Project Configuration

Alternatively, add this snippet to your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "scryfall-local": {
      "command": "/bin/bash",
      "args": ["-c", "cd /path/to/scryfall-local && .venv/bin/python -m src.server"],
      "type": "stdio"
    }
  }
}
```

Or to your user settings at `~/.claude/settings.json` to make it available across all projects.

### Running the Server Manually (Development/Testing)

For development or testing outside of Claude Code:

```bash
uv run python -m src.server
```

### CLI Commands

The CLI tool manages downloading and importing card data:

```bash
# Check current data status
uv run python -m src.cli status

# Download bulk card data (~160 MB for oracle_cards)
uv run python -m src.cli download

# Download a larger dataset with all printings (~2.3 GB)
uv run python -m src.cli download --type all_cards

# Force re-download even if data is current
uv run python -m src.cli download --force

# Import downloaded JSON into SQLite database
uv run python -m src.cli import

# Import a specific JSON file
uv run python -m src.cli import --file path/to/cards.json
```

#### Available Data Types

| Type | Size | Cards | Description |
|------|------|-------|-------------|
| `oracle_cards` | ~160 MB | ~37,000 | One card per Oracle ID (unique cards only) - **default** |
| `all_cards` | ~2.3 GB | ~521,000 | Every printing in every language |
| `default_cards` | ~500 MB | ~100,000 | Every printing in English |

> **Note:** The default `oracle_cards` includes one unique card per Oracle ID - ideal for most use cases. If you need every printing (different sets, promos, languages), use `all_cards`:
> ```bash
> python -m src.cli download --type all_cards
> ```

#### Workflow

1. **Download**: Fetches bulk JSON from Scryfall with progress bar
2. **Import**: Loads JSON into SQLite database with FTS5 indexing

If you download data separately, run `import` to load it into the database:

```bash
uv run python -m src.cli download   # Downloads JSON file
uv run python -m src.cli import     # Imports into SQLite (auto-detects JSON file)
```

> **Atomic download:** Data is written to a temporary file and atomically renamed on completion, preventing partial files if interrupted.
>
> **Atomic import:** Cards are loaded into a temporary database, then swapped into place in a single operation. If import fails mid-way, the existing database is untouched.

## MCP Tools

### search_cards
Search for cards using Scryfall syntax.
```
{"query": "c:blue t:instant cmc<=2", "limit": 10}
```

### get_card
Get a single card by name or Scryfall ID. Name matching is case-insensitive,
and the front-face name is enough for double-faced cards.
```
{"name": "lightning bolt"}
{"name": "Delver of Secrets"}
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
| `layout` | string | Card layout (normal, transform, modal_dfc, split, adventure, etc.) |
| `produced_mana` | array | Mana colors this card can produce |
| `watermark` | string | Guild/faction watermark |
| `produces_tokens` | array | Names of tokens this card creates |
| `image_uris` | object | Image URLs (small, normal, large, etc.) |
| `legalities` | object | Format legality map |
| `prices` | object | Price data (usd, eur, tix) |

## Query Syntax

See [SUPPORTED_SYNTAX.md](SUPPORTED_SYNTAX.md) for full documentation.

**Supported (25 filter types):**
- Name: `"Lightning Bolt"` (exact), `'Ach! Hans, Run!'` (single quotes), `bolt` (partial), `Séance` (accented)
- Colors: `c:blue`, `c:urg`, `c>=rg`, `c<=w`, `c>rg`, `c<rg`
- Color Identity: `id:esper`, `ci:rg`, `id<=rg`, `id>rg`
- Mana Value: `cmc:3`, `cmc>=5`, `mv<2`
- Type: `t:creature`, `t:"legendary creature"`
- Oracle Text: `o:flying`, `o:"enters the battlefield"`, `fo:reminder`
- Flavor Text: `ft:"flavor text"`, `flavor:dragon`
- Keywords: `kw:flying`, `keyword:trample`
- Set: `set:neo`, `e:m19`
- Rarity: `r:mythic`, `r:rare`
- Format: `f:standard`, `f:modern`, `legal:commander`
- Banned: `banned:modern`, `banned:legacy`
- Block: `b:innistrad`, `block:zendikar`
- Produces Mana: `produces:g`, `produces:wubrg`
- Watermark: `wm:phyrexian`, `watermark:selesnya`
- Layout: `layout:transform`, `layout:adventure`, `layout:modal_dfc`
- Produces Token: `pt:zombie`, `produces_token:"Goblin Token"`
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
uv run pytest -v
```

### Test Coverage

```bash
uv run pytest --cov=src --cov-report=term-missing
```

## Architecture

```
scryfall-local/
├── src/
│   ├── server.py          # MCP server (low-level Server class)
│   ├── data_manager.py    # Download/cache bulk data
│   ├── query_parser.py    # Scryfall syntax parser
│   ├── card_store.py      # Card storage (SQLite + FTS5)
│   └── import_utils.py    # Streaming import with atomic DB swap
├── tests/                  # Unit and integration tests
├── data/                   # Cached bulk data (gitignored)
└── pyproject.toml
```

## License

MIT
