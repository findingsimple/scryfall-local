"""Data manager for downloading and caching Scryfall bulk data.

Handles downloading, caching, and freshness checking of Scryfall bulk data.
Implements security measures for URL validation and path traversal prevention.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


# Allowed domains for downloading bulk data
ALLOWED_DOMAINS = [
    "api.scryfall.com",
    "data.scryfall.io",
]

# API endpoints
BULK_DATA_ENDPOINT = "https://api.scryfall.com/bulk-data"


@dataclass
class DataStatus:
    """Status of the local data cache."""

    last_updated: datetime | None
    card_count: int
    version: str | None
    is_stale: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "card_count": self.card_count,
            "version": self.version,
            "stale": self.is_stale,
        }


class DataManager:
    """Manages downloading and caching of Scryfall bulk data."""

    def __init__(self, data_dir: Path):
        """Initialize data manager.

        Args:
            data_dir: Directory for storing downloaded data
        """
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._metadata_path = data_dir / "metadata.json"
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, read=300.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def __aenter__(self) -> "DataManager":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close HTTP client."""
        await self.close()

    def is_valid_download_url(self, url: str) -> bool:
        """Validate that URL is from allowed Scryfall domains.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid and allowed
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        # Must be HTTPS
        if parsed.scheme != "https":
            return False

        # Must be from allowed domain
        if parsed.netloc not in ALLOWED_DOMAINS:
            return False

        return True

    def is_safe_filename(self, filename: str) -> bool:
        """Check if filename is safe (no path traversal).

        Args:
            filename: Filename to check

        Returns:
            True if filename is safe
        """
        if not filename:
            return False

        # Check for path traversal patterns
        if ".." in filename:
            return False

        if filename.startswith("/") or filename.startswith("\\"):
            return False

        # Only allow alphanumeric, dash, underscore, dot
        if not re.match(r"^[a-zA-Z0-9_.-]+$", filename):
            return False

        return True

    async def fetch_catalog(self) -> dict[str, Any]:
        """Fetch bulk data catalog from Scryfall.

        Returns:
            Catalog dictionary with available bulk data types
        """
        client = await self._get_client()
        response = await client.get(BULK_DATA_ENDPOINT)
        response.raise_for_status()
        return response.json()

    async def get_bulk_data_info(self, data_type: str) -> dict[str, Any] | None:
        """Get info for specific bulk data type.

        Args:
            data_type: Type of bulk data (e.g., "all_cards", "oracle_cards")

        Returns:
            Bulk data info dictionary or None if not found
        """
        catalog = await self.fetch_catalog()

        for item in catalog.get("data", []):
            if item.get("type") == data_type:
                return item

        return None

    async def download_bulk_data(
        self,
        data_type: str = "all_cards",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download bulk data file.

        Args:
            data_type: Type of bulk data to download
            progress_callback: Optional callback for progress updates (downloaded, total)

        Returns:
            Path to downloaded file
        """
        # Get download info
        info = await self.get_bulk_data_info(data_type)
        if not info:
            raise ValueError(f"Unknown bulk data type: {data_type}")

        download_url = info.get("download_uri")
        if not download_url or not self.is_valid_download_url(download_url):
            raise ValueError(f"Invalid download URL: {download_url}")

        # Extract filename from URL
        parsed = urlparse(download_url)
        filename = parsed.path.split("/")[-1]

        if not self.is_safe_filename(filename):
            # Use a safe default
            filename = f"{data_type}.json"

        output_path = self.data_dir / filename

        # Download file
        client = await self._get_client()

        async with client.stream("GET", download_url) as response:
            response.raise_for_status()

            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0

            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback:
                        progress_callback(downloaded, total_size)

        # Save metadata
        metadata = {
            "type": data_type,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": info.get("updated_at"),
            "card_count": 0,  # Will be updated after import
            "filename": filename,
        }

        with open(self._metadata_path, "w") as f:
            json.dump(metadata, f)

        return output_path

    def _load_metadata(self) -> dict[str, Any] | None:
        """Load metadata from file."""
        if not self._metadata_path.exists():
            return None

        try:
            with open(self._metadata_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    async def is_cache_stale(self) -> bool:
        """Check if local cache is stale compared to server.

        Returns:
            True if cache is stale or doesn't exist
        """
        metadata = self._load_metadata()

        if not metadata:
            return True

        local_updated = metadata.get("updated_at")
        if not local_updated:
            return True

        # Fetch server info
        try:
            info = await self.get_bulk_data_info(metadata.get("type", "all_cards"))
            if not info:
                return True

            server_updated = info.get("updated_at")
            if not server_updated:
                return True

            # Compare timestamps
            return local_updated != server_updated

        except Exception:
            # If we can't check, assume stale
            return True

    async def get_status(self) -> DataStatus:
        """Get status of local data cache.

        Returns:
            DataStatus with cache information
        """
        metadata = self._load_metadata()

        if not metadata:
            return DataStatus(
                last_updated=None,
                card_count=0,
                version=None,
                is_stale=True,
            )

        # Parse last updated time
        last_updated = None
        downloaded_at = metadata.get("downloaded_at")
        if downloaded_at:
            try:
                last_updated = datetime.fromisoformat(downloaded_at)
            except ValueError:
                pass

        # Check staleness
        try:
            is_stale = await self.is_cache_stale()
        except Exception:
            is_stale = True

        return DataStatus(
            last_updated=last_updated,
            card_count=metadata.get("card_count", 0),
            version=metadata.get("updated_at"),
            is_stale=is_stale,
        )

    def update_card_count(self, count: int) -> None:
        """Update card count in metadata.

        Args:
            count: Number of cards imported
        """
        metadata = self._load_metadata() or {}
        metadata["card_count"] = count

        with open(self._metadata_path, "w") as f:
            json.dump(metadata, f)
