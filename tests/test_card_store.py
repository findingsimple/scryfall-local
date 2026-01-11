"""Tests for card store (SQLite) - TDD approach."""

import json
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

    def test_insert_handles_decimal_values(self, cards_with_decimal_values: list[dict[str, Any]]):
        """Should handle Decimal values from ijson streaming parser."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # This should not raise TypeError: Object of type Decimal is not JSON serializable
            store.insert_cards(cards_with_decimal_values)
            assert store.get_card_count() == 2

            # Verify cards can be retrieved and queried
            card = store.get_card_by_name("Decimal Test Card")
            assert card is not None
            assert card["cmc"] == 3.0  # Should be stored as float
            assert card["name"] == "Decimal Test Card"

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
                    "type": ["instant"],
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


class TestCardStoreORQueries:
    """Test OR query execution."""

    def test_or_query_simple(self, sample_cards: list[dict[str, Any]]):
        """Should return cards matching either condition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # c:blue OR c:red - should get blue cards AND red cards
            parsed = ParsedQuery(
                filters={},
                or_groups=[
                    [{"colors": {"operator": ":", "value": ["U"]}}],
                    [{"colors": {"operator": ":", "value": ["R"]}}],
                ],
                has_or_clause=True,
                raw_query="c:blue OR c:red",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 2  # Should have both blue and red cards

            # Verify we got both colors
            colors_found = set()
            for card in results:
                colors_found.update(card.get("colors", []))
            assert "U" in colors_found or "R" in colors_found

            store.close()

    def test_or_query_with_type(self, sample_cards: list[dict[str, Any]]):
        """Should return cards matching either type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # t:creature OR t:instant
            parsed = ParsedQuery(
                filters={},
                or_groups=[
                    [{"type": "creature"}],
                    [{"type": "instant"}],
                ],
                has_or_clause=True,
                raw_query="t:creature OR t:instant",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 2

            # Verify we got both types
            for card in results:
                type_line = card.get("type_line", "").lower()
                assert "creature" in type_line or "instant" in type_line

            store.close()

    def test_or_query_with_complex_conditions(self, sample_cards: list[dict[str, Any]]):
        """Should handle OR with complex conditions in each group."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # (c:blue t:instant) OR (c:red t:creature)
            parsed = ParsedQuery(
                filters={},
                or_groups=[
                    [
                        {"colors": {"operator": ":", "value": ["U"]}},
                        {"type": "instant"},
                    ],
                    [
                        {"colors": {"operator": ":", "value": ["R"]}},
                        {"type": "creature"},
                    ],
                ],
                has_or_clause=True,
                raw_query="(c:blue t:instant) OR (c:red t:creature)",
            )

            results = store.execute_query(parsed)

            for card in results:
                colors = card.get("colors", [])
                type_line = card.get("type_line", "").lower()
                # Either blue instant OR red creature
                is_blue_instant = "U" in colors and "instant" in type_line
                is_red_creature = "R" in colors and "creature" in type_line
                assert is_blue_instant or is_red_creature

            store.close()

    def test_or_query_empty_groups(self):
        """Should handle empty or_groups gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")

            parsed = ParsedQuery(
                filters={},
                or_groups=[],
                has_or_clause=True,
                raw_query="",
            )

            results = store.execute_query(parsed)
            assert results == []

            store.close()

    def test_or_query_parenthesized_with_outer_filter(self, sample_cards: list[dict[str, Any]]):
        """(t:creature OR t:instant) c:blue - should AND outer filter with each OR group."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Simulates: (t:creature OR t:instant) c:blue
            # Should find blue creatures OR blue instants
            parsed = ParsedQuery(
                filters={},
                or_groups=[
                    [
                        {"type": "creature"},
                        {"colors": {"operator": ":", "value": ["U"]}},
                    ],
                    [
                        {"type": "instant"},
                        {"colors": {"operator": ":", "value": ["U"]}},
                    ],
                ],
                has_or_clause=True,
                raw_query="(t:creature OR t:instant) c:blue",
            )

            results = store.execute_query(parsed)

            # All results must be blue AND either creature or instant
            for card in results:
                colors = card.get("colors", [])
                type_line = card.get("type_line", "").lower()
                assert "U" in colors, f"Card {card['name']} should be blue"
                assert "creature" in type_line or "instant" in type_line, \
                    f"Card {card['name']} should be creature or instant"

            store.close()


class TestCardStoreQueryByKeyword:
    """Test keyword ability queries."""

    def test_query_by_keyword(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Should find cards with specific keyword."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            parsed = ParsedQuery(
                filters={"keyword": ["Flying"]},
                raw_query="kw:flying",
            )
            results = store.execute_query(parsed)

            assert len(results) >= 1
            for card in results:
                assert "Flying" in card.get("keywords", [])

            store.close()

    def test_query_by_keyword_case_insensitive(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Keyword search should be case insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            # Using uppercase in filter value
            parsed = ParsedQuery(
                filters={"keyword": ["FLYING"]},
                raw_query="kw:FLYING",
            )
            results = store.execute_query(parsed)

            assert len(results) >= 1

            store.close()

    def test_query_by_keyword_not(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Should exclude cards with keyword (negation)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            parsed = ParsedQuery(
                filters={"keyword_not": ["Flying"]},
                raw_query="-kw:flying",
            )
            results = store.execute_query(parsed)

            for card in results:
                keywords = card.get("keywords", [])
                assert "Flying" not in keywords

            store.close()

    def test_query_by_keyword_combined_with_type(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Should combine keyword with type filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            parsed = ParsedQuery(
                filters={
                    "type": ["creature"],
                    "keyword": ["Flying"],
                },
                raw_query="t:creature kw:flying",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert "Creature" in card["type_line"]
                assert "Flying" in card.get("keywords", [])

            store.close()

    def test_query_cards_without_keywords(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Cards with empty keywords array should not match keyword filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            # Find cards with deathtouch
            parsed = ParsedQuery(
                filters={"keyword": ["Deathtouch"]},
                raw_query="kw:deathtouch",
            )
            results = store.execute_query(parsed)

            # Only the deathtouch creature should match
            assert len(results) == 1
            assert results[0]["name"] == "Deathtouch Test Creature"

            store.close()

    def test_query_by_multiple_keywords(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Should find cards with ALL specified keywords (AND)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            # Find cards with both flying AND vigilance
            parsed = ParsedQuery(
                filters={"keyword": ["Flying", "Vigilance"]},
                raw_query="kw:flying kw:vigilance",
            )
            results = store.execute_query(parsed)

            # Only Multi-Keyword Angel has both
            assert len(results) == 1
            assert results[0]["name"] == "Multi-Keyword Angel"
            assert "Flying" in results[0].get("keywords", [])
            assert "Vigilance" in results[0].get("keywords", [])

            store.close()

    def test_keyword_stored_and_retrieved(self, sample_cards_with_keywords: list[dict[str, Any]]):
        """Keywords should be stored and retrieved as list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards_with_keywords)

            card = store.get_card_by_name("Multi-Keyword Angel")
            assert card is not None
            assert isinstance(card.get("keywords"), list)
            assert "Flying" in card["keywords"]
            assert "Vigilance" in card["keywords"]
            assert "Lifelink" in card["keywords"]

            store.close()


class TestCardStoreNegationFilters:
    """Test negation filter handling (-type, -color, etc.)."""

    def test_type_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards matching type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"type_not": ["creature"]},
                raw_query="-t:creature",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert "creature" not in card.get("type_line", "").lower()

            store.close()

    def test_oracle_text_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards with specific oracle text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"oracle_text_not": ["damage"]},
                raw_query="-o:damage",
            )
            results = store.execute_query(parsed)

            for card in results:
                oracle_text = card.get("oracle_text", "") or ""
                assert "damage" not in oracle_text.lower()

            store.close()

    def test_colors_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards with specific color."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"colors_not": {"operator": ":", "value": ["R"]}},
                raw_query="-c:red",
            )
            results = store.execute_query(parsed)

            for card in results:
                colors = card.get("colors", [])
                assert "R" not in colors

            store.close()

    def test_set_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards from specific set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"set_not": "lea"},
                raw_query="-set:lea",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert card.get("set_code", "").lower() != "lea"

            store.close()

    def test_rarity_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards of specific rarity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"rarity_not": "common"},
                raw_query="-r:common",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert card.get("rarity", "").lower() != "common"

            store.close()

    def test_cmc_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards with specific CMC."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"cmc_not": {"operator": ":", "value": 1}},
                raw_query="-cmc:1",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert card.get("cmc") != 1

            store.close()

    def test_combined_negation_with_positive_filter(self, sample_cards: list[dict[str, Any]]):
        """Should support combining negation with positive filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Find creatures that are NOT red
            parsed = ParsedQuery(
                filters={
                    "type": ["creature"],
                    "colors_not": {"operator": ":", "value": ["R"]},
                },
                raw_query="t:creature -c:red",
            )
            results = store.execute_query(parsed)

            for card in results:
                assert "creature" in card.get("type_line", "").lower()
                assert "R" not in card.get("colors", [])

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


class TestCardStorePagination:
    """Test pagination with offset."""

    def test_query_with_offset(self, sample_cards: list[dict[str, Any]]):
        """Should skip results when offset is specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Get first page
            page1 = store.execute_query(ParsedQuery(raw_query=""), limit=2, offset=0)
            # Get second page
            page2 = store.execute_query(ParsedQuery(raw_query=""), limit=2, offset=2)

            assert len(page1) == 2
            assert len(page2) >= 1  # May be less if fewer cards
            # Ensure no overlap
            page1_ids = {c["id"] for c in page1}
            page2_ids = {c["id"] for c in page2}
            assert len(page1_ids & page2_ids) == 0

            store.close()

    def test_query_offset_with_filter(self, sample_cards: list[dict[str, Any]]):
        """Should paginate filtered results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Get all results
            parsed = ParsedQuery(
                filters={"type": "creature"},
                raw_query="t:creature",
            )
            all_results = store.execute_query(parsed, limit=100, offset=0)

            if len(all_results) >= 2:
                # Get first result only
                first = store.execute_query(parsed, limit=1, offset=0)
                # Get second result only
                second = store.execute_query(parsed, limit=1, offset=1)

                assert first[0]["id"] != second[0]["id"]

            store.close()

    def test_count_matches_all_cards(self, sample_cards: list[dict[str, Any]]):
        """count_matches should return total card count for empty query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(raw_query="")
            count = store.count_matches(parsed)

            assert count == len(sample_cards)

            store.close()

    def test_count_matches_with_filter(self, sample_cards: list[dict[str, Any]]):
        """count_matches should return filtered count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={"type": "creature"},
                raw_query="t:creature",
            )
            count = store.count_matches(parsed)
            results = store.execute_query(parsed, limit=100)

            assert count == len(results)

            store.close()

    def test_count_matches_independent_of_limit(self, sample_cards: list[dict[str, Any]]):
        """count_matches should return total, not limited count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(raw_query="")

            # Get limited results
            results = store.execute_query(parsed, limit=2)
            # Get total count
            count = store.count_matches(parsed)

            # count should be total cards, not limited to 2
            assert count == len(sample_cards)
            assert len(results) == 2
            assert count > len(results)

            store.close()

    def test_count_matches_with_or_query(self, sample_cards: list[dict[str, Any]]):
        """count_matches should work with OR queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            parsed = ParsedQuery(
                filters={},
                or_groups=[
                    [{"type": "creature"}],
                    [{"type": "instant"}],
                ],
                has_or_clause=True,
                raw_query="t:creature OR t:instant",
            )
            count = store.count_matches(parsed)
            results = store.execute_query(parsed, limit=100)

            assert count == len(results)

            store.close()


class TestCardStoreConcurrentAccess:
    """Test concurrent database access."""

    def test_multiple_readers(self, sample_cards: list[dict[str, Any]]):
        """Multiple read operations should work concurrently."""
        import threading
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)
            store.insert_cards(sample_cards)

            results = []
            errors = []

            def read_cards():
                try:
                    # Create a new connection for this thread
                    thread_store = CardStore(db_path)
                    cards = thread_store.execute_query(ParsedQuery(raw_query=""))
                    results.append(len(cards))
                    thread_store.close()
                except Exception as e:
                    errors.append(str(e))

            # Start multiple reader threads
            threads = [threading.Thread(target=read_cards) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Errors: {errors}"
            assert all(r == len(sample_cards) for r in results)

            store.close()

    def test_writer_and_readers(self, sample_cards: list[dict[str, Any]]):
        """Writing while reading should not cause errors when using separate connections."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            # Initial setup
            store = CardStore(db_path)
            store.insert_cards(sample_cards[:2])  # Insert some cards first
            store.close()

            errors = []

            def read_cards():
                try:
                    # Each thread gets its own connection
                    thread_store = CardStore(db_path)
                    for _ in range(10):
                        thread_store.execute_query(ParsedQuery(raw_query=""))
                    thread_store.close()
                except Exception as e:
                    errors.append(str(e))

            def write_cards():
                try:
                    # Writer thread also uses its own connection
                    write_store = CardStore(db_path)
                    for card in sample_cards[2:]:
                        write_store.insert_card(card)
                    write_store.close()
                except Exception as e:
                    errors.append(str(e))

            reader = threading.Thread(target=read_cards)
            writer = threading.Thread(target=write_cards)

            reader.start()
            writer.start()
            reader.join()
            writer.join()

            assert len(errors) == 0, f"Errors: {errors}"


class TestCardStoreMigration:
    """Test database schema migration."""

    def test_migration_adds_missing_columns(self):
        """Should add missing columns when opening old database."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"

            # Create an "old" database with minimal schema (missing new columns)
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE cards (
                    id TEXT PRIMARY KEY,
                    oracle_id TEXT,
                    name TEXT NOT NULL,
                    mana_cost TEXT,
                    cmc REAL,
                    type_line TEXT,
                    oracle_text TEXT,
                    power TEXT,
                    toughness TEXT,
                    colors TEXT,
                    color_identity TEXT,
                    set_code TEXT,
                    set_name TEXT,
                    rarity TEXT,
                    image_uris TEXT,
                    legalities TEXT,
                    prices TEXT,
                    raw_data TEXT
                )
            """)

            # Insert a card with data in raw_data that should be migrated
            raw_data = {
                "keywords": ["Flying", "Vigilance"],
                "artist": "Test Artist",
                "released_at": "2024-01-01",
                "loyalty": "4",
                "flavor_text": "Test flavor",
                "collector_number": "123",
            }
            cursor.execute(
                "INSERT INTO cards (id, name, raw_data) VALUES (?, ?, ?)",
                ("test-id", "Test Card", json.dumps(raw_data)),
            )
            conn.commit()
            conn.close()

            # Open with CardStore - should trigger migration
            store = CardStore(db_path)

            # Verify new columns exist and have data
            card = store.get_card_by_id("test-id")
            assert card is not None
            assert card.get("keywords") == ["Flying", "Vigilance"]
            assert card.get("artist") == "Test Artist"
            assert card.get("released_at") == "2024-01-01"
            assert card.get("loyalty") == "4"
            assert card.get("flavor_text") == "Test flavor"
            assert card.get("collector_number") == "123"

            store.close()

    def test_migration_preserves_existing_data(self, sample_cards: list[dict[str, Any]]):
        """Migration should not affect databases that already have all columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"

            # Create database with full schema
            store = CardStore(db_path)
            store.insert_cards(sample_cards)
            original_count = store.get_card_count()
            store.close()

            # Reopen - should not cause issues
            store = CardStore(db_path)
            assert store.get_card_count() == original_count

            # Verify cards are intact
            for card_data in sample_cards:
                card = store.get_card_by_id(card_data["id"])
                assert card is not None
                assert card["name"] == card_data["name"]

            store.close()

    def test_migration_handles_null_raw_data(self):
        """Migration should handle cards with NULL raw_data gracefully."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"

            # Create old database with NULL raw_data
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE cards (
                    id TEXT PRIMARY KEY,
                    oracle_id TEXT,
                    name TEXT NOT NULL,
                    mana_cost TEXT,
                    cmc REAL,
                    type_line TEXT,
                    oracle_text TEXT,
                    power TEXT,
                    toughness TEXT,
                    colors TEXT,
                    color_identity TEXT,
                    set_code TEXT,
                    set_name TEXT,
                    rarity TEXT,
                    image_uris TEXT,
                    legalities TEXT,
                    prices TEXT,
                    raw_data TEXT
                )
            """)
            cursor.execute(
                "INSERT INTO cards (id, name, raw_data) VALUES (?, ?, ?)",
                ("test-id", "Test Card", None),
            )
            conn.commit()
            conn.close()

            # Should not crash when opening
            store = CardStore(db_path)
            card = store.get_card_by_id("test-id")
            assert card is not None
            assert card["name"] == "Test Card"
            # New columns should be None
            assert card.get("keywords") is None
            assert card.get("artist") is None

            store.close()
