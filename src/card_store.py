"""Card store using SQLite with FTS5 for text search.

Provides efficient storage and querying of Scryfall card data.
All queries use parameterized statements for SQL injection prevention.
"""

import json
import logging
import random
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# Allowlists for SQL-interpolated values (security: prevents SQL injection)
VALID_FORMATS = frozenset({
    "standard", "future", "historic", "timeless", "gladiator",
    "pioneer", "modern", "legacy", "pauper", "vintage",
    "penny", "commander", "oathbreaker", "standardbrawl", "brawl",
    "alchemy", "paupercommander", "duel", "oldschool", "premodern", "predh"
})

VALID_CURRENCIES = frozenset({
    "usd", "usd_foil", "usd_etched", "eur", "eur_foil", "tix"
})

# Operator mapping for SQL comparisons (: is treated as = for Scryfall compatibility)
OPERATOR_MAP = {
    "=": "=",
    ":": "=",
    ">=": ">=",
    "<=": "<=",
    ">": ">",
    "<": "<",
    "!=": "!=",
}

# Inverted operators for NOT filters (e.g., -cmc>=5 means cmc<5)
INVERTED_OPERATOR_MAP = {
    "=": "!=",
    ":": "!=",
    "!=": "=",
    ">=": "<",
    "<=": ">",
    ">": "<=",
    "<": ">=",
}


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects from ijson streaming parser."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class CardStore:
    """SQLite-based card storage with FTS5 text search."""

    def __init__(self, db_path: Path):
        """Initialize card store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database tables and indexes."""
        cursor = self._conn.cursor()

        # Migration: Add columns if table exists but columns don't
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='cards'
        """)
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(cards)")
            columns = [row[1] for row in cursor.fetchall()]

            # Define migrations: (column_name, json_path, optional_transform)
            migrations = [
                ("keywords", "$.keywords", None),
                ("artist", "$.artist", None),
                ("released_at", "$.released_at", None),
                ("loyalty", "$.loyalty", None),
                ("flavor_text", "$.flavor_text", None),
                ("collector_number", "$.collector_number", None),
            ]

            for col_name, json_path, _ in migrations:
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE cards ADD COLUMN {col_name} TEXT")
                    cursor.execute(f"""
                        UPDATE cards
                        SET {col_name} = json_extract(raw_data, '{json_path}')
                        WHERE {col_name} IS NULL
                    """)
            self._conn.commit()

        # Main cards table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                oracle_id TEXT,
                name TEXT NOT NULL,
                mana_cost TEXT,
                cmc REAL,
                type_line TEXT,
                oracle_text TEXT,
                power TEXT,
                toughness TEXT,
                colors TEXT,  -- JSON array
                color_identity TEXT,  -- JSON array
                keywords TEXT,  -- JSON array of keyword abilities
                set_code TEXT,
                set_name TEXT,
                rarity TEXT,
                artist TEXT,
                released_at TEXT,  -- Date string like "2024-08-02"
                loyalty TEXT,  -- Planeswalker loyalty (can be "X" or number)
                flavor_text TEXT,
                collector_number TEXT,
                image_uris TEXT,  -- JSON object
                legalities TEXT,  -- JSON object
                prices TEXT,  -- JSON object
                raw_data TEXT  -- Full JSON for any other fields
            )
        """)

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_name ON cards(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_name_lower ON cards(LOWER(name))")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmc ON cards(cmc)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_set ON cards(set_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rarity ON cards(rarity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist ON cards(artist)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_released_at ON cards(released_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_oracle_id ON cards(oracle_id)")
        # Color indexes help with exact matches (e.g., colorless = '[]')
        # Note: LIKE '%"U"%' queries can't use B-tree indexes efficiently
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colors ON cards(colors)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_color_identity ON cards(color_identity)")

        # FTS5 virtual table for oracle text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
                id,
                name,
                oracle_text,
                type_line,
                content='cards',
                content_rowid='rowid'
            )
        """)

        # Triggers to keep FTS in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS cards_ai AFTER INSERT ON cards BEGIN
                INSERT INTO cards_fts(rowid, id, name, oracle_text, type_line)
                VALUES (NEW.rowid, NEW.id, NEW.name, NEW.oracle_text, NEW.type_line);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS cards_ad AFTER DELETE ON cards BEGIN
                INSERT INTO cards_fts(cards_fts, rowid, id, name, oracle_text, type_line)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.name, OLD.oracle_text, OLD.type_line);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS cards_au AFTER UPDATE ON cards BEGIN
                INSERT INTO cards_fts(cards_fts, rowid, id, name, oracle_text, type_line)
                VALUES ('delete', OLD.rowid, OLD.id, OLD.name, OLD.oracle_text, OLD.type_line);
                INSERT INTO cards_fts(rowid, id, name, oracle_text, type_line)
                VALUES (NEW.rowid, NEW.id, NEW.name, NEW.oracle_text, NEW.type_line);
            END
        """)

        self._conn.commit()

    def close(self) -> None:
        """Close database connection."""
        self._conn.close()

    def __enter__(self) -> "CardStore":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close connection."""
        self.close()

    def get_table_names(self) -> list[str]:
        """Get list of table names in database."""
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' OR type='virtual table'
        """)
        return [row[0] for row in cursor.fetchall()]

    def get_card_count(self) -> int:
        """Get total number of cards in database."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cards")
        return cursor.fetchone()[0]

    # SQL for inserting cards
    _INSERT_SQL = """
        INSERT OR REPLACE INTO cards (
            id, oracle_id, name, mana_cost, cmc, type_line, oracle_text,
            power, toughness, colors, color_identity, keywords, set_code, set_name,
            rarity, artist, released_at, loyalty, flavor_text, collector_number,
            image_uris, legalities, prices, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def _card_to_params(self, card: dict[str, Any]) -> tuple:
        """Extract card data as SQL parameters.

        Args:
            card: Card data dictionary

        Returns:
            Tuple of parameters for SQL insert
        """
        # Convert cmc from Decimal to float if needed (ijson returns Decimal)
        cmc = card.get("cmc")
        if isinstance(cmc, Decimal):
            cmc = float(cmc)

        return (
            card.get("id"),
            card.get("oracle_id"),
            card.get("name"),
            card.get("mana_cost"),
            cmc,
            card.get("type_line"),
            card.get("oracle_text"),
            card.get("power"),
            card.get("toughness"),
            json.dumps(card.get("colors", []), cls=DecimalEncoder),
            json.dumps(card.get("color_identity", []), cls=DecimalEncoder),
            json.dumps(card.get("keywords", []), cls=DecimalEncoder),
            card.get("set"),
            card.get("set_name"),
            card.get("rarity"),
            card.get("artist"),
            card.get("released_at"),
            card.get("loyalty"),
            card.get("flavor_text"),
            card.get("collector_number"),
            json.dumps(card.get("image_uris", {}), cls=DecimalEncoder),
            json.dumps(card.get("legalities", {}), cls=DecimalEncoder),
            json.dumps(card.get("prices", {}), cls=DecimalEncoder),
            json.dumps(card, cls=DecimalEncoder),
        )

    def insert_card(self, card: dict[str, Any]) -> None:
        """Insert a single card into the database.

        Args:
            card: Card data dictionary
        """
        cursor = self._conn.cursor()
        cursor.execute(self._INSERT_SQL, self._card_to_params(card))
        self._conn.commit()

    def insert_cards(self, cards: list[dict[str, Any]]) -> None:
        """Insert multiple cards into the database.

        Args:
            cards: List of card data dictionaries
        """
        cursor = self._conn.cursor()
        for card in cards:
            cursor.execute(self._INSERT_SQL, self._card_to_params(card))
        self._conn.commit()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert database row to card dictionary."""
        card = dict(row)
        # Parse JSON fields
        for field in ["colors", "color_identity", "keywords", "image_uris", "legalities", "prices"]:
            if card.get(field):
                try:
                    card[field] = json.loads(card[field])
                except json.JSONDecodeError:
                    pass
        # Rename set_code to set for API compatibility
        if "set_code" in card:
            card["set"] = card.pop("set_code")
        # Remove raw_data from output (too verbose)
        card.pop("raw_data", None)
        return card

    def get_card_by_id(self, card_id: str) -> dict[str, Any] | None:
        """Get card by Scryfall ID.

        Args:
            card_id: Scryfall card ID

        Returns:
            Card dictionary or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def get_card_by_name(self, name: str) -> dict[str, Any] | None:
        """Get card by exact name.

        Args:
            name: Exact card name

        Returns:
            Card dictionary or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM cards WHERE name = ?", (name,))
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def search_by_partial_name(self, partial: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search cards by partial name match.

        Args:
            partial: Partial name to search for
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()
        # Note: % and _ in user input act as LIKE wildcards, but no MTG cards
        # contain these characters in their names, so this is safe in practice
        cursor.execute(
            "SELECT * FROM cards WHERE LOWER(name) LIKE ? LIMIT ?",
            (f"%{partial.lower()}%", limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_color(
        self,
        colors: list[str],
        operator: str = ":",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query cards by color.

        Args:
            colors: List of color symbols (W, U, B, R, G)
            operator: Comparison operator (:, >=, <=, etc.)
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()

        if not colors:
            # Colorless cards
            cursor.execute(
                "SELECT * FROM cards WHERE colors = '[]' LIMIT ?",
                (limit,),
            )
        elif operator in (":", "=", ">="):
            # Exact color match or "at least these colors"
            # Check that card has all specified colors
            # Note: colors are validated by query_parser._parse_color_value() to only
            # contain W, U, B, R, G - no SQL injection risk from f-string formatting
            conditions = " AND ".join(
                f"colors LIKE '%\"{c}\"%'" for c in colors
            )
            cursor.execute(
                f"SELECT * FROM cards WHERE {conditions} LIMIT ?",
                (limit,),
            )
        elif operator == "<=":
            # Card has at most these colors (subset)
            # Exclude cards containing colors not in the allowed set
            all_colors = {"W", "U", "B", "R", "G"}
            allowed_colors = set(colors)
            disallowed_colors = all_colors - allowed_colors

            if disallowed_colors:
                # Build NOT LIKE conditions for disallowed colors
                conditions = " AND ".join(
                    f"colors NOT LIKE '%\"{c}\"%'" for c in disallowed_colors
                )
                cursor.execute(
                    f"SELECT * FROM cards WHERE {conditions} LIMIT ?",
                    (limit,),
                )
            else:
                # All colors allowed, return any cards
                cursor.execute("SELECT * FROM cards LIMIT ?", (limit,))
        else:
            cursor.execute("SELECT * FROM cards LIMIT ?", (limit,))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_cmc(
        self,
        value: int,
        operator: str = "=",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query cards by converted mana cost.

        Args:
            value: CMC value to compare
            operator: Comparison operator (=, >=, <=, >, <)
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()
        sql_op = OPERATOR_MAP.get(operator, "=")

        cursor.execute(
            f"SELECT * FROM cards WHERE cmc {sql_op} ? LIMIT ?",
            (value, limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_type(self, type_str: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query cards by type.

        Args:
            type_str: Type to search for (e.g., "creature", "instant")
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE LOWER(type_line) LIKE ? LIMIT ?",
            (f"%{type_str.lower()}%", limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_oracle_text(self, text: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query cards by oracle text using FTS5.

        Args:
            text: Text to search for
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()

        # Escape special FTS characters
        safe_text = text.replace('"', '""')

        try:
            # Try FTS5 search first for better performance on exact phrase matches
            cursor.execute("""
                SELECT cards.* FROM cards
                JOIN cards_fts ON cards.id = cards_fts.id
                WHERE cards_fts MATCH ?
                LIMIT ?
            """, (f'"{safe_text}"', limit))
            results = [self._row_to_dict(row) for row in cursor.fetchall()]
            if results:
                return results
        except sqlite3.OperationalError as e:
            logger.debug("FTS5 search failed, falling back to LIKE: %s", e)

        # Intentional fallback: when FTS5 returns no results or fails, use LIKE
        # for partial/substring matching. This provides better UX for searches
        # that don't match FTS5's exact phrase semantics.
        cursor.execute(
            "SELECT * FROM cards WHERE LOWER(oracle_text) LIKE ? LIMIT ?",
            (f"%{text.lower()}%", limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_set(self, set_code: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query cards by set code.

        Args:
            set_code: Set code (e.g., "neo", "m19")
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE LOWER(set_code) = ? LIMIT ?",
            (set_code.lower(), limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def query_by_rarity(self, rarity: str, limit: int = 100) -> list[dict[str, Any]]:
        """Query cards by rarity.

        Args:
            rarity: Rarity (common, uncommon, rare, mythic)
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM cards WHERE LOWER(rarity) = ? LIMIT ?",
            (rarity.lower(), limit),
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _build_conditions_for_filters(
        self, filters: dict[str, Any]
    ) -> tuple[list[str], list[Any]]:
        """Convert a filters dict to SQL conditions and params.

        Args:
            filters: Dictionary of filter key-value pairs

        Returns:
            Tuple of (conditions list, params list)
        """
        conditions: list[str] = []
        params: list[Any] = []

        # Name filters
        if "name_exact" in filters:
            conditions.append("name = ?")
            params.append(filters["name_exact"])
        if "name_strict" in filters:
            conditions.append("name = ? COLLATE BINARY")
            params.append(filters["name_strict"])
        if "name_partial" in filters:
            conditions.append("LOWER(name) LIKE ?")
            params.append(f"%{filters['name_partial'].lower()}%")
        if "name_contains" in filters:
            # Support list of partial name matches (for backward compatibility)
            name_values = filters["name_contains"]
            if isinstance(name_values, list):
                for name_val in name_values:
                    conditions.append("LOWER(name) LIKE ?")
                    params.append(f"%{name_val.lower()}%")
            else:
                conditions.append("LOWER(name) LIKE ?")
                params.append(f"%{name_values.lower()}%")

        # Color filter
        if "colors" in filters:
            color_filter = filters["colors"]
            colors = color_filter.get("value", [])
            operator = color_filter.get("operator", ":")
            if not colors:
                conditions.append("colors = '[]'")
            elif operator in (":", "=", ">="):
                # Has at least these colors
                for c in colors:
                    conditions.append("colors LIKE ?")
                    params.append(f'%"{c}"%')
            elif operator == "<=":
                # Has at most these colors (subset)
                all_colors = {"W", "U", "B", "R", "G"}
                allowed_colors = set(colors)
                disallowed_colors = all_colors - allowed_colors
                if disallowed_colors:
                    for c in disallowed_colors:
                        conditions.append("colors NOT LIKE ?")
                        params.append(f'%"{c}"%')
            elif operator == ">":
                # Has more colors than specified (superset, not equal)
                # Must have all specified colors plus at least one more
                for c in colors:
                    conditions.append("colors LIKE ?")
                    params.append(f'%"{c}"%')
                all_colors = {"W", "U", "B", "R", "G"}
                other_colors = all_colors - set(colors)
                if other_colors:
                    # Must have at least one color not in the specified set
                    or_conditions = " OR ".join(f"colors LIKE '%\"{c}\"%'" for c in other_colors)
                    conditions.append(f"({or_conditions})")
            elif operator == "<":
                # Has fewer colors than specified (strict subset)
                # Must not have all the specified colors, and must not have any outside
                all_colors = {"W", "U", "B", "R", "G"}
                disallowed_colors = all_colors - set(colors)
                # Can't have colors outside the specified set
                for c in disallowed_colors:
                    conditions.append("colors NOT LIKE ?")
                    params.append(f'%"{c}"%')
                # Must not have ALL of the specified colors (strict subset)
                if len(colors) > 1:
                    # At least one of the specified colors must be missing
                    not_all = " OR ".join(f"colors NOT LIKE '%\"{c}\"%'" for c in colors)
                    conditions.append(f"({not_all})")

        # Color NOT filter
        if "colors_not" in filters:
            color_not_filter = filters["colors_not"]
            colors = color_not_filter.get("value", [])
            if not colors:
                # -c:colorless means NOT colorless, i.e., has at least one color
                conditions.append("colors != '[]'")
            else:
                for c in colors:
                    conditions.append("colors NOT LIKE ?")
                    params.append(f'%"{c}"%')

        # Color identity filter
        if "color_identity" in filters:
            identity_filter = filters["color_identity"]
            colors = identity_filter.get("value", [])
            operator = identity_filter.get("operator", ":")
            if not colors:
                conditions.append("color_identity = '[]'")
            elif operator in (":", "=", ">="):
                # Has at least these colors in identity
                for c in colors:
                    conditions.append("color_identity LIKE ?")
                    params.append(f'%"{c}"%')
            elif operator == "<=":
                # Identity is subset of specified colors
                all_colors = {"W", "U", "B", "R", "G"}
                allowed_colors = set(colors)
                disallowed_colors = all_colors - allowed_colors
                if disallowed_colors:
                    for c in disallowed_colors:
                        conditions.append("color_identity NOT LIKE ?")
                        params.append(f'%"{c}"%')
            elif operator == ">":
                # Identity is strict superset (has all specified plus more)
                for c in colors:
                    conditions.append("color_identity LIKE ?")
                    params.append(f'%"{c}"%')
                all_colors = {"W", "U", "B", "R", "G"}
                other_colors = all_colors - set(colors)
                if other_colors:
                    or_conditions = " OR ".join(f"color_identity LIKE '%\"{c}\"%'" for c in other_colors)
                    conditions.append(f"({or_conditions})")
            elif operator == "<":
                # Identity is strict subset (fewer colors than specified)
                all_colors = {"W", "U", "B", "R", "G"}
                disallowed_colors = all_colors - set(colors)
                for c in disallowed_colors:
                    conditions.append("color_identity NOT LIKE ?")
                    params.append(f'%"{c}"%')
                if len(colors) > 1:
                    not_all = " OR ".join(f"color_identity NOT LIKE '%\"{c}\"%'" for c in colors)
                    conditions.append(f"({not_all})")

        # Color identity NOT filter
        if "color_identity_not" in filters:
            identity_not_filter = filters["color_identity_not"]
            colors = identity_not_filter.get("value", [])
            if not colors:
                # -id:colorless means NOT colorless, i.e., has at least one color
                conditions.append("color_identity != '[]'")
            else:
                for c in colors:
                    conditions.append("color_identity NOT LIKE ?")
                    params.append(f'%"{c}"%')

        # CMC filter
        if "cmc" in filters:
            cmc_filter = filters["cmc"]
            value = cmc_filter.get("value", 0)
            operator = cmc_filter.get("operator", "=")
            sql_op = OPERATOR_MAP.get(operator, "=")
            conditions.append(f"cmc {sql_op} ?")
            params.append(value)

        # CMC NOT filter (inverts the operator: -cmc>=5 means cmc<5)
        if "cmc_not" in filters:
            cmc_not_filter = filters["cmc_not"]
            value = cmc_not_filter.get("value", 0)
            operator = cmc_not_filter.get("operator", "=")
            sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
            conditions.append(f"cmc {sql_op} ?")
            params.append(value)

        # Mana cost filter (e.g., m:{R}{R}, mana:{2}{U}{U})
        if "mana" in filters:
            mana_filter = filters["mana"]
            mana_value = mana_filter.get("value", "")
            operator = mana_filter.get("operator", ":")
            if operator == "=":
                # Exact match
                conditions.append("mana_cost = ?")
                params.append(mana_value)
            else:
                # Contains match (default for :)
                conditions.append("mana_cost LIKE ?")
                params.append(f"%{mana_value}%")

        # Mana cost NOT filter
        if "mana_not" in filters:
            mana_not_filter = filters["mana_not"]
            mana_value = mana_not_filter.get("value", "")
            operator = mana_not_filter.get("operator", ":")
            if operator == "=":
                conditions.append("(mana_cost IS NULL OR mana_cost != ?)")
                params.append(mana_value)
            else:
                conditions.append("(mana_cost IS NULL OR mana_cost NOT LIKE ?)")
                params.append(f"%{mana_value}%")

        # Type filter
        if "type" in filters:
            type_values = filters["type"]
            if isinstance(type_values, list):
                for type_val in type_values:
                    conditions.append("LOWER(type_line) LIKE ?")
                    params.append(f"%{type_val.lower()}%")
            else:
                conditions.append("LOWER(type_line) LIKE ?")
                params.append(f"%{type_values.lower()}%")

        # Type NOT filter
        if "type_not" in filters:
            type_not_values = filters["type_not"]
            if isinstance(type_not_values, list):
                for type_val in type_not_values:
                    conditions.append("(type_line IS NULL OR LOWER(type_line) NOT LIKE ?)")
                    params.append(f"%{type_val.lower()}%")
            else:
                conditions.append("(type_line IS NULL OR LOWER(type_line) NOT LIKE ?)")
                params.append(f"%{type_not_values.lower()}%")

        # Oracle text filter
        if "oracle_text" in filters:
            oracle_values = filters["oracle_text"]
            if isinstance(oracle_values, list):
                for oracle_val in oracle_values:
                    conditions.append("LOWER(oracle_text) LIKE ?")
                    params.append(f"%{oracle_val.lower()}%")
            else:
                conditions.append("LOWER(oracle_text) LIKE ?")
                params.append(f"%{oracle_values.lower()}%")

        # Oracle text NOT filter
        if "oracle_text_not" in filters:
            oracle_not_values = filters["oracle_text_not"]
            if isinstance(oracle_not_values, list):
                for oracle_val in oracle_not_values:
                    conditions.append("(oracle_text IS NULL OR LOWER(oracle_text) NOT LIKE ?)")
                    params.append(f"%{oracle_val.lower()}%")
            else:
                conditions.append("(oracle_text IS NULL OR LOWER(oracle_text) NOT LIKE ?)")
                params.append(f"%{oracle_not_values.lower()}%")

        # Flavor text filter
        if "flavor_text" in filters:
            flavor_values = filters["flavor_text"]
            if isinstance(flavor_values, list):
                for flavor_val in flavor_values:
                    conditions.append("LOWER(flavor_text) LIKE ?")
                    params.append(f"%{flavor_val.lower()}%")
            else:
                conditions.append("LOWER(flavor_text) LIKE ?")
                params.append(f"%{flavor_values.lower()}%")

        # Flavor text NOT filter
        if "flavor_text_not" in filters:
            flavor_not_values = filters["flavor_text_not"]
            if isinstance(flavor_not_values, list):
                for flavor_val in flavor_not_values:
                    conditions.append("(flavor_text IS NULL OR LOWER(flavor_text) NOT LIKE ?)")
                    params.append(f"%{flavor_val.lower()}%")
            else:
                conditions.append("(flavor_text IS NULL OR LOWER(flavor_text) NOT LIKE ?)")
                params.append(f"%{flavor_not_values.lower()}%")

        # Set filter
        if "set" in filters:
            conditions.append("LOWER(set_code) = ?")
            params.append(filters["set"].lower())

        # Set NOT filter
        if "set_not" in filters:
            conditions.append("LOWER(set_code) != ?")
            params.append(filters["set_not"].lower())

        # Rarity filter
        if "rarity" in filters:
            conditions.append("LOWER(rarity) = ?")
            params.append(filters["rarity"].lower())

        # Rarity NOT filter
        if "rarity_not" in filters:
            conditions.append("LOWER(rarity) != ?")
            params.append(filters["rarity_not"].lower())

        # Format legality filter
        if "format" in filters:
            format_name = filters["format"].lower()
            if format_name in VALID_FORMATS:
                conditions.append(
                    f"(json_extract(legalities, '$.{format_name}') = 'legal' "
                    f"OR json_extract(legalities, '$.{format_name}') = 'restricted')"
                )
            else:
                # Invalid format returns empty results
                conditions.append("1=0")

        # Format NOT filter (cards NOT legal in format)
        if "format_not" in filters:
            format_name = filters["format_not"].lower()
            if format_name in VALID_FORMATS:
                conditions.append(
                    f"(json_extract(legalities, '$.{format_name}') IS NULL "
                    f"OR (json_extract(legalities, '$.{format_name}') != 'legal' "
                    f"AND json_extract(legalities, '$.{format_name}') != 'restricted'))"
                )
            else:
                # Invalid format_not matches all cards (no cards are legal in invalid format)
                pass

        # Power filter
        if "power" in filters:
            power_filter = filters["power"]
            value = power_filter.get("value")
            operator = power_filter.get("operator", "=")
            sql_op = OPERATOR_MAP.get(operator, "=")
            if value == "*":
                conditions.append("power = '*'")
            else:
                conditions.append(f"CAST(power AS INTEGER) {sql_op} ?")
                params.append(value)

        # Power NOT filter
        if "power_not" in filters:
            power_not_filter = filters["power_not"]
            value = power_not_filter.get("value")
            operator = power_not_filter.get("operator", "=")
            sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
            if value == "*":
                conditions.append("power != '*'")
            else:
                conditions.append(f"CAST(power AS INTEGER) {sql_op} ?")
                params.append(value)

        # Toughness filter
        if "toughness" in filters:
            toughness_filter = filters["toughness"]
            value = toughness_filter.get("value")
            operator = toughness_filter.get("operator", "=")
            sql_op = OPERATOR_MAP.get(operator, "=")
            if value == "*":
                conditions.append("toughness = '*'")
            else:
                conditions.append(f"CAST(toughness AS INTEGER) {sql_op} ?")
                params.append(value)

        # Toughness NOT filter
        if "toughness_not" in filters:
            toughness_not_filter = filters["toughness_not"]
            value = toughness_not_filter.get("value")
            operator = toughness_not_filter.get("operator", "=")
            sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
            if value == "*":
                conditions.append("toughness != '*'")
            else:
                conditions.append(f"CAST(toughness AS INTEGER) {sql_op} ?")
                params.append(value)

        # Loyalty filter
        if "loyalty" in filters:
            loyalty_filter = filters["loyalty"]
            value = loyalty_filter.get("value")
            operator = loyalty_filter.get("operator", "=")
            sql_op = OPERATOR_MAP.get(operator, "=")
            conditions.append(f"CAST(loyalty AS INTEGER) {sql_op} ?")
            params.append(value)

        # Loyalty NOT filter
        if "loyalty_not" in filters:
            loyalty_not_filter = filters["loyalty_not"]
            value = loyalty_not_filter.get("value")
            operator = loyalty_not_filter.get("operator", "=")
            sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
            conditions.append(f"CAST(loyalty AS INTEGER) {sql_op} ?")
            params.append(value)

        # Collector number filter
        # Note: For numeric comparisons (>, <, >=, <=), CAST handles alphanumeric
        # collector numbers like "1a" or "★" by extracting the numeric prefix (or 0).
        # This is acceptable behavior since numeric comparisons on non-numeric
        # collector numbers are inherently ambiguous.
        if "collector_number" in filters:
            cn_filter = filters["collector_number"]
            value = cn_filter.get("value")
            operator = cn_filter.get("operator", "=")
            if operator == "=":
                conditions.append("collector_number = ?")
                params.append(str(value))
            else:
                sql_op = OPERATOR_MAP.get(operator, "=")
                conditions.append(f"CAST(collector_number AS INTEGER) {sql_op} ?")
                params.append(int(value) if str(value).isdigit() else value)

        # Collector number NOT filter
        if "collector_number_not" in filters:
            cn_not_filter = filters["collector_number_not"]
            value = cn_not_filter.get("value")
            operator = cn_not_filter.get("operator", "=")
            if operator == "=":
                conditions.append("collector_number != ?")
                params.append(str(value))
            else:
                sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
                conditions.append(f"CAST(collector_number AS INTEGER) {sql_op} ?")
                params.append(int(value) if str(value).isdigit() else value)

        # Price filter
        if "price" in filters:
            price_filter = filters["price"]
            currency = price_filter.get("currency", "usd").lower()
            value = price_filter.get("value")
            operator = price_filter.get("operator", "=")
            if currency in VALID_CURRENCIES:
                sql_op = OPERATOR_MAP.get(operator, "=")
                conditions.append(
                    f"CAST(json_extract(prices, '$.{currency}') AS REAL) {sql_op} ?"
                )
                params.append(value)

        # Price NOT filter
        if "price_not" in filters:
            price_not_filter = filters["price_not"]
            currency = price_not_filter.get("currency", "usd").lower()
            value = price_not_filter.get("value")
            operator = price_not_filter.get("operator", "=")
            if currency in VALID_CURRENCIES:
                sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
                conditions.append(
                    f"CAST(json_extract(prices, '$.{currency}') AS REAL) {sql_op} ?"
                )
                params.append(value)

        # Keyword filter
        if "keyword" in filters:
            keyword_values = filters["keyword"]
            if isinstance(keyword_values, list):
                for keyword in keyword_values:
                    conditions.append("LOWER(keywords) LIKE ?")
                    params.append(f'%"{keyword.lower()}"%')
            else:
                conditions.append("LOWER(keywords) LIKE ?")
                params.append(f'%"{keyword_values.lower()}"%')

        # Keyword NOT filter
        if "keyword_not" in filters:
            keyword_not_values = filters["keyword_not"]
            if isinstance(keyword_not_values, list):
                for keyword in keyword_not_values:
                    conditions.append("(keywords IS NULL OR LOWER(keywords) NOT LIKE ?)")
                    params.append(f'%"{keyword.lower()}"%')
            else:
                conditions.append("(keywords IS NULL OR LOWER(keywords) NOT LIKE ?)")
                params.append(f'%"{keyword_not_values.lower()}"%')

        # Artist filter
        if "artist" in filters:
            artist_value = filters["artist"]
            conditions.append("LOWER(artist) LIKE ?")
            params.append(f"%{artist_value.lower()}%")

        # Artist NOT filter
        if "artist_not" in filters:
            artist_not_value = filters["artist_not"]
            conditions.append("(artist IS NULL OR LOWER(artist) NOT LIKE ?)")
            params.append(f"%{artist_not_value.lower()}%")

        # Year filter
        if "year" in filters:
            year_filter = filters["year"]
            value = year_filter.get("value")
            operator = year_filter.get("operator", "=")
            sql_op = OPERATOR_MAP.get(operator, "=")
            conditions.append(f"CAST(substr(released_at, 1, 4) AS INTEGER) {sql_op} ?")
            params.append(value)

        # Year NOT filter
        if "year_not" in filters:
            year_not_filter = filters["year_not"]
            value = year_not_filter.get("value")
            operator = year_not_filter.get("operator", "=")
            sql_op = INVERTED_OPERATOR_MAP.get(operator, "!=")
            conditions.append(f"CAST(substr(released_at, 1, 4) AS INTEGER) {sql_op} ?")
            params.append(value)

        return conditions, params

    def execute_query(
        self,
        parsed: ParsedQuery,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Execute a parsed query.

        Args:
            parsed: ParsedQuery object with filters
            limit: Maximum results to return
            offset: Number of results to skip (for pagination)

        Returns:
            List of matching card dictionaries
        """
        # Start with all cards if no filters
        if parsed.is_empty and not parsed.has_or_clause:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM cards LIMIT ? OFFSET ?", (limit, offset))
            return [self._row_to_dict(row) for row in cursor.fetchall()]

        # Handle OR queries
        if parsed.has_or_clause and parsed.or_groups:
            group_clauses = []
            all_params: list[Any] = []

            for group_filters in parsed.or_groups:
                # Merge list of filter dicts into one
                merged: dict[str, Any] = {}
                for f in group_filters:
                    merged.update(f)

                conditions, params = self._build_conditions_for_filters(merged)
                if conditions:
                    group_clauses.append(f"({' AND '.join(conditions)})")
                    all_params.extend(params)

            if group_clauses:
                where_clause = " OR ".join(group_clauses)
                query = f"SELECT * FROM cards WHERE {where_clause} LIMIT ? OFFSET ?"
                all_params.extend([limit, offset])
                cursor = self._conn.cursor()
                cursor.execute(query, all_params)
                return [self._row_to_dict(row) for row in cursor.fetchall()]
            else:
                # No valid conditions, return empty
                return []

        # Standard AND query (no OR)
        conditions, params = self._build_conditions_for_filters(parsed.filters)

        # Build and execute query
        if conditions:
            where_clause = " AND ".join(conditions)
            query = f"SELECT * FROM cards WHERE {where_clause} LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        else:
            query = "SELECT * FROM cards LIMIT ? OFFSET ?"
            params = [limit, offset]

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def count_matches(self, parsed: ParsedQuery) -> int:
        """Count total matching cards for a query (without pagination).

        Args:
            parsed: ParsedQuery object with filters

        Returns:
            Total count of matching cards
        """
        cursor = self._conn.cursor()

        # No filters - count all cards
        if parsed.is_empty and not parsed.has_or_clause:
            cursor.execute("SELECT COUNT(*) FROM cards")
            return cursor.fetchone()[0]

        # Handle OR queries
        if parsed.has_or_clause and parsed.or_groups:
            group_clauses = []
            all_params: list[Any] = []

            for group_filters in parsed.or_groups:
                merged: dict[str, Any] = {}
                for f in group_filters:
                    merged.update(f)

                conditions, params = self._build_conditions_for_filters(merged)
                if conditions:
                    group_clauses.append(f"({' AND '.join(conditions)})")
                    all_params.extend(params)

            if group_clauses:
                where_clause = " OR ".join(group_clauses)
                query = f"SELECT COUNT(*) FROM cards WHERE {where_clause}"
                cursor.execute(query, all_params)
                return cursor.fetchone()[0]
            else:
                return 0

        # Standard AND query (no OR)
        conditions, params = self._build_conditions_for_filters(parsed.filters)

        if conditions:
            where_clause = " AND ".join(conditions)
            query = f"SELECT COUNT(*) FROM cards WHERE {where_clause}"
        else:
            query = "SELECT COUNT(*) FROM cards"
            params = []

        cursor.execute(query, params)
        return cursor.fetchone()[0]

    def get_random_card(self, parsed: ParsedQuery | None = None) -> dict[str, Any] | None:
        """Get a random card, optionally filtered.

        Args:
            parsed: Optional ParsedQuery for filtering

        Returns:
            Random card dictionary or None if no matches
        """
        cursor = self._conn.cursor()

        # No filter - random from all cards
        if not parsed or parsed.is_empty:
            cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

        # Handle OR queries
        if parsed.has_or_clause and parsed.or_groups:
            group_clauses = []
            all_params: list[Any] = []

            for group_filters in parsed.or_groups:
                merged: dict[str, Any] = {}
                for f in group_filters:
                    merged.update(f)

                conditions, params = self._build_conditions_for_filters(merged)
                if conditions:
                    group_clauses.append(f"({' AND '.join(conditions)})")
                    all_params.extend(params)

            if group_clauses:
                where_clause = " OR ".join(group_clauses)
                query = f"SELECT * FROM cards WHERE {where_clause} ORDER BY RANDOM() LIMIT 1"
                cursor.execute(query, all_params)
                row = cursor.fetchone()
                return self._row_to_dict(row) if row else None
            else:
                return None

        # Standard AND query
        conditions, params = self._build_conditions_for_filters(parsed.filters)

        if conditions:
            where_clause = " AND ".join(conditions)
            query = f"SELECT * FROM cards WHERE {where_clause} ORDER BY RANDOM() LIMIT 1"
        else:
            query = "SELECT * FROM cards ORDER BY RANDOM() LIMIT 1"
            params = []

        cursor.execute(query, params)
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None
