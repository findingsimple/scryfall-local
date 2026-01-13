"""Tests for import_utils module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.import_utils import import_cards_streaming
from src.card_store import CardStore


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
                count = import_cards_streaming(json_file, store)

                assert count == 3
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
                count = import_cards_streaming(
                    json_file, store, progress_callback=progress_callback
                )

                assert count == 1500
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
                count = import_cards_streaming(json_file, store)

                assert count == 0
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
                count = import_cards_streaming(
                    json_file,
                    store,
                    batch_size=100,
                    progress_callback=progress_callback,
                )

                assert count == 250
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

            store.close()
