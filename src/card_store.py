"""Card store using SQLite with FTS5 for text search.

Provides efficient storage and querying of Scryfall card data.
All queries use parameterized statements for SQL injection prevention.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.query_parser import ParsedQuery


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
                set_code TEXT,
                set_name TEXT,
                rarity TEXT,
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
            power, toughness, colors, color_identity, set_code, set_name,
            rarity, image_uris, legalities, prices, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def _card_to_params(self, card: dict[str, Any]) -> tuple:
        """Extract card data as SQL parameters.

        Args:
            card: Card data dictionary

        Returns:
            Tuple of parameters for SQL insert
        """
        return (
            card.get("id"),
            card.get("oracle_id"),
            card.get("name"),
            card.get("mana_cost"),
            card.get("cmc"),
            card.get("type_line"),
            card.get("oracle_text"),
            card.get("power"),
            card.get("toughness"),
            json.dumps(card.get("colors", [])),
            json.dumps(card.get("color_identity", [])),
            card.get("set"),
            card.get("set_name"),
            card.get("rarity"),
            json.dumps(card.get("image_uris", {})),
            json.dumps(card.get("legalities", {})),
            json.dumps(card.get("prices", {})),
            json.dumps(card),
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
        for field in ["colors", "color_identity", "image_uris", "legalities", "prices"]:
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
        # Use LIKE with parameterized query for safety
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
        elif operator in (":", "="):
            # Exact color match
            # Check that card has all specified colors
            conditions = " AND ".join(
                f"colors LIKE '%\"{c}\"%'" for c in colors
            )
            cursor.execute(
                f"SELECT * FROM cards WHERE {conditions} LIMIT ?",
                (limit,),
            )
        elif operator == ">=":
            # Card has at least these colors
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

        op_map = {
            "=": "=",
            ":": "=",
            ">=": ">=",
            "<=": "<=",
            ">": ">",
            "<": "<",
            "!=": "!=",
        }
        sql_op = op_map.get(operator, "=")

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
            # Try FTS5 search first
            cursor.execute("""
                SELECT cards.* FROM cards
                JOIN cards_fts ON cards.id = cards_fts.id
                WHERE cards_fts MATCH ?
                LIMIT ?
            """, (f'"{safe_text}"', limit))
            results = [self._row_to_dict(row) for row in cursor.fetchall()]
            if results:
                return results
        except sqlite3.OperationalError:
            pass

        # Fallback to LIKE search
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

    def execute_query(
        self,
        parsed: ParsedQuery,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Execute a parsed query.

        Args:
            parsed: ParsedQuery object with filters
            limit: Maximum results to return

        Returns:
            List of matching card dictionaries
        """
        # Start with all cards if no filters
        if parsed.is_empty:
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM cards LIMIT ?", (limit,))
            return [self._row_to_dict(row) for row in cursor.fetchall()]

        # Build query conditions
        conditions: list[str] = []
        params: list[Any] = []

        filters = parsed.filters

        # Name filters
        if "name_exact" in filters:
            conditions.append("name = ?")
            params.append(filters["name_exact"])
        if "name_partial" in filters:
            conditions.append("LOWER(name) LIKE ?")
            params.append(f"%{filters['name_partial'].lower()}%")

        # Color filter
        if "colors" in filters:
            color_filter = filters["colors"]
            colors = color_filter.get("value", [])
            operator = color_filter.get("operator", ":")

            if not colors:
                conditions.append("colors = '[]'")
            else:
                for c in colors:
                    conditions.append(f"colors LIKE ?")
                    params.append(f'%"{c}"%')

        # Color identity filter
        if "color_identity" in filters:
            identity_filter = filters["color_identity"]
            colors = identity_filter.get("value", [])
            operator = identity_filter.get("operator", ":")

            if not colors:
                # Colorless identity
                conditions.append("color_identity = '[]'")
            elif operator in (":", "="):
                # Exact match - must have all these colors in identity
                for c in colors:
                    conditions.append(f"color_identity LIKE ?")
                    params.append(f'%"{c}"%')
            elif operator == ">=":
                # At least these colors
                for c in colors:
                    conditions.append(f"color_identity LIKE ?")
                    params.append(f'%"{c}"%')
            elif operator == "<=":
                # At most these colors (subset) - exclude cards with colors not in set
                all_colors = {"W", "U", "B", "R", "G"}
                allowed_colors = set(colors)
                disallowed_colors = all_colors - allowed_colors
                if disallowed_colors:
                    for c in disallowed_colors:
                        conditions.append(f"color_identity NOT LIKE ?")
                        params.append(f'%"{c}"%')

        # CMC filter
        if "cmc" in filters:
            cmc_filter = filters["cmc"]
            value = cmc_filter.get("value", 0)
            operator = cmc_filter.get("operator", "=")
            op_map = {"=": "=", ":": "=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
            sql_op = op_map.get(operator, "=")
            conditions.append(f"cmc {sql_op} ?")
            params.append(value)

        # Type filter
        if "type" in filters:
            conditions.append("LOWER(type_line) LIKE ?")
            params.append(f"%{filters['type'].lower()}%")

        # Oracle text filter
        if "oracle_text" in filters:
            conditions.append("LOWER(oracle_text) LIKE ?")
            params.append(f"%{filters['oracle_text'].lower()}%")

        # Set filter
        if "set" in filters:
            conditions.append("LOWER(set_code) = ?")
            params.append(filters["set"].lower())

        # Rarity filter
        if "rarity" in filters:
            conditions.append("LOWER(rarity) = ?")
            params.append(filters["rarity"].lower())

        # Format legality filter
        if "format" in filters:
            format_name = filters["format"]
            # legalities is stored as JSON like {"standard": "legal", "modern": "not_legal"}
            # Check if the format value is "legal" or "restricted"
            conditions.append(
                f"(json_extract(legalities, '$.{format_name}') = 'legal' "
                f"OR json_extract(legalities, '$.{format_name}') = 'restricted')"
            )

        # Power filter
        if "power" in filters:
            power_filter = filters["power"]
            value = power_filter.get("value")
            operator = power_filter.get("operator", "=")
            op_map = {"=": "=", ":": "=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
            sql_op = op_map.get(operator, "=")
            if value == "*":
                # Match cards with * power
                conditions.append("power = '*'")
            else:
                # Cast power to integer for comparison (excludes * and NULL)
                conditions.append(f"CAST(power AS INTEGER) {sql_op} ?")
                params.append(value)

        # Toughness filter
        if "toughness" in filters:
            toughness_filter = filters["toughness"]
            value = toughness_filter.get("value")
            operator = toughness_filter.get("operator", "=")
            op_map = {"=": "=", ":": "=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
            sql_op = op_map.get(operator, "=")
            if value == "*":
                # Match cards with * toughness
                conditions.append("toughness = '*'")
            else:
                # Cast toughness to integer for comparison (excludes * and NULL)
                conditions.append(f"CAST(toughness AS INTEGER) {sql_op} ?")
                params.append(value)

        # Price filter
        if "price" in filters:
            price_filter = filters["price"]
            currency = price_filter.get("currency", "usd")
            value = price_filter.get("value")
            operator = price_filter.get("operator", "=")
            op_map = {"=": "=", ":": "=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
            sql_op = op_map.get(operator, "=")
            # prices is stored as JSON like {"usd": "1.50", "eur": "1.20"}
            # Need to cast to REAL for numeric comparison
            conditions.append(
                f"CAST(json_extract(prices, '$.{currency}') AS REAL) {sql_op} ?"
            )
            params.append(value)

        # Build and execute query
        if conditions:
            where_clause = " AND ".join(conditions)
            query = f"SELECT * FROM cards WHERE {where_clause} LIMIT ?"
            params.append(limit)
        else:
            query = "SELECT * FROM cards LIMIT ?"
            params = [limit]

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_random_card(self, parsed: ParsedQuery | None = None) -> dict[str, Any] | None:
        """Get a random card, optionally filtered.

        Args:
            parsed: Optional ParsedQuery for filtering

        Returns:
            Random card dictionary or None if no matches
        """
        if parsed and not parsed.is_empty:
            # Get filtered results then pick random
            results = self.execute_query(parsed, limit=1000)
            if results:
                import random
                return random.choice(results)
            return None

        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None
