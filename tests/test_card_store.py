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

    def test_wal_mode_enabled(self):
        """WAL mode should be enabled for better concurrent read performance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Check journal mode is WAL
            result = store._conn.execute("PRAGMA journal_mode").fetchone()
            assert result[0].lower() == "wal"

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

    def test_insert_cards_atomic_rollback(self, sample_cards: list[dict[str, Any]]):
        """Batch insert should rollback all cards if one fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Create a batch with a bad card in the middle
            good_cards = sample_cards[:3]
            bad_card = {"id": None, "name": None}  # Will fail - NULL id/name
            more_cards = sample_cards[3:5]
            batch = good_cards + [bad_card] + more_cards

            # Insert should fail
            with pytest.raises(Exception):
                store.insert_cards(batch)

            # No cards should be inserted due to rollback
            assert store.get_card_count() == 0

            store.close()

    def test_insert_cards_commits_on_success(self, sample_cards: list[dict[str, Any]]):
        """Batch insert should commit all cards on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(sample_cards)

            # All cards should be committed
            assert store.get_card_count() == len(sample_cards)

            # Verify they persist (close and reopen)
            store.close()
            store = CardStore(db_path)
            assert store.get_card_count() == len(sample_cards)

            store.close()

    def test_upsert_preserves_rowid_and_fts_sync(self, lightning_bolt: dict[str, Any]):
        """Updating a card should preserve rowid and keep FTS in sync."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Insert original card
            store.insert_card(lightning_bolt)

            # Get the original rowid
            cursor = store._conn.cursor()
            cursor.execute("SELECT rowid FROM cards WHERE id = ?", (lightning_bolt["id"],))
            original_rowid = cursor.fetchone()[0]

            # Verify FTS works with original text
            results = store.query_by_oracle_text("3 damage")
            assert len(results) == 1
            assert results[0]["name"] == "Lightning Bolt"

            # Update the card with new oracle text
            updated_card = lightning_bolt.copy()
            updated_card["oracle_text"] = "Lightning Bolt deals 4 damage to any target."
            store.insert_card(updated_card)

            # Verify rowid is preserved (UPSERT behavior, not DELETE+INSERT)
            cursor.execute("SELECT rowid FROM cards WHERE id = ?", (lightning_bolt["id"],))
            new_rowid = cursor.fetchone()[0]
            assert new_rowid == original_rowid, "Rowid should be preserved on update"

            # Verify card count is still 1 (update, not duplicate)
            assert store.get_card_count() == 1

            # Verify FTS is updated - old text should NOT match
            results = store.query_by_oracle_text("3 damage")
            assert len(results) == 0, "Old oracle text should not be in FTS index"

            # Verify FTS has new text
            results = store.query_by_oracle_text("4 damage")
            assert len(results) == 1
            assert results[0]["name"] == "Lightning Bolt"

            store.close()

    def test_upsert_fts_sync_multiple_updates(self, lightning_bolt: dict[str, Any]):
        """Multiple updates should keep FTS properly synced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Insert and update multiple times
            store.insert_card(lightning_bolt)

            for i in range(5):
                updated_card = lightning_bolt.copy()
                updated_card["oracle_text"] = f"Deals {i} damage."
                store.insert_card(updated_card)

            # Should still only have 1 card
            assert store.get_card_count() == 1

            # Only the latest text should be searchable
            for i in range(4):
                results = store.query_by_oracle_text(f"Deals {i} damage")
                assert len(results) == 0, f"Old text 'Deals {i} damage' should not match"

            # Latest update should match
            results = store.query_by_oracle_text("Deals 4 damage")
            assert len(results) == 1

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


class TestCardStoreColorOperators:
    """Test color > and < operators."""

    def test_color_greater_than_operator(self):
        """c>rg should find cards with R and G plus at least one more color."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Mono Red", "colors": ["R"], "color_identity": ["R"]},
                {"id": "2", "name": "Gruul", "colors": ["R", "G"], "color_identity": ["R", "G"]},
                {"id": "3", "name": "Jund", "colors": ["B", "R", "G"], "color_identity": ["B", "R", "G"]},
                {"id": "4", "name": "Five Color", "colors": ["W", "U", "B", "R", "G"], "color_identity": ["W", "U", "B", "R", "G"]},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"colors": {"operator": ">", "value": ["R", "G"]}},
                raw_query="c>rg",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Jund" in names
            assert "Five Color" in names
            assert "Gruul" not in names  # Exactly RG, not more
            assert "Mono Red" not in names

            store.close()

    def test_color_less_than_operator(self):
        """c<rg should find cards with strict subset of {R, G}."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Mono Red", "colors": ["R"], "color_identity": ["R"]},
                {"id": "2", "name": "Mono Green", "colors": ["G"], "color_identity": ["G"]},
                {"id": "3", "name": "Colorless", "colors": [], "color_identity": []},
                {"id": "4", "name": "Gruul", "colors": ["R", "G"], "color_identity": ["R", "G"]},
                {"id": "5", "name": "Jund", "colors": ["B", "R", "G"], "color_identity": ["B", "R", "G"]},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"colors": {"operator": "<", "value": ["R", "G"]}},
                raw_query="c<rg",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Mono Red" in names
            assert "Mono Green" in names
            assert "Colorless" in names
            assert "Gruul" not in names  # Exactly RG, not less
            assert "Jund" not in names

            store.close()

    def test_identity_greater_than_operator(self):
        """id>rg should find cards with RG identity plus at least one more."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Gruul", "colors": ["R", "G"], "color_identity": ["R", "G"]},
                {"id": "2", "name": "Jund", "colors": ["B", "R", "G"], "color_identity": ["B", "R", "G"]},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"color_identity": {"operator": ">", "value": ["R", "G"]}},
                raw_query="id>rg",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Jund" in names
            assert "Gruul" not in names

            store.close()


class TestCardStoreInvertedOperators:
    """Test inverted operators for NOT filters."""

    def test_cmc_not_with_greater_equal(self):
        """-cmc>=5 should find cards with cmc < 5 (inverted operator)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Low Cost", "cmc": 2},
                {"id": "2", "name": "Medium Cost", "cmc": 4},
                {"id": "3", "name": "High Cost", "cmc": 5},
                {"id": "4", "name": "Very High", "cmc": 7},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"cmc_not": {"operator": ">=", "value": 5}},
                raw_query="-cmc>=5",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Low Cost" in names
            assert "Medium Cost" in names
            assert "High Cost" not in names
            assert "Very High" not in names

            store.close()

    def test_power_not_filter(self):
        """-pow:3 should exclude cards with power 3."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Small", "power": "2", "type_line": "Creature"},
                {"id": "2", "name": "Medium", "power": "3", "type_line": "Creature"},
                {"id": "3", "name": "Large", "power": "4", "type_line": "Creature"},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"power_not": {"operator": "=", "value": 3}},
                raw_query="-pow:3",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Small" in names
            assert "Large" in names
            assert "Medium" not in names

            store.close()

    def test_year_not_filter(self):
        """-year:2023 should exclude cards from 2023."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Old Card", "released_at": "2020-01-01"},
                {"id": "2", "name": "New Card", "released_at": "2023-06-15"},
                {"id": "3", "name": "Newer Card", "released_at": "2024-01-01"},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"year_not": {"operator": "=", "value": 2023}},
                raw_query="-year:2023",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Old Card" in names
            assert "Newer Card" in names
            assert "New Card" not in names

            store.close()


class TestCardStoreInvalidFormat:
    """Test invalid format handling."""

    def test_invalid_format_returns_empty(self):
        """f:notaformat should return empty results, not all cards."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Card 1", "legalities": {"standard": "legal"}},
                {"id": "2", "name": "Card 2", "legalities": {"modern": "legal"}},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"format": "notaformat"},
                raw_query="f:notaformat",
            )
            results = store.execute_query(parsed)

            assert len(results) == 0

            store.close()


class TestCardStoreNewFilters:
    """Test new filter types: banned, produces, watermark, block."""

    def test_banned_filter(self):
        """banned:modern should find cards banned in modern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Legal Card", "legalities": {"modern": "legal"}},
                {"id": "2", "name": "Banned Card", "legalities": {"modern": "banned"}},
                {"id": "3", "name": "Not Legal", "legalities": {"modern": "not_legal"}},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"banned": "modern"},
                raw_query="banned:modern",
            )
            results = store.execute_query(parsed)

            assert len(results) == 1
            assert results[0]["name"] == "Banned Card"

            store.close()

    def test_produces_filter(self):
        """produces:g should find cards that produce green mana."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Forest", "produced_mana": ["G"]},
                {"id": "2", "name": "Mountain", "produced_mana": ["R"]},
                {"id": "3", "name": "Dual Land", "produced_mana": ["G", "W"]},
                {"id": "4", "name": "Sol Ring", "produced_mana": ["C"]},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"produces": ["G"]},
                raw_query="produces:g",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Forest" in names
            assert "Dual Land" in names
            assert "Mountain" not in names
            assert "Sol Ring" not in names

            store.close()

    def test_produces_colorless_filter(self):
        """produces:c should find cards that produce colorless mana."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Forest", "produced_mana": ["G"]},
                {"id": "2", "name": "Mountain", "produced_mana": ["R"]},
                {"id": "3", "name": "Sol Ring", "produced_mana": ["C"]},
                {"id": "4", "name": "Mana Crypt", "produced_mana": ["C"]},
                {"id": "5", "name": "City of Brass", "produced_mana": ["W", "U", "B", "R", "G"]},
            ]
            store.insert_cards(cards)

            # produces:c passes an empty list [] which means colorless
            parsed = ParsedQuery(
                filters={"produces": []},
                raw_query="produces:c",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Sol Ring" in names
            assert "Mana Crypt" in names
            assert "Forest" not in names
            assert "City of Brass" not in names

            store.close()

    def test_produces_filter_with_sample_cards(self, sample_cards: list[dict[str, Any]]):
        """produces: filter should work with sample_cards fixture."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # Test produces:g finds Llanowar Elves
            parsed = ParsedQuery(
                filters={"produces": ["G"]},
                raw_query="produces:g",
            )
            results = store.execute_query(parsed)
            names = [c["name"] for c in results]
            assert "Llanowar Elves" in names
            assert "Lightning Bolt" not in names

            # Test produces:b finds Dark Ritual
            parsed = ParsedQuery(
                filters={"produces": ["B"]},
                raw_query="produces:b",
            )
            results = store.execute_query(parsed)
            names = [c["name"] for c in results]
            assert "Dark Ritual" in names
            assert "Llanowar Elves" not in names

            store.close()

    def test_produces_colorless_with_sample_cards(self, sample_cards: list[dict[str, Any]]):
        """produces:c should find Sol Ring from sample_cards fixture."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # produces:c passes an empty list [] which means colorless
            parsed = ParsedQuery(
                filters={"produces": []},
                raw_query="produces:c",
            )
            results = store.execute_query(parsed)
            names = [c["name"] for c in results]
            assert "Sol Ring" in names
            assert "Llanowar Elves" not in names
            assert "Dark Ritual" not in names

            store.close()

    def test_watermark_filter(self):
        """wm:selesnya should find cards with selesnya watermark."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Selesnya Card", "watermark": "selesnya"},
                {"id": "2", "name": "Dimir Card", "watermark": "dimir"},
                {"id": "3", "name": "No Watermark", "watermark": None},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"watermark": "selesnya"},
                raw_query="wm:selesnya",
            )
            results = store.execute_query(parsed)

            assert len(results) == 1
            assert results[0]["name"] == "Selesnya Card"

            store.close()

    def test_block_filter(self):
        """b:innistrad should find cards from Innistrad block sets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Innistrad Card", "set": "isd"},
                {"id": "2", "name": "Dark Ascension Card", "set": "dka"},
                {"id": "3", "name": "Avacyn Card", "set": "avr"},
                {"id": "4", "name": "M19 Card", "set": "m19"},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"block": "innistrad"},
                raw_query="b:innistrad",
            )
            results = store.execute_query(parsed)

            names = [c["name"] for c in results]
            assert "Innistrad Card" in names
            assert "Dark Ascension Card" in names
            assert "Avacyn Card" in names
            assert "M19 Card" not in names

            store.close()

    def test_unknown_block_returns_empty(self):
        """Unknown block should return empty results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            cards = [
                {"id": "1", "name": "Some Card", "set": "m19"},
            ]
            store.insert_cards(cards)

            parsed = ParsedQuery(
                filters={"block": "notablock"},
                raw_query="b:notablock",
            )
            results = store.execute_query(parsed)

            assert len(results) == 0

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


class TestCardStoreManaCost:
    """Test mana cost queries."""

    def test_mana_contains_single_symbol(self, sample_cards: list[dict[str, Any]]):
        """Should find cards containing a single mana symbol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # m:{R} should match cards with R in mana cost
            parsed = ParsedQuery(
                filters={"mana": {"operator": ":", "value": "{R}"}},
                raw_query="m:{R}",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 1
            for card in results:
                assert "{R}" in card.get("mana_cost", "")

            store.close()

    def test_mana_contains_double_symbol(self, sample_cards: list[dict[str, Any]]):
        """Should find cards containing double mana symbols."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # m:{U}{U} should match Counterspell
            parsed = ParsedQuery(
                filters={"mana": {"operator": ":", "value": "{U}{U}"}},
                raw_query="m:{U}{U}",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 1
            for card in results:
                assert "{U}{U}" in card.get("mana_cost", "")

            store.close()

    def test_mana_exact_match(self, sample_cards: list[dict[str, Any]]):
        """Should find cards with exact mana cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # m={R} should match only cards with exactly {R} mana cost
            parsed = ParsedQuery(
                filters={"mana": {"operator": "=", "value": "{R}"}},
                raw_query="m={R}",
            )

            results = store.execute_query(parsed)
            for card in results:
                assert card.get("mana_cost") == "{R}"

            store.close()

    def test_mana_with_generic(self, sample_cards: list[dict[str, Any]]):
        """Should find cards with generic mana in cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # m:{4}{R}{R} should match Shivan Dragon
            parsed = ParsedQuery(
                filters={"mana": {"operator": ":", "value": "{4}{R}{R}"}},
                raw_query="m:{4}{R}{R}",
            )

            results = store.execute_query(parsed)
            assert len(results) >= 1
            for card in results:
                assert "{4}{R}{R}" in card.get("mana_cost", "")

            store.close()

    def test_mana_not_filter(self, sample_cards: list[dict[str, Any]]):
        """Should exclude cards with specific mana symbol."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CardStore(Path(tmpdir) / "cards.db")
            store.insert_cards(sample_cards)

            # -m:{R} should exclude cards with R in mana cost
            parsed = ParsedQuery(
                filters={"mana_not": {"operator": ":", "value": "{R}"}},
                raw_query="-m:{R}",
            )

            results = store.execute_query(parsed)
            for card in results:
                mana_cost = card.get("mana_cost", "") or ""
                assert "{R}" not in mana_cost

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


class TestDoubleFacedCards:
    """Test handling of double-faced cards (transform, modal_dfc, split, adventure)."""

    def test_transform_card_extracts_oracle_text(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have oracle text extracted from card_faces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Insert Delver of Secrets (transform)
            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            # Oracle text should be combined from both faces
            assert "look at the top card" in card["oracle_text"]
            assert "Flying" in card["oracle_text"]
            assert " // " in card["oracle_text"]

            store.close()

    def test_transform_card_extracts_mana_cost(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have mana cost extracted from first face."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            assert "{U}" in card["mana_cost"]

            store.close()

    def test_transform_card_extracts_power_toughness(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have power/toughness from first creature face."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            # Should get first face's stats (Delver is 1/1)
            assert card["power"] == "1"
            assert card["toughness"] == "1"

            store.close()

    def test_transform_card_extracts_type_line(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have type line combined from faces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            assert "Creature" in card["type_line"]
            assert "Human Wizard" in card["type_line"]

            store.close()

    def test_transform_card_extracts_colors(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have colors from card_faces when top-level is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            # Should extract blue from faces
            assert "U" in card["colors"]

            store.close()

    def test_modal_dfc_extracts_oracle_text(self, double_faced_cards: list[dict[str, Any]]):
        """Modal DFCs should have oracle text combined from both faces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            shatterskull = double_faced_cards[1]
            store.insert_card(shatterskull)

            card = store.get_card_by_id(shatterskull["id"])
            assert card is not None
            # Should have text from both Sorcery face and Land face
            assert "damage" in card["oracle_text"].lower()
            assert "Add {R}" in card["oracle_text"]
            assert " // " in card["oracle_text"]

            store.close()

    def test_split_card_extracts_oracle_text(self, double_faced_cards: list[dict[str, Any]]):
        """Split cards should have oracle text combined from both halves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            fire_ice = double_faced_cards[2]
            store.insert_card(fire_ice)

            card = store.get_card_by_id(fire_ice["id"])
            assert card is not None
            # Should have text from both Fire and Ice
            assert "2 damage" in card["oracle_text"]
            assert "Draw a card" in card["oracle_text"]

            store.close()

    def test_split_card_preserves_top_level_colors(self, double_faced_cards: list[dict[str, Any]]):
        """Split cards should preserve colors when already at top level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            fire_ice = double_faced_cards[2]
            store.insert_card(fire_ice)

            card = store.get_card_by_id(fire_ice["id"])
            assert card is not None
            # Fire // Ice has colors at top level
            assert "R" in card["colors"]
            assert "U" in card["colors"]

            store.close()

    def test_adventure_card_extracts_oracle_text(self, double_faced_cards: list[dict[str, Any]]):
        """Adventure cards should have oracle text from both creature and adventure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            bonecrusher = double_faced_cards[3]
            store.insert_card(bonecrusher)

            card = store.get_card_by_id(bonecrusher["id"])
            assert card is not None
            # Should have text from creature and Stomp adventure
            assert "target of a spell" in card["oracle_text"]
            assert "Damage can't be prevented" in card["oracle_text"]

            store.close()

    def test_adventure_card_extracts_power_toughness(self, double_faced_cards: list[dict[str, Any]]):
        """Adventure cards should have power/toughness from creature face."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            bonecrusher = double_faced_cards[3]
            store.insert_card(bonecrusher)

            card = store.get_card_by_id(bonecrusher["id"])
            assert card is not None
            # Bonecrusher Giant is 4/3
            assert card["power"] == "4"
            assert card["toughness"] == "3"

            store.close()

    def test_transform_planeswalker_extracts_loyalty(self, double_faced_cards: list[dict[str, Any]]):
        """Transform planeswalkers should have loyalty from planeswalker face."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            jace = double_faced_cards[4]
            store.insert_card(jace)

            card = store.get_card_by_id(jace["id"])
            assert card is not None
            # Jace, Telepath Unbound has loyalty 5
            assert card["loyalty"] == "5"

            store.close()

    def test_transform_card_extracts_flavor_text(self, double_faced_cards: list[dict[str, Any]]):
        """Transform cards should have flavor text combined from faces."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            delver = double_faced_cards[0]
            store.insert_card(delver)

            card = store.get_card_by_id(delver["id"])
            assert card is not None
            # Should have flavor text from both faces
            assert "hypothesis" in card["flavor_text"]
            assert "famous and dead" in card["flavor_text"]

            store.close()

    def test_dfc_searchable_by_oracle_text(self, double_faced_cards: list[dict[str, Any]]):
        """Double-faced cards should be searchable by their extracted oracle text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            # Search for Delver by its oracle text
            results = store.query_by_oracle_text("upkeep")
            assert len(results) >= 1
            assert any("Delver" in r["name"] for r in results)

            # Search for Bonecrusher by Stomp text
            results = store.query_by_oracle_text("Damage can't be prevented")
            assert len(results) >= 1
            assert any("Bonecrusher" in r["name"] for r in results)

            store.close()

    def test_dfc_searchable_by_type(self, double_faced_cards: list[dict[str, Any]]):
        """Double-faced cards should be searchable by type line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            # Search for creatures
            results = store.query_by_type("creature")
            creature_names = [r["name"] for r in results]
            # Delver, Bonecrusher, and Jace (creature side) should match
            assert any("Delver" in name for name in creature_names)
            assert any("Bonecrusher" in name for name in creature_names)

            store.close()

    def test_normal_card_not_affected(self, sample_cards: list[dict[str, Any]], double_faced_cards: list[dict[str, Any]]):
        """Normal cards (without card_faces) should still work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            # Insert both normal and DFC cards
            store.insert_cards(sample_cards)
            store.insert_cards(double_faced_cards)

            # Check normal card
            bolt = store.get_card_by_name("Lightning Bolt")
            assert bolt is not None
            assert bolt["oracle_text"] == "Lightning Bolt deals 3 damage to any target."
            assert bolt["mana_cost"] == "{R}"

            store.close()


class TestLayoutFilter:
    """Test layout field search functionality."""

    def test_layout_filter_transform(self, double_faced_cards: list[dict[str, Any]]):
        """Should find transform cards by layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            # Search for transform cards
            from src.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse("layout:transform")
            results = store.execute_query(parsed)

            # Should find Delver and Jace (both are transform)
            names = [r["name"] for r in results]
            assert len(results) == 2
            assert any("Delver" in name for name in names)
            assert any("Jace" in name for name in names)

            store.close()

    def test_layout_filter_modal_dfc(self, double_faced_cards: list[dict[str, Any]]):
        """Should find modal DFC cards by layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            from src.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse("layout:modal_dfc")
            results = store.execute_query(parsed)

            # Should find Shatterskull Smashing
            assert len(results) == 1
            assert "Shatterskull" in results[0]["name"]

            store.close()

    def test_layout_filter_adventure(self, double_faced_cards: list[dict[str, Any]]):
        """Should find adventure cards by layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            from src.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse("layout:adventure")
            results = store.execute_query(parsed)

            # Should find Bonecrusher Giant
            assert len(results) == 1
            assert "Bonecrusher" in results[0]["name"]

            store.close()

    def test_layout_filter_split(self, double_faced_cards: list[dict[str, Any]]):
        """Should find split cards by layout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            from src.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse("layout:split")
            results = store.execute_query(parsed)

            # Should find Fire // Ice
            assert len(results) == 1
            assert "Fire" in results[0]["name"]

            store.close()

    def test_layout_not_filter(self, double_faced_cards: list[dict[str, Any]]):
        """Should exclude cards with negated layout filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            from src.query_parser import QueryParser
            parser = QueryParser()
            parsed = parser.parse("-layout:transform")
            results = store.execute_query(parsed)

            # Should find all non-transform cards (3 cards)
            names = [r["name"] for r in results]
            assert len(results) == 3
            assert not any("Delver" in name for name in names)
            assert not any("Jace" in name for name in names)

            store.close()

    def test_layout_in_result(self, double_faced_cards: list[dict[str, Any]]):
        """Layout should be included in query results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            card = store.get_card_by_name("Delver of Secrets // Insectile Aberration")
            assert card is not None
            assert card["layout"] == "transform"

            card = store.get_card_by_name("Bonecrusher Giant // Stomp")
            assert card is not None
            assert card["layout"] == "adventure"

            store.close()

    def test_layout_combined_with_other_filters(self, double_faced_cards: list[dict[str, Any]]):
        """Layout filter should work with other filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cards.db"
            store = CardStore(db_path)

            store.insert_cards(double_faced_cards)

            from src.query_parser import QueryParser
            parser = QueryParser()

            # Transform cards that are creatures
            parsed = parser.parse("layout:transform t:creature")
            results = store.execute_query(parsed)

            # Both Delver and Jace have creature sides
            assert len(results) == 2

            store.close()
