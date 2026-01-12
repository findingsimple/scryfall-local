"""Scryfall query syntax parser.

Parses Scryfall-style queries into structured filter objects.
Supports: name, colors, cmc, type, oracle text, set, rarity.
Boolean operators: implicit AND, explicit OR, negation (-).
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Supported syntax for error messages
# Brief summary for tool descriptions
SYNTAX_SUMMARY = (
    "Supports: name, colors (c:blue), mana value (cmc:3), mana cost (m:{R}{R}), type (t:creature), "
    "oracle text (o:flying), set (set:neo), rarity (r:mythic), format (f:modern), "
    "power/toughness (pow:3, tou:4), keywords (kw:flying), artist (a:name), year (year:2023), "
    "produces token (pt:zombie). Boolean operators: implicit AND, OR, - (negation), (parentheses)."
)

# Detailed list for error messages
SUPPORTED_SYNTAX = [
    'name search: "Lightning Bolt" (exact), bolt (partial), !"Exact Name" (strict)',
    "colors: c:blue, c:urg, c>=rg, c<=w, c:c (colorless)",
    "color identity: id:wubrg, identity:esper, ci:rg (for Commander)",
    "mana value: cmc:3, cmc>=5, cmc<2, mv:3",
    "mana cost: m:{R}, m:{2}{U}{U}, mana:{W}{W} (exact symbols)",
    "type: t:creature, t:\"legendary creature\"",
    "oracle text: o:flying, o:\"enters the battlefield\"",
    "keyword ability: kw:flying, keyword:deathtouch, keywords:vigilance",
    "set: set:neo, e:m19, s:cmd",
    "rarity: r:mythic, r:rare, r:uncommon, r:common",
    "format: f:standard, f:modern, f:legacy, f:vintage, f:commander",
    "power: pow:3, pow>=4, power<2",
    "toughness: tou:3, tou>=4, toughness<2",
    "loyalty: loy:3, loy>=4, loyalty<5 (planeswalkers)",
    "artist: a:\"Rebecca Guay\", artist:Seb",
    "year: year:2023, year>=2020, year<2015",
    "flavor text: ft:\"flavor text\" (search flavor text)",
    "collector number: cn:123, cn:1a (find specific printings)",
    "price: usd<1, usd>=10, eur<5",
    "produces token: pt:zombie, produces_token:\"Goblin Token\" (find token creators)",
    "boolean: implicit AND, OR, - (negation), parentheses",
]

# Color name to symbol mapping
COLOR_MAP = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
    "w": "W",
    "u": "U",
    "b": "B",
    "r": "R",
    "g": "G",
    "c": "",  # Colorless
    "colorless": "",
}

# Rarity short to full mapping
RARITY_MAP = {
    "c": "common",
    "u": "uncommon",
    "r": "rare",
    "m": "mythic",
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "mythic": "mythic",
}

# Named color identity combinations (guilds, shards, wedges)
IDENTITY_MAP = {
    # Mono colors
    "white": ["W"], "blue": ["U"], "black": ["B"], "red": ["R"], "green": ["G"],
    "colorless": [],
    # Guilds (2 color)
    "azorius": ["W", "U"], "dimir": ["U", "B"], "rakdos": ["B", "R"],
    "gruul": ["R", "G"], "selesnya": ["G", "W"], "orzhov": ["W", "B"],
    "izzet": ["U", "R"], "golgari": ["B", "G"], "boros": ["R", "W"],
    "simic": ["G", "U"],
    # Shards (3 color)
    "bant": ["G", "W", "U"], "esper": ["W", "U", "B"], "grixis": ["U", "B", "R"],
    "jund": ["B", "R", "G"], "naya": ["R", "G", "W"],
    # Wedges (3 color)
    "abzan": ["W", "B", "G"], "jeskai": ["U", "R", "W"], "sultai": ["B", "G", "U"],
    "mardu": ["R", "W", "B"], "temur": ["G", "U", "R"],
    # 4 color
    "chaos": ["U", "B", "R", "G"], "aggression": ["B", "R", "G", "W"],
    "altruism": ["R", "G", "W", "U"], "growth": ["G", "W", "U", "B"],
    "artifice": ["W", "U", "B", "R"],
    # 5 color
    "wubrg": ["W", "U", "B", "R", "G"], "fivecolor": ["W", "U", "B", "R", "G"],
}


class QueryError(Exception):
    """Error parsing a query with helpful hints."""

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        supported_syntax: list[str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.hint = hint or "Check the query syntax"
        self.supported_syntax = supported_syntax or SUPPORTED_SYNTAX

    def __str__(self) -> str:
        return f"{self.message}. Hint: {self.hint}"


@dataclass
class ParsedQuery:
    """Structured representation of a parsed query."""

    filters: dict[str, Any] = field(default_factory=dict)
    or_groups: list[list[dict[str, Any]]] = field(default_factory=list)
    has_or_clause: bool = False
    raw_query: str = ""

    @property
    def is_empty(self) -> bool:
        """Check if query has no filters."""
        return len(self.filters) == 0 and not self.has_or_clause

    @property
    def filter_count(self) -> int:
        """Count total number of filters."""
        return len(self.filters)

    def __str__(self) -> str:
        """Human-readable representation."""
        parts = []
        for key, value in self.filters.items():
            parts.append(f"{key}={value}")
        if self.has_or_clause:
            parts.append(f"OR groups: {len(self.or_groups)}")
        return f"ParsedQuery({', '.join(parts)})"


def _parse_color_value(value: str) -> list[str]:
    """Parse color value into list of color symbols."""
    value = value.lower()

    # Handle colorless
    if value in ("c", "colorless"):
        return []

    # Handle color names
    if value in COLOR_MAP and value not in "wubrgc":
        mapped = COLOR_MAP[value]
        return [mapped] if mapped else []

    # Handle multiple color symbols (e.g., "urg")
    colors = []
    for char in value:
        if char.lower() in COLOR_MAP:
            mapped = COLOR_MAP[char.lower()]
            if mapped:
                colors.append(mapped)
    return colors


def _parse_identity_value(value: str) -> list[str]:
    """Parse color identity value into list of color symbols.

    Supports named combinations like 'esper', 'grixis', etc.
    """
    value = value.lower()

    # Check for named combinations first
    if value in IDENTITY_MAP:
        return IDENTITY_MAP[value]

    # Handle colorless
    if value in ("c", "colorless"):
        return []

    # Handle color symbols (e.g., "wubrg", "rg")
    colors = []
    for char in value:
        if char.lower() in COLOR_MAP:
            mapped = COLOR_MAP[char.lower()]
            if mapped:
                colors.append(mapped)
    return colors


# Token patterns (order matters - more specific patterns first)
TOKEN_PATTERNS = [
    # Filter patterns with operators
    (r'(?:id|identity|ci)(>=|<=|>|<|=|!=|:)([a-zA-Z]+)', 'COLOR_IDENTITY'),
    (r'(?:c|color|colors)(>=|<=|>|<|=|!=|:)([a-zA-Z]+)', 'COLOR'),
    (r'(?:cmc|mv|manavalue)(>=|<=|>|<|=|!=|:)(\d+(?:\.\d+)?)', 'CMC'),
    (r'(?:t|type):"([^"]+)"', 'TYPE_QUOTED'),
    (r'(?:t|type):([a-zA-Z]+)', 'TYPE'),
    (r'(?:o|oracle|text):"([^"]+)"', 'ORACLE_QUOTED'),
    (r'(?:o|oracle|text):([a-zA-Z]+)', 'ORACLE'),
    (r'(?:ft|flavor):"([^"]+)"', 'FLAVOR_QUOTED'),
    (r'(?:ft|flavor):([a-zA-Z]+)', 'FLAVOR'),
    # Full oracle text (includes reminder text) - fo: is alias for o: since oracle_text already has reminder text
    (r'(?:fo|fulloracle):"([^"]+)"', 'FULL_ORACLE_QUOTED'),
    (r'(?:fo|fulloracle):([a-zA-Z]+)', 'FULL_ORACLE'),
    (r'(?:set|e|s|edition):([a-zA-Z0-9]+)', 'SET'),
    (r'(?:r|rarity):([a-zA-Z]+)', 'RARITY'),
    (r'(?:f|format|legal|legality):([a-zA-Z]+)', 'FORMAT'),
    # Banned in format (e.g., banned:modern)
    (r'banned:([a-zA-Z]+)', 'BANNED'),
    # Block filter (e.g., b:innistrad, block:zendikar)
    (r'(?:b|block):([a-zA-Z]+)', 'BLOCK'),
    # Produces mana filter (e.g., produces:g, produces:wubrg)
    (r'produces:([a-zA-Z]+)', 'PRODUCES'),
    # Watermark filter (e.g., wm:phyrexian, watermark:selesnya)
    (r'(?:wm|watermark):([a-zA-Z]+)', 'WATERMARK'),
    # Layout filter (e.g., layout:transform, layout:modal_dfc, layout:adventure)
    (r'layout:([a-zA-Z_]+)', 'LAYOUT'),
    # Produces token filter (e.g., pt:zombie, produces_token:"Goblin Token")
    (r'(?:pt|produces_token):"([^"]+)"', 'PRODUCES_TOKEN_QUOTED'),
    (r'(?:pt|produces_token):([a-zA-Z]+)', 'PRODUCES_TOKEN'),
    (r'(?:kw|keyword|keywords):"([^"]+)"', 'KEYWORD_QUOTED'),
    (r'(?:kw|keyword|keywords):([a-zA-Z]+)', 'KEYWORD'),
    (r'(?:pow|power)(>=|<=|>|<|=|!=|:)(\d+|\*)', 'POWER'),
    (r'(?:tou|toughness)(>=|<=|>|<|=|!=|:)(\d+|\*)', 'TOUGHNESS'),
    (r'(?:loy|loyalty)(>=|<=|>|<|=|!=|:)(\d+)', 'LOYALTY'),
    (r'(?:cn|number)(>=|<=|>|<|=|!=|:)([a-zA-Z0-9]+)', 'COLLECTOR_NUMBER'),
    (r'(?:usd|eur|tix)(>=|<=|>|<|=|!=|:)(\d+(?:\.\d+)?)', 'PRICE'),
    (r'(?:a|artist):"([^"]+)"', 'ARTIST_QUOTED'),
    (r'(?:a|artist):([a-zA-Z][a-zA-Z0-9_-]*)', 'ARTIST'),
    (r'year(>=|<=|>|<|=|!=|:)(\d{4})', 'YEAR'),
    # Mana cost pattern (e.g., m:{R}{R}, mana:{2}{U}{U})
    (r'(?:m|mana)(=|:)((?:\{[^}]+\})+)', 'MANA'),
    # Boolean operators
    (r'\bOR\b', 'OR'),
    (r'-', 'NEGATION'),
    (r'\(', 'LPAREN'),
    (r'\)', 'RPAREN'),
    # Name patterns - strict exact match with ! prefix comes first
    # Support both double quotes and single quotes for flexibility
    (r'!"([^"]+)"', 'STRICT_NAME'),
    (r"!'([^']+)'", 'STRICT_NAME'),  # Single-quote variant
    (r'"([^"]+)"', 'EXACT_NAME'),
    (r"'([^']+)'", 'EXACT_NAME'),  # Single-quote variant for names with special chars
    # Partial name allows:
    # - ASCII and accented Latin letters (a-zA-Z plus \u00C0-\u024F for é, û, ö, etc.)
    # - Numbers, underscores, hyphens, apostrophes
    # - Common punctuation in card names: comma, period, ampersand
    # This supports names like "Urza's", "Séance", "Lim-Dûl", "Dr.", "R&D", "Hans,"
    (r"([a-zA-Z\u00C0-\u024F][a-zA-Z0-9\u00C0-\u024F_',.&-]*)", 'PARTIAL_NAME'),
]


class QueryParser:
    """Parser for Scryfall-style queries using regex tokenization."""

    def __init__(self):
        # Compile token patterns
        self._patterns = [
            (re.compile(pattern, re.IGNORECASE), token_type)
            for pattern, token_type in TOKEN_PATTERNS
        ]

    def parse(self, query: str) -> ParsedQuery:
        """Parse a query string into a ParsedQuery object."""
        query = query.strip()
        logger.debug("Parsing query: %r", query)

        # Handle empty query
        if not query:
            logger.debug("Empty query, returning empty ParsedQuery")
            return ParsedQuery(raw_query=query)

        try:
            tokens = self._tokenize(query)
            logger.debug("Tokenized into %d tokens", len(tokens))
            result = self._parse_tokens(tokens, query)
            logger.debug("Parsed into %d filters", result.filter_count)
            return result
        except QueryError:
            raise
        except Exception as e:
            logger.warning("Failed to parse query %r: %s", query, e)
            raise QueryError(
                f"Failed to parse query: {str(e)}",
                hint="Check the query syntax",
                supported_syntax=SUPPORTED_SYNTAX,
            ) from e

    def _tokenize(self, query: str) -> list[tuple[str, Any]]:
        """Tokenize query string."""
        tokens = []
        pos = 0

        while pos < len(query):
            # Skip whitespace
            if query[pos].isspace():
                pos += 1
                continue

            matched = False
            for pattern, token_type in self._patterns:
                match = pattern.match(query, pos)
                if match:
                    if token_type in ('COLOR', 'COLOR_IDENTITY'):
                        operator = match.group(1)
                        value = match.group(2)
                        tokens.append((token_type, (operator, value)))
                    elif token_type == 'CMC':
                        operator = match.group(1)
                        value = float(match.group(2))
                        tokens.append((token_type, (operator, value)))
                    elif token_type in ('POWER', 'TOUGHNESS', 'LOYALTY'):
                        operator = match.group(1)
                        value = match.group(2)
                        # Keep * as string, convert numbers to int
                        if value != '*':
                            value = int(value)
                        tokens.append((token_type, (operator, value)))
                    elif token_type == 'COLLECTOR_NUMBER':
                        operator = match.group(1)
                        value = match.group(2)
                        tokens.append((token_type, (operator, value)))
                    elif token_type == 'PRICE':
                        # Extract currency from the full match
                        full_match = match.group(0).lower()
                        if full_match.startswith('usd'):
                            currency = 'usd'
                        elif full_match.startswith('eur'):
                            currency = 'eur'
                        else:
                            currency = 'tix'
                        operator = match.group(1)
                        value = float(match.group(2))
                        tokens.append((token_type, (currency, operator, value)))
                    elif token_type == 'YEAR':
                        operator = match.group(1)
                        value = int(match.group(2))
                        tokens.append((token_type, (operator, value)))
                    elif token_type == 'MANA':
                        operator = match.group(1)
                        mana_str = match.group(2)
                        tokens.append((token_type, (operator, mana_str)))
                    elif token_type in ('TYPE_QUOTED', 'ORACLE_QUOTED', 'KEYWORD_QUOTED', 'FLAVOR_QUOTED', 'ARTIST_QUOTED', 'FULL_ORACLE_QUOTED', 'PRODUCES_TOKEN_QUOTED'):
                        tokens.append((token_type.replace('_QUOTED', ''), match.group(1)))
                    elif token_type in ('TYPE', 'ORACLE', 'SET', 'RARITY', 'FORMAT', 'KEYWORD', 'FLAVOR', 'ARTIST',
                                       'FULL_ORACLE', 'BANNED', 'BLOCK', 'PRODUCES', 'WATERMARK', 'LAYOUT', 'PRODUCES_TOKEN'):
                        tokens.append((token_type, match.group(1)))
                    elif token_type in ('EXACT_NAME', 'STRICT_NAME'):
                        tokens.append((token_type, match.group(1)))
                    elif token_type == 'PARTIAL_NAME':
                        tokens.append((token_type, match.group(1)))
                    else:
                        tokens.append((token_type, match.group(0)))

                    pos = match.end()
                    matched = True
                    break

            if not matched:
                raise QueryError(
                    f"Unexpected character at position {pos}: '{query[pos]}'",
                    hint="Check for unsupported characters or syntax",
                )

        return tokens

    def _parse_tokens(self, tokens: list[tuple[str, Any]], raw_query: str) -> ParsedQuery:
        """Parse tokens into ParsedQuery."""
        filters: dict[str, Any] = {}
        or_groups: list[list[dict[str, Any]]] = []
        has_or = False
        negated = False
        or_from_parens = False  # Track if OR groups came from parentheses

        # Simple state machine for parsing
        current_group: list[dict[str, Any]] = []
        i = 0

        while i < len(tokens):
            token_type, value = tokens[i]

            if token_type == 'NEGATION':
                negated = True
                i += 1
                continue

            if token_type == 'OR':
                has_or = True
                if current_group:
                    or_groups.append(current_group)
                    current_group = []
                i += 1
                continue

            if token_type == 'LPAREN':
                # Find matching RPAREN and parse recursively
                depth = 1
                j = i + 1
                while j < len(tokens) and depth > 0:
                    if tokens[j][0] == 'LPAREN':
                        depth += 1
                    elif tokens[j][0] == 'RPAREN':
                        depth -= 1
                    j += 1

                # Check for unbalanced parentheses
                if depth > 0:
                    raise QueryError(
                        "Unbalanced parentheses: missing closing ')'",
                        hint="Check that all opening parentheses have matching closing parentheses",
                        supported_syntax=SYNTAX_SUMMARY,
                    )

                # Parse inner tokens
                inner_tokens = tokens[i+1:j-1]
                inner_result = self._parse_tokens(inner_tokens, raw_query)

                # Merge inner filters
                if inner_result.has_or_clause:
                    has_or = True
                    or_from_parens = True
                    # Add any filters collected before parentheses to each inner OR group
                    if current_group:
                        for group in inner_result.or_groups:
                            group.extend(current_group)
                        current_group = []
                    or_groups.extend(inner_result.or_groups)
                else:
                    current_group.append(inner_result.filters)

                i = j
                negated = False
                continue

            if token_type == 'RPAREN':
                # Unmatched closing parenthesis at top level
                raise QueryError(
                    "Unbalanced parentheses: extra closing ')'",
                    hint="Check that all closing parentheses have matching opening parentheses",
                    supported_syntax=SYNTAX_SUMMARY,
                )

            # Process filter tokens
            filter_key = self._get_filter_key(token_type, negated)
            filter_value = self._get_filter_value(token_type, value)

            if filter_key and filter_value is not None:
                # Handle multiple values for same filter type (e.g., keyword:flying keyword:trample)
                # These filter types can have multiple values that should be ANDed together
                multi_value_filters = {'keyword', 'keyword_not', 'type', 'type_not', 'oracle_text', 'oracle_text_not', 'flavor_text', 'flavor_text_not', 'produces_token', 'produces_token_not', 'name_partial', 'name_partial_not'}

                if filter_key in multi_value_filters:
                    if filter_key not in filters:
                        filters[filter_key] = [filter_value]
                    else:
                        filters[filter_key].append(filter_value)
                else:
                    filters[filter_key] = filter_value
                current_group.append({filter_key: filter_value})

            negated = False
            i += 1

        # Handle remaining group for OR
        if has_or:
            if or_from_parens and current_group and or_groups:
                # Distribute outer filters (after parentheses) to each OR group
                # e.g., (t:elf OR t:goblin) c:green -> (elf AND green) OR (goblin AND green)
                for group in or_groups:
                    group.extend(current_group)
            elif current_group:
                or_groups.append(current_group)

        return ParsedQuery(
            filters=filters,
            or_groups=or_groups,
            has_or_clause=has_or,
            raw_query=raw_query,
        )

    def _get_filter_key(self, token_type: str, negated: bool) -> str | None:
        """Get filter key for token type."""
        key_map = {
            'COLOR': 'colors',
            'COLOR_IDENTITY': 'color_identity',
            'CMC': 'cmc',
            'TYPE': 'type',
            'ORACLE': 'oracle_text',
            'FULL_ORACLE': 'oracle_text',  # fo: is alias for o: (oracle_text includes reminder text)
            'FLAVOR': 'flavor_text',
            'SET': 'set',
            'RARITY': 'rarity',
            'FORMAT': 'format',
            'BANNED': 'banned',
            'BLOCK': 'block',
            'PRODUCES': 'produces',
            'WATERMARK': 'watermark',
            'LAYOUT': 'layout',
            'PRODUCES_TOKEN': 'produces_token',
            'KEYWORD': 'keyword',
            'POWER': 'power',
            'TOUGHNESS': 'toughness',
            'LOYALTY': 'loyalty',
            'COLLECTOR_NUMBER': 'collector_number',
            'PRICE': 'price',
            'ARTIST': 'artist',
            'YEAR': 'year',
            'MANA': 'mana',
            'EXACT_NAME': 'name_exact',
            'STRICT_NAME': 'name_strict',
            'PARTIAL_NAME': 'name_partial',
        }
        key = key_map.get(token_type)
        if key and negated:
            return f"{key}_not"
        return key

    def _get_filter_value(self, token_type: str, value: Any) -> Any:
        """Get filter value for token type."""
        if token_type == 'COLOR':
            operator, color_str = value
            colors = _parse_color_value(color_str)
            return {"operator": operator, "value": colors}

        if token_type == 'COLOR_IDENTITY':
            operator, identity_str = value
            colors = _parse_identity_value(identity_str)
            return {"operator": operator, "value": colors}

        if token_type == 'CMC':
            operator, num = value
            # Normalize : to =
            if operator == ':':
                operator = '='
            return {"operator": operator, "value": num}

        if token_type in ('POWER', 'TOUGHNESS', 'LOYALTY'):
            operator, val = value
            # Normalize : to =
            if operator == ':':
                operator = '='
            return {"operator": operator, "value": val}

        if token_type == 'COLLECTOR_NUMBER':
            operator, val = value
            # Normalize : to =
            if operator == ':':
                operator = '='
            return {"operator": operator, "value": val}

        if token_type == 'PRICE':
            currency, operator, val = value
            # Normalize : to =
            if operator == ':':
                operator = '='
            return {"currency": currency, "operator": operator, "value": val}

        if token_type == 'FORMAT':
            return value.lower()

        if token_type == 'RARITY':
            return RARITY_MAP.get(value.lower(), value.lower())

        if token_type == 'SET':
            return value.lower()

        if token_type == 'KEYWORD':
            # Normalize to title case to match Scryfall format ("Flying", "Deathtouch")
            return value.title()

        if token_type == 'ARTIST':
            return value

        if token_type == 'YEAR':
            operator, val = value
            # Normalize : to =
            if operator == ':':
                operator = '='
            return {"operator": operator, "value": val}

        if token_type == 'MANA':
            operator, mana_str = value
            # Normalize : to = for exact match, keep as : for contains
            # m:{R} means contains {R}, m={R} means exactly {R}
            return {"operator": operator, "value": mana_str}

        if token_type in ('TYPE', 'ORACLE', 'FULL_ORACLE', 'FLAVOR', 'EXACT_NAME', 'STRICT_NAME', 'PARTIAL_NAME'):
            return value

        if token_type == 'BANNED':
            # Format name where the card is banned
            return value.lower()

        if token_type == 'BLOCK':
            # Block name (e.g., innistrad, zendikar)
            return value.lower()

        if token_type == 'PRODUCES':
            # Parse color values for mana production (e.g., "g", "wubrg")
            return _parse_color_value(value)

        if token_type == 'WATERMARK':
            # Watermark name (e.g., phyrexian, selesnya)
            return value.lower()

        if token_type == 'LAYOUT':
            # Layout type (e.g., transform, modal_dfc, adventure)
            return value.lower()

        if token_type == 'PRODUCES_TOKEN':
            # Token name (e.g., zombie, "Goblin Token")
            return value

        return None

