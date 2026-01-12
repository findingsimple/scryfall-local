# Supported Scryfall Query Syntax

This document describes the query syntax supported by the Scryfall Local MCP server.

## Currently Supported

### Name Search

| Syntax | Description | Example |
|--------|-------------|---------|
| `"card name"` | Exact name match (case-insensitive) | `"Lightning Bolt"` |
| `'card name'` | Exact name match (single quotes) | `'Ach! Hans, Run!'` |
| `!"card name"` | Strict exact match (case-sensitive) | `!"Lightning Bolt"` |
| `!'card name'` | Strict exact match (single quotes) | `!'Question Elemental?'` |
| `word` | Partial name match | `bolt` |

**Quote Style Tips:**
- Use double quotes `"..."` for names with apostrophes: `"Urza's Tower"`
- Use single quotes `'...'` for names with `!`, `?`, or parentheses: `'Ach! Hans, Run!'`

**Partial Name Special Characters:**
Unquoted partial names support these characters:
- Accented Latin letters: `Séance`, `Lim-Dûl`, `Márton`
- Apostrophes: `Urza's`, `Al-abara's`
- Periods: `Dr.`, `B.F.M.`
- Ampersands: `R&D`
- Commas: `Hans,`
- Hyphens: `Lim-Dûl`, `Will-o'-the-Wisp`

For `!`, `?`, `()`, or `:` in names, use quotes: `'Question Elemental?'`

### Colors

| Syntax | Description | Example |
|--------|-------------|---------|
| `c:color` | Cards with this color | `c:blue`, `c:u` |
| `c:colorless` | Colorless cards | `c:c`, `c:colorless` |
| `c:multicolor` | Multiple color symbols | `c:urg` (blue, red, green) |
| `c>=colors` | At least these colors | `c>=rg` (red and green, possibly more) |
| `c<=colors` | At most these colors | `c<=w` (white or colorless only) |
| `c>colors` | Strict superset (has all + more) | `c>rg` (RG plus at least one more color) |
| `c<colors` | Strict subset (fewer colors) | `c<rg` (only R, only G, or colorless) |

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
| `id>=colors` | At least these colors in identity | `id>=rg` (has R and G, possibly more) |
| `id<=colors` | Identity subset (for Commander) | `id<=rg` (fits in Gruul deck) |
| `id>colors` | Strict superset identity | `id>rg` (has RG plus at least one more) |
| `id<colors` | Strict subset identity | `id<rg` (only R, only G, or colorless) |
| `identity:` | Alias for id: | `identity:boros` |
| `ci:` | Alias for id: | `ci:ub` |

**Named Combinations:**
- **Guilds:** azorius, dimir, rakdos, gruul, selesnya, orzhov, izzet, golgari, boros, simic
- **Shards:** bant, esper, grixis, jund, naya
- **Wedges:** abzan, jeskai, sultai, mardu, temur

### Negation Semantics for Colors

When negating color or color identity filters, the behavior is as follows:

| Syntax | Meaning | Returns |
|--------|---------|---------|
| `-c:blue` | NOT blue | Cards without blue in their colors |
| `-c:urg` | NOT (blue AND red AND green) | Cards missing ANY of U, R, or G |
| `-id:esper` | NOT (white AND blue AND black) | Cards missing ANY of W, U, or B in identity |

**Important:** Negation excludes cards that have ANY of the specified colors, not cards that have ALL of them. This means:
- `-c:urg` returns cards that are NOT blue OR NOT red OR NOT green (i.e., missing at least one)
- To find cards that aren't exactly Temur-colored, use a different approach

**Examples:**
```
# Cards that aren't blue (no blue anywhere in colors)
-c:blue

# Cards that don't have ALL of red, green, and blue
# (This includes mono-red, mono-green, Gruul, etc.)
-c:urg

# Cards that can't go in an Esper commander deck
# (Has colors outside of WUB)
-id<=esper

# Colorless cards (no colors at all)
c:colorless
```

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

### Full Oracle Text

| Syntax | Description | Example |
|--------|-------------|---------|
| `fo:text` | Search oracle text (alias for o:) | `fo:flying` |
| `fo:"phrase"` | Search oracle text with phrase | `fo:"enters the battlefield"` |

**Note:** `fo:` is an alias for `o:` since our oracle_text field already includes reminder text.

### Produces Mana

| Syntax | Description | Example |
|--------|-------------|---------|
| `produces:color` | Cards that produce this mana | `produces:g` |
| `produces:colors` | Cards that produce all colors | `produces:wubrg` |

### Banned in Format

| Syntax | Description | Example |
|--------|-------------|---------|
| `banned:format` | Cards banned in format | `banned:modern` |

Supported formats: standard, future, historic, timeless, gladiator, pioneer, modern, legacy, pauper, vintage, penny, commander, oathbreaker, standardbrawl, brawl, alchemy, paupercommander, duel, oldschool, premodern, predh.

### Block

| Syntax | Description | Example |
|--------|-------------|---------|
| `b:block` | Cards from a block | `b:innistrad` |
| `block:block` | Alias for b: | `block:zendikar` |

Supported blocks: ice age, mirage, tempest, urza, masques, invasion, odyssey, onslaught, mirrodin, kamigawa, ravnica, time spiral, lorwyn, shadowmoor, alara, zendikar, scars, innistrad, return to ravnica, theros, khans, tarkir, battle for zendikar, shadows, kaladesh, amonkhet, ixalan.

**Note:** Blocks were discontinued by Wizards after Ixalan (2017).

### Watermark

| Syntax | Description | Example |
|--------|-------------|---------|
| `wm:name` | Cards with watermark | `wm:phyrexian` |
| `watermark:name` | Alias for wm: | `watermark:selesnya` |

Common watermarks: phyrexian, mirran, selesnya, dimir, golgari, boros, orzhov, izzet, gruul, azorius, simic, rakdos, riveteers, obscura, maestros, cabaretti, brokers.

### Layout

| Syntax | Description | Example |
|--------|-------------|---------|
| `layout:type` | Cards with specific layout | `layout:transform` |
| `-layout:type` | Cards without layout | `-layout:normal` |

**Layout Types:**
- `normal` - Standard single-faced cards
- `transform` - Double-faced cards that transform (e.g., Delver of Secrets)
- `modal_dfc` - Modal double-faced cards (e.g., Shatterskull Smashing)
- `split` - Split cards (e.g., Fire // Ice)
- `adventure` - Adventure cards (e.g., Bonecrusher Giant)
- `flip` - Flip cards (e.g., Akki Lavarunner)
- `meld` - Meld cards (e.g., Bruna, the Fading Light)
- `leveler` - Level Up cards
- `saga` - Saga enchantments
- `class` - Class enchantments
- `prototype` - Prototype cards
- `reversible_card` - Reversible cards

**Examples:**
```
# Find all transform cards
layout:transform

# Find adventure cards that are creatures
layout:adventure t:creature

# Find all double-faced cards (transform or modal)
layout:transform OR layout:modal_dfc
```

### Produces Token

| Syntax | Description | Example |
|--------|-------------|---------|
| `pt:name` | Cards that create this token | `pt:zombie` |
| `pt:"token name"` | Quoted token name | `pt:"Goblin Token"` |
| `produces_token:name` | Alias for pt: | `produces_token:soldier` |
| `-pt:name` | Cards that don't create token | `-pt:zombie` |

**Examples:**
```
# Find cards that create Zombie tokens
pt:zombie

# Find cards that create Goblin tokens (creatures)
pt:goblin t:creature

# Find cards that create tokens but not Zombie tokens
-pt:zombie kw:token
```

**Note:** This filter searches the `produces_tokens` field, which is extracted from Scryfall's `all_parts` data. Only entries with `component: "token"` are included; meld parts, combo pieces, and other related cards are not counted.

## Planned Features

Features that could be implemented to achieve fuller Scryfall parity:

### High Priority

- [ ] **restricted:format** - Cards restricted (1-of) in a format
  - Syntax: `restricted:vintage`
  - Similar to `banned:` but checks for "restricted" status in legalities

- [ ] **is: filters** - Card characteristic flags
  - Syntax: `is:reserved`, `is:reprint`, `is:promo`, `is:digital`, `is:full`, `is:foil`, `is:nonfoil`, `is:etched`
  - Requires extracting fields from raw_data: `reserved`, `reprint`, `promo`, `digital`, `full_art`, `foil`, `nonfoil`

- [ ] **game: filter** - Platform availability
  - Syntax: `game:paper`, `game:arena`, `game:mtgo`
  - Requires `games` array from raw_data

- [ ] **lang: filter** - Card language
  - Syntax: `lang:en`, `lang:ja`, `lang:de`, `lang:ko`
  - Requires `lang` field from raw_data

- [ ] **unique: filter** - Deduplicate results
  - Syntax: `unique:cards` (by oracle_id), `unique:art` (by illustration_id), `unique:prints` (all)
  - Requires grouping logic in query execution

- [ ] **order:/direction:** - Sort results
  - Syntax: `order:name`, `order:cmc`, `order:released`, `order:usd`, `direction:asc`, `direction:desc`
  - Requires ORDER BY clause in SQL

### Medium Priority

- [ ] **frame: filter** - Card frame style
  - Syntax: `frame:2015`, `frame:modern`, `frame:old`, `frame:future`
  - Requires `frame` field from raw_data

- [ ] **border: filter** - Card border color
  - Syntax: `border:black`, `border:white`, `border:silver`, `border:gold`, `border:borderless`
  - Requires `border_color` field from raw_data

- [ ] **date: filter** - Exact release date
  - Syntax: `date:2023-01-01`, `date>=2020-06-15`, `date<2019-01-01`
  - Uses existing `released_at` column with full date comparison

- [ ] **prints: filter** - Number of printings
  - Syntax: `prints:1` (only one printing), `prints>=10` (many printings)
  - Requires subquery counting by oracle_id

- [ ] **stamp: filter** - Security stamp type
  - Syntax: `stamp:oval`, `stamp:acorn`, `stamp:triangle`, `stamp:arena`, `stamp:heart`
  - Requires `security_stamp` field from raw_data

### Lower Priority

- [ ] **art: filter** - Art treatment
  - Syntax: `is:fullart`, `is:extendedart`, `art:full`, `art:extended`
  - Requires `full_art` field from raw_data

- [ ] **illustration: filter** - Specific illustration
  - Syntax: `illustration:uuid`
  - Requires `illustration_id` field from raw_data

- [ ] **new: filter** - Changed elements in reprints
  - Syntax: `new:art`, `new:flavor`, `new:frame`, `new:artist`
  - Complex: requires comparing against other printings

- [ ] **powtou: filter** - Combined power/toughness total
  - Syntax: `powtou>=6` (combined total >= 6)
  - Requires calculating sum of power and toughness

- [ ] **devotion: filter** - Mana symbol count in cost
  - Syntax: `devotion:R>=3` (3+ red symbols in cost)
  - Requires parsing mana_cost string

- [ ] **re:/regex: filter** - Regex pattern matching
  - Syntax: `re:"^Lightning"`, `regex:"bolt$"`
  - SQLite supports REGEXP with custom function

- [ ] **is:commander filter** - Can be commander
  - Syntax: `is:commander`
  - Requires checking type_line for "Legendary Creature" or specific text

- [ ] **is:spell/is:permanent** - Card category
  - Syntax: `is:spell`, `is:permanent`
  - Derived from type_line

- [ ] **is:vanilla** - No rules text
  - Syntax: `is:vanilla`
  - Check for empty/null oracle_text (excluding reminder text)

- [ ] **is:funny** - Un-set cards
  - Syntax: `is:funny`
  - Requires checking set type or `set_type` field

- [ ] **include:extras** - Include tokens/emblems
  - Syntax: `include:extras`
  - Currently may already include these; toggle to exclude

### Implementation Notes

**Database columns that may need adding:**
- `frame` (text) - frame style
- `border_color` (text) - border color
- `lang` (text) - language code
- `games` (text/JSON) - platform availability
- `reserved` (boolean) - reserved list
- `reprint` (boolean) - is a reprint
- `promo` (boolean) - is a promo
- `digital` (boolean) - digital-only
- `full_art` (boolean) - full art treatment
- `security_stamp` (text) - stamp type
- `illustration_id` (text) - illustration UUID

**Query execution changes:**
- `unique:` requires GROUP BY or DISTINCT ON logic
- `order:` requires dynamic ORDER BY clause
- `prints:` requires COUNT subquery

## Not Planned

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
  "error": "Unbalanced parentheses: missing closing ')'",
  "hint": "Check that all opening parentheses have matching closing parentheses",
  "supported_syntax": "Supports: name, colors (c:blue), mana value (cmc:3), ..."
}
```
