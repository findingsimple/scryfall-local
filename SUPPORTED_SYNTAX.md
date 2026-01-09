# Supported Scryfall Query Syntax

This document describes the query syntax supported by the Scryfall Local MCP server.

## Currently Supported

### Name Search

| Syntax | Description | Example |
|--------|-------------|---------|
| `"card name"` | Exact name match | `"Lightning Bolt"` |
| `word` | Partial name match | `bolt` |

### Colors

| Syntax | Description | Example |
|--------|-------------|---------|
| `c:color` | Cards with this color | `c:blue`, `c:u` |
| `c:colorless` | Colorless cards | `c:c`, `c:colorless` |
| `c:multicolor` | Multiple color symbols | `c:urg` (blue, red, green) |
| `c>=colors` | At least these colors | `c>=rg` (red and green, possibly more) |
| `c<=colors` | At most these colors | `c<=w` (white or colorless only) |

**Color Codes:**
- `w` or `white` - White
- `u` or `blue` - Blue
- `b` or `black` - Black
- `r` or `red` - Red
- `g` or `green` - Green
- `c` or `colorless` - Colorless

### Mana Value (CMC)

| Syntax | Description | Example |
|--------|-------------|---------|
| `cmc:N` | Exact mana value | `cmc:3` |
| `cmc=N` | Exact mana value | `cmc=3` |
| `cmc>=N` | Mana value >= N | `cmc>=5` |
| `cmc<=N` | Mana value <= N | `cmc<=2` |
| `cmc>N` | Mana value > N | `cmc>4` |
| `cmc<N` | Mana value < N | `cmc<2` |
| `mv:N` | Alias for cmc | `mv:3` |

### Type

| Syntax | Description | Example |
|--------|-------------|---------|
| `t:type` | Cards with type | `t:creature`, `t:instant` |
| `t:"type line"` | Quoted type search | `t:"legendary creature"` |
| `type:type` | Alias for t: | `type:artifact` |

### Oracle Text

| Syntax | Description | Example |
|--------|-------------|---------|
| `o:word` | Cards with word in text | `o:flying`, `o:draw` |
| `o:"phrase"` | Cards with phrase in text | `o:"enters the battlefield"` |
| `oracle:word` | Alias for o: | `oracle:flying` |
| `text:word` | Alias for o: | `text:counter` |

### Set

| Syntax | Description | Example |
|--------|-------------|---------|
| `set:code` | Cards from set | `set:neo` |
| `e:code` | Alias for set: | `e:m19` |
| `s:code` | Alias for set: | `s:cmd` |

### Rarity

| Syntax | Description | Example |
|--------|-------------|---------|
| `r:rarity` | Cards with rarity | `r:mythic`, `r:rare` |
| `r:letter` | Short rarity code | `r:m`, `r:r`, `r:u`, `r:c` |
| `rarity:rarity` | Alias for r: | `rarity:uncommon` |

**Rarity Codes:**
- `c` or `common`
- `u` or `uncommon`
- `r` or `rare`
- `m` or `mythic`

### Boolean Operators

| Syntax | Description | Example |
|--------|-------------|---------|
| `term term` | Implicit AND | `c:blue t:instant` |
| `term OR term` | Logical OR | `c:blue OR c:red` |
| `-term` | Negation (NOT) | `-t:creature` |
| `(terms)` | Grouping | `(c:blue OR c:red) t:instant` |

## Complex Query Examples

```
# Blue instant cards with CMC 2 or less
c:blue t:instant cmc<=2

# Dragons with flying
t:dragon o:flying

# Multicolor legendary creatures
c>=ur t:"legendary creature"

# Mythic rares from Core Set 2019
set:m19 r:mythic

# Red or green cards that aren't creatures
(c:red OR c:green) -t:creature

# Cards with "enters the battlefield" text
o:"enters the battlefield"
```

## Planned (Not Yet Supported)

The following syntax is documented for future implementation:

| Feature | Syntax | Status |
|---------|--------|--------|
| Format legality | `f:standard`, `f:modern` | Planned |
| Power/Toughness | `pow:3`, `tou>=4` | Planned |
| Prices | `usd<1`, `usd>=10` | Planned |
| Artist | `a:"Rebecca Guay"` | Planned |
| Year | `year:2023` | Planned |
| Mana symbols | `m:{2}{U}{U}` | Planned |

When using unsupported syntax, the server returns a helpful error message with suggestions for supported alternatives.

## Error Handling

If you use unsupported syntax, you'll receive an error like:

```json
{
  "error": "Format legality is not yet supported",
  "hint": "'f:standard, f:modern' syntax will be added in a future version",
  "supported_syntax": [
    "name search: \"Lightning Bolt\" (exact) or bolt (partial)",
    "colors: c:blue, c:urg, c>=rg, c<=w, c:c (colorless)",
    ...
  ]
}
```
