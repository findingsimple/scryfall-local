"""Tests for data manager (bulk data download) - TDD approach."""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

from src.data_manager import DataManager, DataStatus


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
            manager = DataManager(Path(tmpdir))
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
            manager = DataManager(Path(tmpdir))
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
                headers={"Content-Length": "100"},
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))
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
            manager = DataManager(Path(tmpdir))
            await manager.download_bulk_data("all_cards", progress_callback=progress_callback)

            # Progress should have been called
            assert len(progress_calls) >= 1


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
            manager = DataManager(Path(tmpdir))

            # Create a recent metadata file
            metadata = {
                "type": "all_cards",
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": "2025-01-09T12:00:00.000+00:00",
                "card_count": 100,
            }
            metadata_path = Path(tmpdir) / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(metadata, f)

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
            manager = DataManager(Path(tmpdir))

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

            is_stale = await manager.is_cache_stale()
            # Cache should be stale since server has newer data
            assert is_stale

    @pytest.mark.asyncio
    async def test_no_cache_is_stale(self):
        """Should report stale if no cache exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            is_stale = await manager.is_cache_stale()
            assert is_stale


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
            manager = DataManager(Path(tmpdir))
            status = await manager.get_status()

            assert isinstance(status, DataStatus)
            assert status.card_count == 0
            assert status.last_updated is None
            assert status.is_stale

    @pytest.mark.asyncio
    async def test_get_status_with_data(self):
        """Should report status with data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DataManager(Path(tmpdir))

            # Create metadata
            metadata = {
                "type": "all_cards",
                "downloaded_at": "2025-01-09T12:00:00+00:00",
                "updated_at": "2025-01-09T12:00:00+00:00",
                "card_count": 50000,
            }
            with open(Path(tmpdir) / "metadata.json", "w") as f:
                json.dump(metadata, f)

            status = await manager.get_status()

            assert status.card_count == 50000
            assert status.last_updated is not None
