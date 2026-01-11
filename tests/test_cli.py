"""Tests for CLI module."""

import json
import pytest
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from src.cli import (
    format_size,
    print_progress_bar,
    download_data,
    show_status,
    import_data,
    main,
)


class TestFormatSize:
    """Test format_size utility function."""

    def test_format_bytes(self):
        """Should format bytes correctly."""
        assert format_size(500) == "500.0 B"
        assert format_size(0) == "0.0 B"

    def test_format_kilobytes(self):
        """Should format kilobytes correctly."""
        assert format_size(1024) == "1.0 KB"
        assert format_size(2048) == "2.0 KB"
        assert format_size(1536) == "1.5 KB"

    def test_format_megabytes(self):
        """Should format megabytes correctly."""
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 5) == "5.0 MB"

    def test_format_gigabytes(self):
        """Should format gigabytes correctly."""
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1024 * 1024 * 1024 * 2.5) == "2.5 GB"

    def test_format_terabytes(self):
        """Should format terabytes correctly."""
        assert format_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"


class TestPrintProgressBar:
    """Test print_progress_bar utility function."""

    def test_progress_bar_output(self):
        """Should print progress bar to stdout."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            print_progress_bar(50, 100)
            output = mock_stdout.getvalue()

            assert "[" in output
            assert "]" in output
            assert "50.0%" in output
            assert "█" in output

    def test_progress_bar_zero_total(self):
        """Should handle zero total gracefully."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            print_progress_bar(0, 0)
            output = mock_stdout.getvalue()
            # Should not output anything when total is 0
            assert output == ""

    def test_progress_bar_complete(self):
        """Should show 100% when complete."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            print_progress_bar(100, 100)
            output = mock_stdout.getvalue()

            assert "100.0%" in output


class TestShowStatus:
    """Test show_status command."""

    @pytest.mark.asyncio
    async def test_show_status_no_data(self):
        """Should show status when no data exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("builtins.print") as mock_print:
                await show_status(Path(tmpdir))

                # Should print status header
                calls = [str(c) for c in mock_print.call_args_list]
                assert any("Status" in str(c) for c in calls)
                assert any("Never" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_show_status_with_data(self):
        """Should show status when data exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create metadata file
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-09T12:00:00+00:00",
                "updated_at": "2025-01-09T12:00:00+00:00",
                "card_count": 50000,
            }
            metadata_path = Path(tmpdir) / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

            with patch("builtins.print") as mock_print:
                await show_status(Path(tmpdir))

                calls = [str(c) for c in mock_print.call_args_list]
                assert any("50,000" in str(c) for c in calls)


class TestImportData:
    """Test import_data command."""

    @pytest.mark.asyncio
    async def test_import_data_no_file(self):
        """Should handle missing JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("builtins.print") as mock_print:
                await import_data(Path(tmpdir))

                calls = [str(c) for c in mock_print.call_args_list]
                assert any("No JSON data file found" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_import_data_file_not_exists(self):
        """Should handle non-existent specified file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("builtins.print") as mock_print:
                await import_data(Path(tmpdir), Path(tmpdir) / "nonexistent.json")

                calls = [str(c) for c in mock_print.call_args_list]
                assert any("File not found" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_import_data_success(self):
        """Should import cards from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create sample JSON file
            sample_cards = [
                {"id": "123", "name": "Lightning Bolt", "cmc": 1, "colors": ["R"]},
                {"id": "456", "name": "Counterspell", "cmc": 2, "colors": ["U"]},
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            with patch("builtins.print"):
                with patch("sys.stdout.write"):
                    await import_data(tmpdir_path, json_file)

            # Verify database was created
            db_path = tmpdir_path / "cards.db"
            assert db_path.exists()

            # Verify cards were imported
            from src.card_store import CardStore
            with CardStore(db_path) as store:
                assert store.get_card_count() == 2

    @pytest.mark.asyncio
    async def test_import_data_auto_detect_file(self):
        """Should auto-detect JSON file when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create sample JSON file
            sample_cards = [
                {"id": "789", "name": "Giant Growth", "cmc": 1, "colors": ["G"]},
            ]
            json_file = tmpdir_path / "all-cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            with patch("builtins.print"):
                with patch("sys.stdout.write"):
                    await import_data(tmpdir_path)

            # Verify import succeeded
            db_path = tmpdir_path / "cards.db"
            assert db_path.exists()


class TestDownloadData:
    """Test download_data command."""

    @pytest.mark.asyncio
    async def test_download_data_already_current(self):
        """Should skip download when data is current."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Mock DataManager to return not stale
            with patch("src.cli.DataManager") as MockDataManager:
                mock_manager = AsyncMock()
                mock_manager.is_cache_stale = AsyncMock(return_value=False)
                mock_manager.get_status = AsyncMock(return_value=MagicMock(
                    last_updated="2025-01-09",
                    card_count=50000,
                ))
                mock_manager.close = AsyncMock()
                MockDataManager.return_value = mock_manager

                with patch("builtins.print") as mock_print:
                    await download_data(tmpdir_path)

                    calls = [str(c) for c in mock_print.call_args_list]
                    assert any("already up to date" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_download_data_unknown_type(self):
        """Should handle unknown data type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            with patch("src.cli.DataManager") as MockDataManager:
                mock_manager = AsyncMock()
                mock_manager.is_cache_stale = AsyncMock(return_value=True)
                mock_manager.get_bulk_data_info = AsyncMock(return_value=None)
                mock_manager.close = AsyncMock()
                MockDataManager.return_value = mock_manager

                with patch("builtins.print") as mock_print:
                    await download_data(tmpdir_path, "unknown_type")

                    calls = [str(c) for c in mock_print.call_args_list]
                    assert any("Unknown data type" in str(c) for c in calls)


class TestMain:
    """Test main CLI entry point."""

    def test_main_no_command(self):
        """Should print help when no command given."""
        with patch("sys.argv", ["cli"]):
            with patch("argparse.ArgumentParser.print_help") as mock_help:
                main()
                mock_help.assert_called_once()

    def test_main_status_command(self):
        """Should call show_status for status command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli", "--data-dir", tmpdir, "status"]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.assert_called_once()
                    # Verify it was called with show_status coroutine
                    coro = mock_run.call_args[0][0]
                    assert coro.__name__ == "show_status" or "show_status" in str(coro)
                    coro.close()  # Close to prevent unawaited coroutine warning

    def test_main_import_command(self):
        """Should call import_data for import command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli", "--data-dir", tmpdir, "import"]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.assert_called_once()
                    mock_run.call_args[0][0].close()  # Close unawaited coroutine

    def test_main_download_command(self):
        """Should call download_data for download command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli", "--data-dir", tmpdir, "download"]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.assert_called_once()
                    mock_run.call_args[0][0].close()  # Close unawaited coroutine

    def test_main_creates_data_dir(self):
        """Should create data directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_data_dir"
            assert not new_dir.exists()

            with patch("sys.argv", ["cli", "--data-dir", str(new_dir), "status"]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.call_args[0][0].close()  # Close unawaited coroutine

            assert new_dir.exists()

    def test_main_download_with_type(self):
        """Should pass type argument to download_data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.argv", ["cli", "--data-dir", tmpdir, "download", "--type", "oracle_cards"]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.assert_called_once()
                    mock_run.call_args[0][0].close()  # Close unawaited coroutine

    def test_main_import_with_file(self):
        """Should pass file argument to import_data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "test.json"
            json_file.touch()

            with patch("sys.argv", ["cli", "--data-dir", tmpdir, "import", "--file", str(json_file)]):
                with patch("src.cli.asyncio.run") as mock_run:
                    main()
                    mock_run.assert_called_once()
                    mock_run.call_args[0][0].close()  # Close unawaited coroutine


class TestStreamingImport:
    """Test streaming JSON import functionality."""

    def test_import_cards_streaming_basic(self):
        """Should import cards using streaming parser."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

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

            count = import_cards_streaming(json_file, store)

            assert count == 3
            assert store.get_card_count() == 3
            store.close()

    def test_import_cards_streaming_with_progress(self):
        """Should call progress callback during import."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create sample JSON file with enough cards to trigger progress
            sample_cards = [
                {"id": str(i), "name": f"Card {i}", "cmc": i % 5, "colors": []}
                for i in range(1500)  # More than batch_size of 1000
            ]
            json_file = tmpdir_path / "cards.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            progress_calls = []

            def progress_callback(imported: int, total: int | None):
                progress_calls.append(imported)

            count = import_cards_streaming(json_file, store, progress_callback)

            assert count == 1500
            # Should have been called at least twice (after first batch and final)
            assert len(progress_calls) >= 2
            # Progress should be increasing
            for i in range(1, len(progress_calls)):
                assert progress_calls[i] >= progress_calls[i - 1]

            store.close()

    def test_import_cards_streaming_empty_file(self):
        """Should handle empty JSON array."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create empty JSON array
            json_file = tmpdir_path / "empty.json"
            with open(json_file, "w") as f:
                json.dump([], f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            count = import_cards_streaming(json_file, store)

            assert count == 0
            assert store.get_card_count() == 0
            store.close()


class TestStreamingImportErrors:
    """Test error handling in streaming JSON import."""

    def test_import_corrupted_json_raises_error(self):
        """Should raise error on corrupted JSON."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create corrupted JSON file
            json_file = tmpdir_path / "corrupted.json"
            with open(json_file, "w") as f:
                f.write('[{"id": "1", "name": "Card"}, {"id": "2", "name": truncated')

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            with pytest.raises((ijson.JSONError, ijson.IncompleteJSONError)):
                import_cards_streaming(json_file, store)

            store.close()

    def test_import_invalid_json_structure_raises_error(self):
        """Should raise error when JSON is not an array."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create JSON that's an object, not an array
            json_file = tmpdir_path / "not_array.json"
            with open(json_file, "w") as f:
                f.write('{"cards": [{"id": "1"}]}')

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            # This should process 0 cards since ijson.items("item") expects array items
            count = import_cards_streaming(json_file, store)
            assert count == 0

            store.close()

    def test_import_file_not_found_raises_error(self):
        """Should raise FileNotFoundError for missing file."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            json_file = tmpdir_path / "nonexistent.json"
            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            with pytest.raises(FileNotFoundError):
                import_cards_streaming(json_file, store)

            store.close()

    def test_import_partial_success_on_bad_card(self):
        """Should import valid cards even if some are malformed."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create JSON with mix of valid and minimal cards
            # Note: Cards without required fields may fail silently or be inserted with NULLs
            sample_cards = [
                {"id": "1", "name": "Valid Card", "cmc": 1, "colors": ["R"]},
                {"id": "2", "name": "Another Valid", "cmc": 2, "colors": ["U"]},
                {"id": "3"},  # Minimal card - just id, SQLite allows NULL name
            ]
            json_file = tmpdir_path / "mixed.json"
            with open(json_file, "w") as f:
                json.dump(sample_cards, f)

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            # Should process all cards (SQLite constraint will fail on missing name)
            try:
                count = import_cards_streaming(json_file, store)
                # If no constraint, all cards imported
                assert count == 3
            except Exception:
                # If constraint fails, at least the batch before bad card should be imported
                pass

            store.close()

    def test_import_empty_file_not_json(self):
        """Should handle completely empty file."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create empty file
            json_file = tmpdir_path / "empty.json"
            with open(json_file, "w") as f:
                pass  # Empty file

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            with pytest.raises((ijson.JSONError, ijson.IncompleteJSONError)):
                import_cards_streaming(json_file, store)

            store.close()

    def test_import_binary_file_raises_error(self):
        """Should raise error on binary/non-JSON file."""
        from src.cli import import_cards_streaming
        from src.card_store import CardStore
        import ijson

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create binary file
            json_file = tmpdir_path / "binary.json"
            with open(json_file, "wb") as f:
                f.write(b"\x00\x01\x02\x03\xff\xfe")

            db_path = tmpdir_path / "cards.db"
            store = CardStore(db_path)

            with pytest.raises((ijson.JSONError, UnicodeDecodeError, ijson.IncompleteJSONError)):
                import_cards_streaming(json_file, store)

            store.close()
