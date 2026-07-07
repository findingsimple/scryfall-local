"""Tests for import_utils module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.card_store import CardStore
from src.import_utils import import_cards_streaming, import_to_temp_and_swap


class TestImportCardsStreaming:
    """Test the shared streaming import function."""

    def test_import_basic(self):
        """Should import cards from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create sample JSON file
            sample_cards = [
                {"id": "1", "name": "Card One", "cmc": 1, "colors": ["R"]},
                {"id": "2", "name": "Card Two", "cmc": 2, "colors": ["U"]},
                {"id": "3", "name": "Card Three", "cmc": 3, "colors": ["G"]},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 3
                assert skipped == 0
                assert store.get_card_count() == 3
            finally:
                store.close()

    def test_import_with_progress_callback(self):
        """Should call progress callback during import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create enough cards to trigger multiple batches
            sample_cards = [
                {"id": str(i), "name": f"Card {i}", "cmc": i % 5, "colors": []}
                for i in range(1500)
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            progress_calls = []

            def progress_callback(card_count: int) -> None:
                progress_calls.append(card_count)

            try:
                count, skipped = import_cards_streaming(
                    json_file, store, progress_callback=progress_callback
                )

                assert count == 1500
                assert skipped == 0
                # Should have been called at least twice (after first batch and final)
                assert len(progress_calls) >= 2
                # Progress should be increasing
                for i in range(1, len(progress_calls)):
                    assert progress_calls[i] >= progress_calls[i - 1]
                # Final call should have total count
                assert progress_calls[-1] == 1500
            finally:
                store.close()

    def test_import_empty_file(self):
        """Should handle empty JSON array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "empty.json"
            with open(json_file, "w") as f:
                json.dump([], f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 0
                assert skipped == 0
                assert store.get_card_count() == 0
            finally:
                store.close()

    def test_import_custom_batch_size(self):
        """Should respect custom batch size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create 250 cards
            sample_cards = [
                {"id": str(i), "name": f"Card {i}", "cmc": 1, "colors": []}
                for i in range(250)
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            progress_calls = []

            def progress_callback(card_count: int) -> None:
                progress_calls.append(card_count)

            try:
                # Use batch size of 100, so we should get callbacks at 100, 200, 250
                count, skipped = import_cards_streaming(
                    json_file,
                    store,
                    batch_size=100,
                    progress_callback=progress_callback,
                )

                assert count == 250
                assert skipped == 0
                # With batch_size=100 and 250 cards: callbacks at 100, 200, 250
                assert len(progress_calls) == 3
                assert progress_calls == [100, 200, 250]
            finally:
                store.close()

    def test_import_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                with pytest.raises(FileNotFoundError):
                    import_cards_streaming(
                        tmpdir_path / "nonexistent.json", store
                    )
            finally:
                store.close()

    def test_import_invalid_json_structure(self):
        """Should return 0 cards when JSON is an object instead of array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "not_array.json"
            with open(json_file, "w") as f:
                f.write('{"cards": [{"id": "1"}]}')

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                # ijson.items("item") expects array items; object yields 0 cards
                count, skipped = import_cards_streaming(json_file, store)
                assert count == 0
                assert skipped == 0
            finally:
                store.close()

    def test_import_empty_file_not_json(self):
        """Should raise error on completely empty file."""
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "empty.json"
            json_file.touch()  # Empty file

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                with pytest.raises((ijson.JSONError, ijson.IncompleteJSONError)):
                    import_cards_streaming(json_file, store)
            finally:
                store.close()

    def test_import_binary_file_raises_error(self):
        """Should raise error on binary/non-JSON file."""
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "binary.json"
            with open(json_file, "wb") as f:
                f.write(b"\x00\x01\x02\x03\xff\xfe")

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                with pytest.raises((ijson.JSONError, UnicodeDecodeError, ijson.IncompleteJSONError)):
                    import_cards_streaming(json_file, store)
            finally:
                store.close()

    def test_import_corrupted_json(self):
        """Should raise error on corrupted JSON."""
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "corrupted.json"
            with open(json_file, "w") as f:
                f.write('[{"id": "1", "name": "Card"}, {"id": "2", truncated')

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                with pytest.raises(ijson.JSONError):
                    import_cards_streaming(json_file, store)
            finally:
                store.close()

    def test_import_partial_failure_mid_batch(self):
        """Should commit first batch but fail on second batch error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create 1500 cards — with batch_size=1000, that's 2 insert_cards calls
            sample_cards = [
                {"id": str(i), "name": f"Card {i}", "cmc": i % 5, "colors": []}
                for i in range(1500)
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            call_count = 0
            original_insert = store.insert_cards

            def insert_fails_on_second_call(cards):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("Simulated mid-batch failure")
                return original_insert(cards)

            try:
                with patch.object(store, "insert_cards", side_effect=insert_fails_on_second_call):
                    with pytest.raises(RuntimeError, match="Simulated mid-batch failure"):
                        import_cards_streaming(json_file, store)

                # First batch of 1000 was committed before the error
                assert store.get_card_count() == 1000
            finally:
                store.close()

    def test_import_does_not_close_store(self):
        """Function should not close the store - caller manages lifecycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            sample_cards = [{"id": "1", "name": "Test", "cmc": 1, "colors": []}]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            import_cards_streaming(json_file, store)

            # Store should still be usable after import
            assert store.get_card_count() == 1
            card = store.get_card_by_name("Test")
            assert card is not None

    def test_skip_card_missing_id(self):
        """Should skip cards missing the 'id' field and import the rest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": "1", "name": "Good Card", "cmc": 1, "colors": []},
                {"name": "No ID Card", "cmc": 2, "colors": []},  # missing id
                {"id": "3", "name": "Another Good", "cmc": 3, "colors": []},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 2
                assert skipped == 1
                assert store.get_card_count() == 2
                assert store.get_card_by_name("Good Card") is not None
                assert store.get_card_by_name("Another Good") is not None
                assert store.get_card_by_name("No ID Card") is None
            finally:
                store.close()

    def test_skip_non_dict_item(self):
        """Should skip non-dict items in the JSON array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": "1", "name": "Good Card", "cmc": 1, "colors": []},
                "not a dict",
                42,
                None,
                {"id": "5", "name": "Also Good", "cmc": 2, "colors": []},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 2
                assert skipped == 3
                assert store.get_card_count() == 2
                assert store.get_card_by_name("Good Card") is not None
                assert store.get_card_by_name("Also Good") is not None
            finally:
                store.close()

    def test_skip_card_with_empty_string_id(self):
        """Should skip cards with empty string id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": "1", "name": "Good Card", "cmc": 1, "colors": []},
                {"id": "", "name": "Empty ID", "cmc": 2, "colors": []},
                {"id": "3", "name": "Also Good", "cmc": 3, "colors": []},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 2
                assert skipped == 1
                assert store.get_card_by_name("Empty ID") is None
            finally:
                store.close()

    def test_skip_card_with_none_id(self):
        """Should skip cards with None id value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": "1", "name": "Good Card", "cmc": 1, "colors": []},
                {"id": None, "name": "Null ID", "cmc": 2, "colors": []},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 1
                assert skipped == 1
                assert store.get_card_by_name("Null ID") is None
            finally:
                store.close()

    def test_skip_malformed_at_batch_boundary(self):
        """Should handle malformed card at a batch boundary correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": "1", "name": "Card A", "cmc": 1, "colors": []},
                {"id": "2", "name": "Card B", "cmc": 2, "colors": []},
                "malformed at boundary",  # position 2, right at batch_size=2
                {"id": "4", "name": "Card D", "cmc": 4, "colors": []},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(
                    json_file, store, batch_size=2
                )

                assert count == 3
                assert skipped == 1
                assert store.get_card_count() == 3
                assert store.get_card_by_name("Card A") is not None
                assert store.get_card_by_name("Card B") is not None
                assert store.get_card_by_name("Card D") is not None
            finally:
                store.close()

    def test_all_valid_cards_zero_skipped(self):
        """Should report zero skipped when all cards are valid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            cards = [
                {"id": str(i), "name": f"Card {i}", "cmc": i, "colors": []}
                for i in range(5)
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            try:
                count, skipped = import_cards_streaming(json_file, store)

                assert count == 5
                assert skipped == 0
            finally:
                store.close()


class TestImportToTempAndSwap:
    """Test atomic temp-database-then-swap import."""

    def _make_json(self, tmpdir: Path, cards: list[dict]) -> Path:
        """Helper to create a JSON file with card data."""
        json_file = tmpdir / "cards.json"
        with open(json_file, "w") as f:
            json.dump(cards, f)
        return json_file

    def _sample_cards(self, count: int = 3) -> list[dict]:
        """Helper to create sample card data."""
        return [
            {"id": str(i), "name": f"Card {i}", "cmc": i, "colors": []}
            for i in range(count)
        ]

    def test_basic_import(self):
        """Should import cards and create database at target path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_file = self._make_json(tmpdir_path, self._sample_cards(3))
            db_path = tmpdir_path / "cards.db"

            count, skipped = import_to_temp_and_swap(json_file, db_path)

            assert count == 3
            assert skipped == 0
            assert db_path.exists()
            with CardStore(db_path) as store:
                assert store.get_card_count() == 3

    def test_no_temp_files_after_success(self):
        """Should not leave temp files after successful import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_file = self._make_json(tmpdir_path, self._sample_cards())
            db_path = tmpdir_path / "cards.db"

            import_to_temp_and_swap(json_file, db_path)

            assert not db_path.with_suffix(".db.tmp").exists()
            assert not Path(str(db_path) + "-wal").exists()
            assert not Path(str(db_path) + "-shm").exists()

    def test_old_db_preserved_on_import_failure(self):
        """Should preserve old database when import fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"

            # Create an existing database with known data
            old_json = self._make_json(tmpdir_path, [
                {"id": "old-1", "name": "Old Card", "cmc": 1, "colors": []},
            ])
            import_to_temp_and_swap(old_json, db_path)
            assert db_path.exists()

            # Now try to import with a failure mid-way
            json_file = self._make_json(tmpdir_path, self._sample_cards(5))

            with patch(
                "src.import_utils.import_cards_streaming",
                side_effect=RuntimeError("Simulated import failure"),
            ), pytest.raises(RuntimeError, match="Simulated import failure"):
                import_to_temp_and_swap(json_file, db_path)

            # Old database should still be intact
            assert db_path.exists()
            with CardStore(db_path) as store:
                assert store.get_card_count() == 1
                card = store.get_card_by_name("Old Card")
                assert card is not None

    def test_temp_files_cleaned_up_on_failure(self):
        """Should clean up temp files when import fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"
            json_file = self._make_json(tmpdir_path, self._sample_cards())

            with patch(
                "src.import_utils.import_cards_streaming",
                side_effect=RuntimeError("Simulated failure"),
            ), pytest.raises(RuntimeError):
                import_to_temp_and_swap(json_file, db_path)

            assert not db_path.with_suffix(".db.tmp").exists()
            assert not Path(str(db_path.with_suffix(".db.tmp")) + "-wal").exists()
            assert not Path(str(db_path.with_suffix(".db.tmp")) + "-shm").exists()

    def test_leftover_temp_files_cleaned_before_import(self):
        """Should clean up leftover temp files from a previous failed run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"
            json_file = self._make_json(tmpdir_path, self._sample_cards())

            # Create leftover temp files
            temp_path = db_path.with_suffix(".db.tmp")
            temp_path.write_text("leftover")

            count, _ = import_to_temp_and_swap(json_file, db_path)

            assert count == 3
            assert not temp_path.exists()

    def test_replaces_existing_database(self):
        """Should replace existing database with new data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"

            # First import
            old_json = self._make_json(tmpdir_path, [
                {"id": "old-1", "name": "Old Card", "cmc": 1, "colors": []},
            ])
            import_to_temp_and_swap(old_json, db_path)

            # Second import with different data
            new_json = self._make_json(tmpdir_path, [
                {"id": "new-1", "name": "New Card A", "cmc": 2, "colors": ["R"]},
                {"id": "new-2", "name": "New Card B", "cmc": 3, "colors": ["U"]},
            ])
            count, _ = import_to_temp_and_swap(new_json, db_path)

            assert count == 2
            with CardStore(db_path) as store:
                assert store.get_card_count() == 2
                assert store.get_card_by_name("Old Card") is None
                assert store.get_card_by_name("New Card A") is not None

    def test_progress_callback(self):
        """Should pass progress callback through to streaming import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_file = self._make_json(tmpdir_path, self._sample_cards(5))
            db_path = tmpdir_path / "cards.db"

            progress_calls = []
            count, _ = import_to_temp_and_swap(
                json_file, db_path,
                progress_callback=lambda n: progress_calls.append(n),
            )

            assert count == 5
            assert len(progress_calls) >= 1
            assert progress_calls[-1] == 5

    def test_checkpoint_failure_preserves_old_db(self):
        """Should preserve old database and clean up temp if checkpoint fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"

            # Create an existing database
            old_json = self._make_json(tmpdir_path, [
                {"id": "old-1", "name": "Old Card", "cmc": 1, "colors": []},
            ])
            import_to_temp_and_swap(old_json, db_path)

            # Now try import where checkpoint fails
            new_json = self._make_json(tmpdir_path, self._sample_cards(5))

            with patch.object(
                CardStore, "checkpoint",
                side_effect=RuntimeError("Simulated checkpoint failure"),
            ), pytest.raises(RuntimeError, match="Simulated checkpoint failure"):
                import_to_temp_and_swap(new_json, db_path)

            # Old database should be intact
            assert db_path.exists()
            with CardStore(db_path) as store:
                assert store.get_card_count() == 1
                assert store.get_card_by_name("Old Card") is not None

            # No temp files left behind
            assert not db_path.with_suffix(".db.tmp").exists()

    def test_old_wal_shm_files_cleaned_after_swap(self):
        """Should clean up pre-existing WAL/SHM companion files after swap."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            db_path = tmpdir_path / "cards.db"

            # Create initial database
            json_file = self._make_json(tmpdir_path, self._sample_cards(2))
            import_to_temp_and_swap(json_file, db_path)

            # Simulate leftover WAL/SHM files from old database
            wal_path = Path(str(db_path) + "-wal")
            shm_path = Path(str(db_path) + "-shm")
            wal_path.write_text("stale wal data")
            shm_path.write_text("stale shm data")

            # Run a new import
            new_json = self._make_json(tmpdir_path, self._sample_cards(3))
            count, _ = import_to_temp_and_swap(new_json, db_path)

            assert count == 3
            assert not wal_path.exists()
            assert not shm_path.exists()

            # New database should be readable
            with CardStore(db_path) as store:
                assert store.get_card_count() == 3
