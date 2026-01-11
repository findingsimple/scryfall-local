# Supported Scryfall Query Syntax

This document describes the query syntax supported by the Scryfall Local MCP server.

## Currently Supported

### Name Search

| Syntax | Description | Example |
|--------|-------------|---------|
| `"card name"` | Exact name match (case-insensitive) | `"Lightning Bolt"` |
| `!"card name"` | Strict exact match (case-sensitive) | `!"Lightning Bolt"` |
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

### Color Identity

For Commander deck building - includes colors in mana cost, rules text, and color indicators.

| Syntax | Description | Example |
|--------|-------------|---------|
| `id:colors` | Cards with this identity | `id:rg`, `id:wubrg` |
| `id:name` | Named color combination | `id:esper`, `id:gruul` |
| `id<=colors` | Identity subset (for Commander) | `id<=rg` (fits in Gruul deck) |
| `identity:` | Alias for id: | `identity:boros` |
| `ci:` | Alias for id: | `ci:ub` |

**Named Combinations:**
- **Guilds:** azorius, dimir, rakdos, gruul, selesnya, orzhov, izzet, golgari, boros, simic
- **Shards:** bant, esper, grixis, jund, naya
- **Wedges:** abzan, jeskai, sultai, mardu, temur

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

### Mana Cost (Symbols)

| Syntax | Description | Example |
|--------|-------------|---------|
| `m:{symbols}` | Contains mana symbols | `m:{R}`, `m:{U}{U}` |
| `m={symbols}` | Exact mana cost | `m={R}`, `m={2}{U}{U}` |
| `mana:{symbols}` | Alias for m: | `mana:{W}{W}` |

**Symbol Format:**
- Use curly braces: `{R}`, `{U}`, `{B}`, `{W}`, `{G}`
- Generic mana: `{1}`, `{2}`, `{3}`, etc.
- Colorless: `{C}`
- Variable: `{X}`
- Hybrid: `{W/U}`, `{2/B}`, etc.

**Examples:**
```
# Find cards with two blue mana in cost
m:{U}{U}

# Find cards with exactly {R} mana cost
m={R}

# Find cards costing 4 generic + 2 red
m:{4}{R}{R}

# Combine with other filters
m:{W}{W} t:creature
```

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

### Keyword Abilities

| Syntax | Description | Example |
|--------|-------------|---------|
| `kw:keyword` | Cards with keyword ability | `kw:flying`, `kw:deathtouch` |
| `kw:"multi word"` | Multi-word keywords | `kw:"first strike"` |
| `keyword:keyword` | Alias for kw: | `keyword:trample` |
| `keywords:keyword` | Alias for kw: | `keywords:vigilance` |
| `-kw:keyword` | Cards without keyword | `-kw:flying` |

**Note:** Keyword filters match the official Scryfall `keywords` field, which is more precise than searching oracle text. A card with "flying" in reminder text won't match `kw:flying` unless it actually has the Flying keyword.

**Common Keywords:**
- Combat: Flying, First Strike, Double Strike, Trample, Vigilance, Deathtouch, Lifelink, Haste, Menace, Reach
- Protection: Hexproof, Indestructible, Shroud, Ward
- Triggered: Landfall, Constellation, Magecraft
- Static: Defender, Flash, Prowess

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
| `(a OR b) c` | Parenthetical grouping | `(t:elf OR t:goblin) c:green` |

**OR Query Examples:**
```
# Blue cards or red cards
c:blue OR c:red

# Dragons or angels
t:dragon OR t:angel

# Cheap blue instants or cheap red sorceries
c:blue t:instant cmc<=2 OR c:red t:sorcery cmc<=2
```

**Parenthetical Grouping:**
```
# Green elves or green goblins
(t:elf OR t:goblin) c:green

# Rare or mythic dragons
(r:rare OR r:mythic) t:dragon

# Rare green elves or rare green goblins
c:green (t:elf OR t:goblin) r:rare
```

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

# Green creatures without flying
c:green t:creature -kw:flying

# Cards with "enters the battlefield" text
o:"enters the battlefield"
```

### Format Legality

| Syntax | Description | Example |
|--------|-------------|---------|
| `f:format` | Cards legal in format | `f:standard`, `f:modern` |
| `format:format` | Alias for f: | `format:legacy` |
| `legal:format` | Alias for f: | `legal:vintage` |

**Format Codes:**
- `standard`, `pioneer`, `modern`, `legacy`, `vintage`
- `commander`, `pauper`, `historic`, `alchemy`
- `brawl`, `penny`, `duel`, `oldschool`, `premodern`

### Power/Toughness

| Syntax | Description | Example |
|--------|-------------|---------|
| `pow:N` | Exact power | `pow:3` |
| `pow>=N` | Power >= N | `pow>=4` |
| `pow<N` | Power < N | `pow<2` |
| `pow:*` | Variable power | `pow:*` |
| `power:N` | Alias for pow: | `power:5` |
| `tou:N` | Exact toughness | `tou:4` |
| `tou>=N` | Toughness >= N | `tou>=5` |
| `tou<N` | Toughness < N | `tou<3` |
| `toughness:N` | Alias for tou: | `toughness:7` |

### Loyalty

For planeswalker cards.

| Syntax | Description | Example |
|--------|-------------|---------|
| `loy:N` | Exact loyalty | `loy:3` |
| `loy>=N` | Loyalty >= N | `loy>=4` |
| `loy<N` | Loyalty < N | `loy<5` |
| `loyalty:N` | Alias for loy: | `loyalty:4` |

### Flavor Text

| Syntax | Description | Example |
|--------|-------------|---------|
| `ft:word` | Cards with word in flavor text | `ft:doom` |
| `ft:"phrase"` | Cards with phrase in flavor text | `ft:"the dead shall rise"` |
| `flavor:word` | Alias for ft: | `flavor:dragon` |

### Collector Number

| Syntax | Description | Example |
|--------|-------------|---------|
| `cn:N` | Exact collector number | `cn:123` |
| `cn:code` | Collector number with suffix | `cn:1a` |
| `cn>N` | Collector number > N | `cn>100` |
| `number:N` | Alias for cn: | `number:50` |

### Price

| Syntax | Description | Example |
|--------|-------------|---------|
| `usd<N` | USD price < N | `usd<1` |
| `usd>=N` | USD price >= N | `usd>=10` |
| `eur<N` | EUR price < N | `eur<5` |
| `tix<N` | MTGO TIX < N | `tix<1` |

**Note:** Price filters only match cards with available price data.

### Artist

| Syntax | Description | Example |
|--------|-------------|---------|
| `a:name` | Cards by artist (partial match) | `a:seb` |
| `a:"full name"` | Cards by artist (quoted) | `a:"Rebecca Guay"` |
| `artist:name` | Alias for a: | `artist:Terese` |

### Year

| Syntax | Description | Example |
|--------|-------------|---------|
| `year:YYYY` | Cards released in year | `year:2023` |
| `year>=YYYY` | Released in or after year | `year>=2020` |
| `year<YYYY` | Released before year | `year<2015` |

## Planned (Not Yet Supported)

The following syntax is documented for future implementation:

### Medium Value

| Feature | Syntax | Description |
|---------|--------|-------------|
| Full oracle text | `fo:"reminder"` | Includes reminder text |
| Produces mana | `produces:g` | Cards that produce specific mana |
| Block | `b:innistrad` | Set block filtering |
| Banned in format | `banned:modern` | Cards banned in format |
| Watermark | `wm:phyrexian` | Faction/guild watermarks |

### Not Planned

The following features are intentionally out of scope for this project:

| Feature | Reason |
|---------|--------|
| Rate limiting | Designed for local use only; no external API calls during queries |
| Query caching | SQLite with FTS5 is already fast enough for local use |

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
