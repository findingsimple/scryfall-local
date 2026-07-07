"""Tests for data manager (bulk data download) - TDD approach."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from scryfall_local.data_manager import DataManager, DataStatus

# Sample bulk data catalog response
SAMPLE_CATALOG = {
    "object": "list",
    "has_more": False,
    "data": [
        {
            "object": "bulk_data",
            "id": "abc123",
            "type": "all_cards",
            "updated_at": "2025-01-09T12:00:00.000+00:00",
            "uri": "https://api.scryfall.com/bulk-data/abc123",
            "name": "All Cards",
            "description": "All cards",
            "size": 2400000000,
            "download_uri": "https://data.scryfall.io/all-cards/all-cards-20250109.json",
            "content_type": "application/json",
            "content_encoding": "gzip",
        },
        {
            "object": "bulk_data",
            "id": "def456",
            "type": "oracle_cards",
            "updated_at": "2025-01-09T12:00:00.000+00:00",
            "uri": "https://api.scryfall.com/bulk-data/def456",
            "name": "Oracle Cards",
            "description": "Oracle cards",
            "size": 160000000,
            "download_uri": "https://data.scryfall.io/oracle-cards/oracle-cards-20250109.json",
            "content_type": "application/json",
            "content_encoding": "gzip",
        },
    ],
}


class TestDataManagerCatalog:
    """Test fetching bulk data catalog."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_catalog(self):
        """Should fetch bulk data catalog from Scryfall."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                catalog = await manager.fetch_catalog()

                assert "data" in catalog
                assert len(catalog["data"]) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_all_cards_info(self):
        """Should get info for all_cards bulk data type."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                info = await manager.get_bulk_data_info("all_cards")

                assert info["type"] == "all_cards"
                assert "download_uri" in info
                assert "updated_at" in info


class TestDataManagerUrlValidation:
    """Test URL validation for security."""

    def test_validate_scryfall_url(self):
        """Should accept valid Scryfall URLs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            # Valid URLs
            assert manager.is_valid_download_url("https://data.scryfall.io/all-cards/file.json")
            assert manager.is_valid_download_url("https://api.scryfall.com/bulk-data/abc")

    def test_reject_non_scryfall_url(self):
        """Should reject non-Scryfall URLs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            # Invalid URLs
            assert not manager.is_valid_download_url("https://evil.com/malware.json")
            assert not manager.is_valid_download_url("https://scryfall.evil.com/file.json")
            assert not manager.is_valid_download_url("http://data.scryfall.io/file.json")  # HTTP

    def test_reject_malformed_url(self):
        """Should reject malformed URLs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            assert not manager.is_valid_download_url("")
            assert not manager.is_valid_download_url("not-a-url")
            assert not manager.is_valid_download_url("file:///etc/passwd")

    @pytest.mark.asyncio
    @respx.mock
    async def test_redirect_to_invalid_domain_rejected(self):
        """Should reject redirects to non-allowed domains."""
        # Set up a redirect to an evil domain
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "https://evil.com/malware.json"}
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                with pytest.raises(ValueError) as exc_info:
                    await manager.fetch_catalog()

                assert "non-allowed domain" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @respx.mock
    async def test_redirect_to_valid_domain_allowed(self):
        """Should follow redirects to allowed Scryfall domains."""
        # Set up a redirect to another valid Scryfall domain
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "https://data.scryfall.io/catalog.json"}
            )
        )
        respx.get("https://data.scryfall.io/catalog.json").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                catalog = await manager.fetch_catalog()

                assert "data" in catalog


class TestDataManagerDownload:
    """Test bulk data downloading."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_bulk_data(self):
        """Should download bulk data file."""
        # Mock catalog
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        # Mock download - return sample card data
        sample_cards = [
            {"id": "123", "name": "Lightning Bolt", "cmc": 1},
            {"id": "456", "name": "Counterspell", "cmc": 2},
        ]
        respx.get("https://data.scryfall.io/all-cards/all-cards-20250109.json").mock(
            return_value=httpx.Response(
                200,
                content=json.dumps(sample_cards).encode(),
                headers={"Content-Length": str(len(json.dumps(sample_cards).encode()))},
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                file_path = await manager.download_bulk_data("all_cards")

                assert file_path.exists()
                with open(file_path) as f:
                    data = json.load(f)
                assert len(data) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_with_progress(self):
        """Should call progress callback during download."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        respx.get("https://data.scryfall.io/all-cards/all-cards-20250109.json").mock(
            return_value=httpx.Response(
                200,
                content=sample_data,
                headers={"Content-Length": str(len(sample_data))},
            )
        )

        progress_calls = []

        def progress_callback(downloaded: int, total: int):
            progress_calls.append((downloaded, total))

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                await manager.download_bulk_data("all_cards", progress_callback=progress_callback)

                # Progress should have been called
                assert len(progress_calls) >= 1


class TestAtomicDownload:
    """Test atomic download (temp-then-rename) behaviour."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_no_temp_file_after_success(self):
        """After successful download, no .tmp file should remain."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )
        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        respx.get("https://data.scryfall.io/all-cards/all-cards-20250109.json").mock(
            return_value=httpx.Response(
                200,
                content=sample_data,
                headers={"Content-Length": str(len(sample_data))},
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                file_path = await manager.download_bulk_data("all_cards")

                assert file_path.exists()
                temp_path = file_path.with_suffix(".json.tmp")
                assert not temp_path.exists()

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_cleans_temp_on_mid_stream_failure(self):
        """Mid-stream failure should clean up the partial temp file."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        # Build a mock response whose aiter_bytes yields one chunk then raises
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Length": "10000"}

        async def failing_stream(chunk_size=8192):
            yield b"partial data"
            raise httpx.ReadError("connection lost mid-stream")

        mock_response.aiter_bytes = failing_stream
        mock_response.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                # Patch only the download request — catalog fetch uses respx
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    if "all-cards" in url:
                        return mock_response
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    with pytest.raises(httpx.ReadError):
                        await manager.download_bulk_data("all_cards", max_retries=0)

                # Partial temp file should be cleaned up
                tmp_files = list(Path(tmpdir).glob("*.tmp"))
                assert tmp_files == []
                # Final path should never have been written
                json_files = list(Path(tmpdir).glob("all-cards*.json"))
                assert json_files == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_preserves_existing_file_on_failure(self):
        """A failed re-download should not corrupt a previously downloaded file."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        # Mock response that fails mid-stream
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Length": "10000"}

        async def failing_stream(chunk_size=8192):
            yield b"corrupt partial"
            raise httpx.ReadError("connection lost")

        mock_response.aiter_bytes = failing_stream
        mock_response.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-existing good file from a previous download
            existing_file = Path(tmpdir) / "all-cards-20250109.json"
            existing_file.write_text('[{"id":"good","name":"Good Card"}]')

            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    if "all-cards" in url:
                        return mock_response
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    with pytest.raises(httpx.ReadError):
                        await manager.download_bulk_data("all_cards", max_retries=0)

                # Original file should be untouched
                assert existing_file.exists()
                data = json.loads(existing_file.read_text())
                assert data[0]["name"] == "Good Card"

                # No temp file left behind
                tmp_files = list(Path(tmpdir).glob("*.tmp"))
                assert tmp_files == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_final_path_not_written_until_complete(self):
        """During download, data goes to temp path only — final path doesn't exist."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )
        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        respx.get("https://data.scryfall.io/all-cards/all-cards-20250109.json").mock(
            return_value=httpx.Response(
                200,
                content=sample_data,
                headers={"Content-Length": str(len(sample_data))},
            )
        )

        mid_download_state = {"captured": False}

        def progress_spy(downloaded: int, total: int):
            """Capture filesystem state mid-download."""
            if not mid_download_state["captured"]:
                mid_download_state["captured"] = True
                mid_download_state["final_exists"] = (
                    Path(mid_download_state["tmpdir"]) / "all-cards-20250109.json"
                ).exists()
                mid_download_state["temp_exists"] = (
                    Path(mid_download_state["tmpdir"]) / "all-cards-20250109.json.tmp"
                ).exists()

        with tempfile.TemporaryDirectory() as tmpdir:
            mid_download_state["tmpdir"] = tmpdir
            async with DataManager(Path(tmpdir)) as manager:
                await manager.download_bulk_data(
                    "all_cards", progress_callback=progress_spy
                )

                # Mid-download: temp file exists, final does not
                assert mid_download_state["temp_exists"] is True
                assert mid_download_state["final_exists"] is False


    @pytest.mark.asyncio
    @respx.mock
    async def test_download_rejects_truncated_response(self):
        """Download with Content-Length but fewer bytes should raise ReadError."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Length": "1000"}

        async def short_stream(chunk_size=8192):
            yield b"x" * 100

        mock_response.aiter_bytes = short_stream
        mock_response.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    if "all-cards" in url:
                        return mock_response
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    with pytest.raises(httpx.ReadError, match="Incomplete download"):
                        await manager.download_bulk_data("all_cards", max_retries=0)

                # No temp or final file should remain
                tmp_files = list(Path(tmpdir).glob("*.tmp"))
                assert tmp_files == []
                json_files = list(Path(tmpdir).glob("all-cards*.json"))
                assert json_files == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_accepts_missing_content_length(self):
        """Download without Content-Length header should succeed normally."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )
        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        respx.get("https://data.scryfall.io/all-cards/all-cards-20250109.json").mock(
            return_value=httpx.Response(200, content=sample_data)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                file_path = await manager.download_bulk_data("all_cards")

                assert file_path.exists()
                assert file_path.read_bytes() == sample_data


    @pytest.mark.asyncio
    @respx.mock
    async def test_download_rejects_over_delivery(self):
        """Server sending more bytes than Content-Length should raise ReadError."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Length": "50"}

        async def long_stream(chunk_size=8192):
            yield b"x" * 200

        mock_response.aiter_bytes = long_stream
        mock_response.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    if "all-cards" in url:
                        return mock_response
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    with pytest.raises(httpx.ReadError, match="Incomplete download"):
                        await manager.download_bulk_data("all_cards", max_retries=0)

                # No files should remain
                tmp_files = list(Path(tmpdir).glob("*.tmp"))
                assert tmp_files == []
                json_files = list(Path(tmpdir).glob("all-cards*.json"))
                assert json_files == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_download_accepts_content_length_zero(self):
        """Explicit Content-Length: 0 should skip size check (treated as missing)."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"Content-Length": "0"}

        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()

        async def normal_stream(chunk_size=8192):
            yield sample_data

        mock_response.aiter_bytes = normal_stream
        mock_response.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    if "all-cards" in url:
                        return mock_response
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    file_path = await manager.download_bulk_data("all_cards")

                    assert file_path.exists()
                    assert file_path.read_bytes() == sample_data

    @pytest.mark.asyncio
    @respx.mock
    async def test_truncated_download_retries_and_succeeds(self):
        """Truncated download should be retried and succeed on next attempt."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        call_count = 0

        def make_mock_response(truncated: bool):
            mock = MagicMock()
            mock.raise_for_status = MagicMock()
            mock.aclose = AsyncMock()
            if truncated:
                mock.headers = {"Content-Length": "1000"}

                async def short_stream(chunk_size=8192):
                    yield b"x" * 100

                mock.aiter_bytes = short_stream
            else:
                mock.headers = {"Content-Length": str(len(sample_data))}

                async def full_stream(chunk_size=8192):
                    yield sample_data

                mock.aiter_bytes = full_stream
            return mock

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    nonlocal call_count
                    if "all-cards" in url:
                        call_count += 1
                        # First attempt truncated, second succeeds
                        return make_mock_response(truncated=(call_count == 1))
                    return await original_validated_get(url, **kwargs)

                with patch.object(manager, "_validated_get", side_effect=patched_get):
                    file_path = await manager.download_bulk_data(
                        "all_cards", max_retries=1
                    )

                    assert file_path.exists()
                    assert file_path.read_bytes() == sample_data
                    assert call_count == 2


class TestDataManagerCache:
    """Test cache freshness checking."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_check_cache_fresh(self):
        """Should detect fresh cache."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a recent metadata file
            metadata = {
                "type": "all_cards",
                "downloaded_at": datetime.now(UTC).isoformat(),
                "updated_at": "2025-01-09T12:00:00.000+00:00",
                "card_count": 100,
            }
            metadata_path = Path(tmpdir) / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                is_stale = await manager.is_cache_stale()
                # Cache should be fresh if updated_at matches
                assert not is_stale

    @pytest.mark.asyncio
    @respx.mock
    async def test_check_cache_stale(self):
        """Should detect stale cache."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an old metadata file
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",  # Old
                "card_count": 100,
            }
            metadata_path = Path(tmpdir) / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                is_stale = await manager.is_cache_stale()
                # Cache should be stale since server has newer data
                assert is_stale

    @pytest.mark.asyncio
    async def test_no_cache_is_stale(self):
        """Should report stale if no cache exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                is_stale = await manager.is_cache_stale()
                assert is_stale

    @pytest.mark.asyncio
    @respx.mock
    async def test_cache_stale_missing_type_defaults_to_oracle_cards(self):
        """Metadata without 'type' key should default to oracle_cards."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Metadata with NO type key — simulates older version
            metadata = {
                "downloaded_at": datetime.now(UTC).isoformat(),
                "updated_at": "2025-01-09T12:00:00.000+00:00",
                "card_count": 100,
            }
            with open(Path(tmpdir) / "metadata.json", "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                with patch.object(
                    manager, "get_bulk_data_info", wraps=manager.get_bulk_data_info
                ) as spy:
                    await manager.is_cache_stale()
                    spy.assert_called_once_with("oracle_cards")


class TestDataManagerPathSecurity:
    """Test path traversal prevention."""

    def test_reject_path_traversal(self):
        """Should reject path traversal attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            # These should all be rejected
            assert not manager.is_safe_filename("../etc/passwd")
            assert not manager.is_safe_filename("/etc/passwd")
            assert not manager.is_safe_filename("..\\windows\\system32")
            assert not manager.is_safe_filename("foo/../../../etc/passwd")

    def test_accept_safe_filename(self):
        """Should accept safe filenames."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            assert manager.is_safe_filename("all-cards-20250109.json")
            assert manager.is_safe_filename("oracle_cards.json")
            assert manager.is_safe_filename("cards.db")


class TestDataManagerStatus:
    """Test data status reporting."""

    @pytest.mark.asyncio
    async def test_get_status_no_data(self):
        """Should report no data status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                status = await manager.get_status()

                assert isinstance(status, DataStatus)
                assert status.card_count == 0
                assert status.last_updated is None
                assert status.is_stale

    @pytest.mark.asyncio
    async def test_get_status_with_data(self):
        """Should report status with data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create metadata
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-09T12:00:00+00:00",
                "updated_at": "2025-01-09T12:00:00+00:00",
                "card_count": 50000,
            }
            with open(Path(tmpdir) / "metadata.json", "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                status = await manager.get_status()

                assert status.card_count == 50000
                assert status.last_updated is not None

    @pytest.mark.asyncio
    async def test_get_status_default_skips_update_check(self):
        """get_status must not hit the network unless check_updates=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-09T12:00:00+00:00",
                "updated_at": "2025-01-09T12:00:00+00:00",
                "card_count": 50000,
            }
            with open(Path(tmpdir) / "metadata.json", "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                with patch.object(manager, "get_bulk_data_info") as spy:
                    status = await manager.get_status()

                    spy.assert_not_called()
                    # Staleness is unknown without the server comparison
                    assert status.is_stale is None

    @pytest.mark.asyncio
    async def test_get_status_no_data_is_stale_without_network(self):
        """A missing cache is definitively stale — no network call needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                with patch.object(manager, "get_bulk_data_info") as spy:
                    status = await manager.get_status()

                    spy.assert_not_called()
                    assert status.is_stale is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_status_check_updates_compares_server(self):
        """check_updates=True should perform the real staleness comparison."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",  # Old
                "card_count": 100,
            }
            with open(Path(tmpdir) / "metadata.json", "w") as f:
                json.dump(metadata, f)

            async with DataManager(Path(tmpdir)) as manager:
                status = await manager.get_status(check_updates=True)

                assert status.is_stale is True


class TestRetryJitter:
    """Test that retry backoff includes jitter."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_delay_includes_jitter(self):
        """Sleep delay should include jitter from random.uniform."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        # First attempt fails, second succeeds
        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        call_count = 0

        mock_response_fail = MagicMock()
        mock_response_fail.raise_for_status = MagicMock()
        mock_response_fail.headers = {"Content-Length": "1000"}

        async def short_stream(chunk_size=8192):
            yield b"x" * 100

        mock_response_fail.aiter_bytes = short_stream
        mock_response_fail.aclose = AsyncMock()

        mock_response_ok = MagicMock()
        mock_response_ok.raise_for_status = MagicMock()
        mock_response_ok.headers = {"Content-Length": str(len(sample_data))}

        async def full_stream(chunk_size=8192):
            yield sample_data

        mock_response_ok.aiter_bytes = full_stream
        mock_response_ok.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    nonlocal call_count
                    if "all-cards" in url:
                        call_count += 1
                        if call_count == 1:
                            return mock_response_fail
                        return mock_response_ok
                    return await original_validated_get(url, **kwargs)

                sleep_values = []

                async def mock_sleep(delay):
                    sleep_values.append(delay)

                with patch.object(manager, "_validated_get", side_effect=patched_get), \
                     patch("scryfall_local.data_manager.random.uniform", return_value=0.75) as mock_uniform, \
                     patch("asyncio.sleep", side_effect=mock_sleep):
                    await manager.download_bulk_data("all_cards", max_retries=1)

                # First retry: base_delay=1, jitter=0.75, total=1.75
                assert len(sleep_values) == 1
                assert sleep_values[0] == pytest.approx(1.75)
                # Jitter range should be [0, base_delay]
                mock_uniform.assert_called_once_with(0, 1)

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_jitter_increases_with_attempt(self):
        """Later retries should have larger base delays with jitter."""
        respx.get("https://api.scryfall.com/bulk-data").mock(
            return_value=httpx.Response(200, json=SAMPLE_CATALOG)
        )

        sample_data = json.dumps([{"id": "123", "name": "Test"}]).encode()
        call_count = 0

        def make_fail_response():
            mock = MagicMock()
            mock.raise_for_status = MagicMock()
            mock.headers = {"Content-Length": "1000"}

            async def short_stream(chunk_size=8192):
                yield b"x" * 100

            mock.aiter_bytes = short_stream
            mock.aclose = AsyncMock()
            return mock

        mock_response_ok = MagicMock()
        mock_response_ok.raise_for_status = MagicMock()
        mock_response_ok.headers = {"Content-Length": str(len(sample_data))}

        async def full_stream(chunk_size=8192):
            yield sample_data

        mock_response_ok.aiter_bytes = full_stream
        mock_response_ok.aclose = AsyncMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            async with DataManager(Path(tmpdir)) as manager:
                original_validated_get = manager._validated_get

                async def patched_get(url, **kwargs):
                    nonlocal call_count
                    if "all-cards" in url:
                        call_count += 1
                        if call_count <= 2:
                            return make_fail_response()
                        return mock_response_ok
                    return await original_validated_get(url, **kwargs)

                sleep_values = []

                async def mock_sleep(delay):
                    sleep_values.append(delay)

                # random.uniform returns 0.5 each time
                with patch.object(manager, "_validated_get", side_effect=patched_get), \
                     patch("scryfall_local.data_manager.random.uniform", return_value=0.5) as mock_uniform, \
                     patch("asyncio.sleep", side_effect=mock_sleep):
                    await manager.download_bulk_data("all_cards", max_retries=2)

                # Attempt 1 retry: base=1, jitter=0.5 → 1.5
                # Attempt 2 retry: base=2, jitter=0.5 → 2.5
                assert len(sleep_values) == 2
                assert sleep_values[0] == pytest.approx(1.5)
                assert sleep_values[1] == pytest.approx(2.5)
                # Jitter range should scale with base_delay
                from unittest.mock import call
                assert mock_uniform.call_args_list == [call(0, 1), call(0, 2)]


class TestGetCachedDataType:
    """Test reading the cached bulk data type from metadata."""

    def test_defaults_to_oracle_cards_without_metadata(self):
        """Should default to oracle_cards when no metadata exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))
            assert manager.get_cached_data_type() == "oracle_cards"

    def test_reads_type_from_metadata(self):
        """Should return the data type recorded in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))
            (Path(tmpdir) / "metadata.json").write_text('{"type": "all_cards"}')
            assert manager.get_cached_data_type() == "all_cards"
