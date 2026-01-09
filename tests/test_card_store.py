"""Tests for card store (SQLite) - TDD approach."""

import pytest
import tempfile
from pathlib import Path
from typing import Any

from src.card_store import CardStore
from src.query_parser import ParsedQuery


class TestCardStoreSchema:
    """Test database schema creation."""

    def test_create_database(self):
        """Database should be created successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)
            assert db_path.exists()
            store.close()

    def test_create_tables(self):
        """Tables should be created on initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Check tables exist
            tables = store.get_table_names()
            assert "cards" in tables
            assert "cards_fts" in tables  # FTS5 table

            store.close()


class TestCardStoreInsert:
    """Test card insertion."""

    def test_insert_single_card(self, lightning_bolt: dict[str, Any]):
        """Should insert a single card."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_card(lightning_bolt)
            assert store.get_card_count() == 1

            store.close()

    def test_insert_multiple_cards(self, sample_cards: list[dict[str, Any]]):
        """Should insert multiple cards."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(sample_cards)
            assert store.get_card_count() == len(sample_cards)

            store.close()

    def test_insert_preserves_all_fields(self, lightning_bolt: dict[str, Any]):
        """Inserted card should have all original fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_card(lightning_bolt)
            card = store.get_card_by_id(lightning_bolt["id"])

            assert card["name"] == lightning_bolt["name"]
            assert card["mana_cost"] == lightning_bolt["mana_cost"]
            assert card["cmc"] == lightning_bolt["cmc"]
            assert card["type_line"] == lightning_bolt["type_line"]
            assert card["oracle_text"] == lightning_bolt["oracle_text"]

            store.close()


class TestCardStoreQueryByName:
    """Test name-based queries."""

    def test_get_card_by_exact_name(self, sample_cards: list[dict[str, Any]]):
        """Should find card by exact name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            card = store.get_card_by_name("Lightning Bolt")
            assert card is not None
            assert card["name"] == "Lightning Bolt"

            store.close()

    def test_get_card_by_exact_name_not_found(self, sample_cards: list[dict[str, Any]]):
        """Should return None for non-existent name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            card = store.get_card_by_name("Nonexistent Card")
            assert card is None

            store.close()

    def test_search_partial_name(self, sample_cards: list[dict[str, Any]]):
        """Should find cards matching partial name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.search_by_partial_name("bolt")
            assert len(results) >= 1
            assert any(c["name"] == "Lightning Bolt" for c in results)

            store.close()

    def test_search_partial_name_case_insensitive(self, sample_cards: list[dict[str, Any]]):
        """Partial name search should be case insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.search_by_partial_name("LIGHTNING")
            assert len(results) >= 1
            assert any(c["name"] == "Lightning Bolt" for c in results)

            store.close()


class TestCardStoreQueryByColor:
    """Test color-based queries."""

    def test_query_single_color(self, sample_cards: list[dict[str, Any]]):
        """Should find cards by single color."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_color(["R"], operator=":")
            assert len(results) >= 1
            assert all("R" in c["colors"] for c in results)

            store.close()

    def test_query_multiple_colors(self, sample_cards: list[dict[str, Any]]):
        """Should find cards matching multiple colors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Should find Nicol Bolas (UBR)
            results = store.query_by_color(["U", "B", "R"], operator=":")
            assert any("Nicol Bolas" in c["name"] for c in results)

            store.close()

    def test_query_colorless(self, sample_cards: list[dict[str, Any]]):
        """Should find colorless cards."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_color([], operator=":")
            assert len(results) >= 1
            assert any(c["name"] == "Sol Ring" for c in results)

            store.close()


class TestCardStoreQueryByCmc:
    """Test CMC-based queries."""

    def test_query_cmc_exact(self, sample_cards: list[dict[str, Any]]):
        """Should find cards with exact CMC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_cmc(1, operator="=")
            assert all(c["cmc"] == 1 for c in results)

            store.close()

    def test_query_cmc_greater_equal(self, sample_cards: list[dict[str, Any]]):
        """Should find cards with CMC >= value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_cmc(5, operator=">=")
            assert all(c["cmc"] >= 5 for c in results)
            assert len(results) >= 1

            store.close()

    def test_query_cmc_less_than(self, sample_cards: list[dict[str, Any]]):
        """Should find cards with CMC < value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_cmc(2, operator="<")
            assert all(c["cmc"] < 2 for c in results)

            store.close()


class TestCardStoreQueryByType:
    """Test type-based queries."""

    def test_query_type_creature(self, sample_cards: list[dict[str, Any]]):
        """Should find creatures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_type("creature")
            assert len(results) >= 1
            assert all("Creature" in c["type_line"] for c in results)

            store.close()

    def test_query_type_instant(self, sample_cards: list[dict[str, Any]]):
        """Should find instants."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_type("instant")
            assert len(results) >= 1
            assert all("Instant" in c["type_line"] for c in results)

            store.close()

    def test_query_type_dragon(self, sample_cards: list[dict[str, Any]]):
        """Should find dragons."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_type("dragon")
            assert len(results) >= 1
            assert all("Dragon" in c["type_line"] for c in results)

            store.close()


class TestCardStoreQueryByOracleText:
    """Test oracle text queries using FTS5."""

    def test_query_oracle_simple(self, sample_cards: list[dict[str, Any]]):
        """Should find cards by oracle text keyword."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_oracle_text("flying")
            assert len(results) >= 1
            assert all("flying" in c["oracle_text"].lower() for c in results)

            store.close()

    def test_query_oracle_phrase(self, sample_cards: list[dict[str, Any]]):
        """Should find cards by oracle text phrase."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_oracle_text("deals 3 damage")
            assert len(results) >= 1

            store.close()

    def test_query_oracle_fts(self, sample_cards: list[dict[str, Any]]):
        """FTS should be efficient for text search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Should use FTS index
            results = store.query_by_oracle_text("counter target spell")
            assert any(c["name"] == "Counterspell" for c in results)

            store.close()


class TestCardStoreQueryBySet:
    """Test set-based queries."""

    def test_query_by_set(self, sample_cards: list[dict[str, Any]]):
        """Should find cards by set code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_set("leb")
            assert len(results) >= 1
            assert all(c["set"] == "leb" for c in results)

            store.close()


class TestCardStoreQueryByRarity:
    """Test rarity-based queries."""

    def test_query_by_rarity(self, sample_cards: list[dict[str, Any]]):
        """Should find cards by rarity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.query_by_rarity("mythic")
            assert len(results) >= 1
            assert all(c["rarity"] == "mythic" for c in results)

            store.close()


class TestCardStoreComplexQueries:
    """Test complex queries combining multiple filters."""

    def test_query_from_parsed_query(self, sample_cards: list[dict[str, Any]]):
        """Should execute query from ParsedQuery object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # c:blue t:instant
            parsed = ParsedQuery(
                filters={
                    "colors": {"operator": ":", "value": ["U"]},
                    "type": "instant",
                },
                raw_query="c:blue t:instant",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 1
            assert all("U" in c["colors"] for c in results)
            assert all("Instant" in c["type_line"] for c in results)

            store.close()

    def test_query_with_limit(self, sample_cards: list[dict[str, Any]]):
        """Should respect result limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.execute_query(
                ParsedQuery(raw_query=""),
                limit=2,
            )
            assert len(results) <= 2

            store.close()


class TestCardStoreSecurity:
    """Test security measures."""

    def test_sql_injection_name(self, sample_cards: list[dict[str, Any]]):
        """Name query should be safe from SQL injection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Attempt SQL injection
            malicious_name = "'; DROP TABLE cards; --"
            result = store.get_card_by_name(malicious_name)

            # Table should still exist
            assert result is None
            assert store.get_card_count() == len(sample_cards)

            store.close()

    def test_sql_injection_search(self, sample_cards: list[dict[str, Any]]):
        """Search queries should be safe from SQL injection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Attempt SQL injection
            malicious_query = "' OR '1'='1"
            results = store.search_by_partial_name(malicious_query)

            # Should not return all cards
            assert len(results) < len(sample_cards)

            store.close()

    def test_parameterized_queries(self, sample_cards: list[dict[str, Any]]):
        """All queries should use parameterized statements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Various inputs that shouldn't break queries
            test_inputs = [
                "test'test",
                "test\"test",
                "test;test",
                "test--test",
                "test/*test",
            ]

            for inp in test_inputs:
                # These should not raise exceptions
                store.get_card_by_name(inp)
                store.search_by_partial_name(inp)
                store.query_by_type(inp)
                store.query_by_oracle_text(inp)

            # Table should still be intact
            assert store.get_card_count() == len(sample_cards)

            store.close()


class TestCardStoreResultFormat:
    """Test result format for agentic use."""

    def test_result_is_dict(self, sample_cards: list[dict[str, Any]]):
        """Results should be dictionaries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            results = store.execute_query(ParsedQuery(raw_query=""))
            assert all(isinstance(r, dict) for r in results)

            store.close()

    def test_result_includes_all_fields(self, lightning_bolt: dict[str, Any]):
        """Results should include all card fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_card(lightning_bolt)

            results = store.execute_query(ParsedQuery(raw_query=""))
            card = results[0]

            expected_fields = ["id", "name", "mana_cost", "cmc", "type_line", "oracle_text", "colors", "set", "rarity"]
            for field in expected_fields:
                assert field in card

            store.close()


class TestCardStoreRandomCard:
    """Test random card selection."""

    def test_get_random_card(self, sample_cards: list[dict[str, Any]]):
        """Should return a random card."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            card = store.get_random_card()
            assert card is not None
            assert "name" in card

            store.close()

    def test_get_random_card_with_filter(self, sample_cards: list[dict[str, Any]]):
        """Should return random card matching filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Get random red card
            parsed = ParsedQuery(
                filters={"colors": {"operator": ":", "value": ["R"]}},
                raw_query="c:r",
            )
            card = store.get_random_card(parsed)

            assert card is not None
            assert "R" in card["colors"]

            store.close()
