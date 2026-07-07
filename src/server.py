"""MCP Server for local Scryfall card data.

Provides tools for querying Magic: The Gathering cards from locally cached
Scryfall bulk data. Uses the low-level MCP Server class for educational purposes.
"""

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from src import __version__
from src.card_store import CardStore
from src.data_manager import DataManager
from src.import_utils import import_to_temp_and_swap
from src.query_parser import SYNTAX_SUMMARY, QueryError, QueryParser

logger = logging.getLogger(__name__)

# Server name constant - used in multiple places
SERVER_NAME = "scryfall-local"


@dataclass
class Tool:
    """Tool definition for MCP."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class ScryfallServer:
    """Scryfall Local MCP Server.

    Provides tools for searching and retrieving Magic: The Gathering cards
    from locally cached Scryfall data.
    """

    name = SERVER_NAME
    version = __version__

    def __init__(self, data_dir: Path):
        """Initialize server.

        Args:
            data_dir: Directory for storing card data
        """
        self.data_dir = data_dir
        self.db_path = data_dir / "cards.db"

        self._store: CardStore | None = None
        self._parser = QueryParser()
        self._data_manager = DataManager(data_dir)
        self._refresh_task: asyncio.Task | None = None
        self._refresh_status: str = "idle"
        self._refresh_lock = asyncio.Lock()  # Serializes store access during swap
        # Once the DB is seen non-empty it stays that way (refresh only adds
        # data), so the empty-DB check short-circuits after the first hit.
        self._db_known_nonempty = False

    def _get_store(self) -> CardStore:
        """Get or create card store."""
        if self._store is None:
            self._store = CardStore(self.db_path)
        return self._store

    def close(self) -> None:
        """Close server resources synchronously."""
        if self._store is not None:
            self._store.close()
            self._store = None

    async def cleanup(self) -> None:
        """Clean up all server resources including async tasks.

        This method should be called on shutdown to ensure:
        - Background refresh tasks are cancelled
        - Database connections are closed
        - Data manager resources are released
        """
        # Cancel any background refresh task
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
            self._refresh_task = None

        # Close database connection
        self.close()

        # Close data manager
        await self._data_manager.close()

    def __enter__(self) -> "ScryfallServer":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and close resources."""
        self.close()

    async def __aenter__(self) -> "ScryfallServer":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and clean up resources."""
        await self.cleanup()

    def _init_db(self, cards: list[dict[str, Any]]) -> None:
        """Initialize database with cards (for testing).

        Args:
            cards: List of card data dictionaries
        """
        store = self._get_store()
        store.insert_cards(cards)

    def list_tools(self) -> list[Tool]:
        """List available tools.

        Returns:
            List of tool definitions
        """
        return [
            Tool(
                name="search_cards",
                description="Search for Magic: The Gathering cards using Scryfall syntax. "
                "Results are compact (name, cost, type, text, colors, set, rarity); "
                f"use get_card or verbose=true for full detail. {SYNTAX_SUMMARY}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Scryfall search query "
                            "(e.g., 'c:blue t:instant cmc<=2')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return (default 20, max 100)",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of results to skip for pagination (default 0)",
                            "default": 0,
                            "minimum": 0,
                        },
                        "verbose": {
                            "type": "boolean",
                            "description": "Return full card objects (legalities, prices, "
                            "image URIs, ...) instead of the compact projection "
                            "(default false)",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_card",
                description="Get a single Magic: The Gathering card by name or Scryfall ID. "
                "Name matching is case-insensitive; for double-faced cards the front-face "
                "name is enough (e.g. 'Delver of Secrets').",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Card name, case-insensitive (e.g., 'Lightning Bolt'). "
                            "Front-face name works for double-faced cards.",
                        },
                        "id": {
                            "type": "string",
                            "description": "Scryfall card ID",
                        },
                    },
                },
            ),
            Tool(
                name="get_cards_batch",
                description="Get multiple Magic: The Gathering cards by name or ID in a "
                "single call. More efficient than multiple get_card calls. "
                "Limited to 50 cards per request.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of card names, case-insensitive; front-face "
                            "names work for double-faced cards (max 50 combined with ids)",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of Scryfall card IDs (max 50 combined with names)",
                        },
                    },
                },
            ),
            Tool(
                name="random_card",
                description="Get a random Magic: The Gathering card, optionally filtered by query.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional filter query (e.g., 't:dragon')",
                        },
                    },
                },
            ),
            Tool(
                name="data_status",
                description="Check the status of the local card data cache. "
                "Returns card count and last updated time. Pass check_updates=true "
                "to also compare against Scryfall for staleness (network call).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "check_updates": {
                            "type": "boolean",
                            "description": "Compare against the Scryfall server to "
                            "report staleness (default false — local status only)",
                            "default": False,
                        },
                    },
                },
            ),
            Tool(
                name="refresh_data",
                description="Trigger a refresh of the local card data cache. "
                "Downloads latest data from Scryfall if updates are available.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result dictionary
        """
        if name == "search_cards":
            return await self._search_cards(arguments)
        elif name == "get_card":
            return await self._get_card(arguments)
        elif name == "get_cards_batch":
            return await self._get_cards_batch(arguments)
        elif name == "random_card":
            return await self._random_card(arguments)
        elif name == "data_status":
            return await self._data_status(arguments)
        elif name == "refresh_data":
            return await self._refresh_data(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    # Fields included in compact (default) search results. Everything else
    # (legalities, image_uris, prices, flavor_text, ...) is bulk the agent
    # rarely needs per-result — it lives behind get_card or verbose=true.
    COMPACT_FIELDS = (
        "id",
        "name",
        "mana_cost",
        "cmc",
        "type_line",
        "oracle_text",
        "power",
        "toughness",
        "loyalty",
        "colors",
        "set",
        "rarity",
    )

    def _empty_db_warning(self, store: CardStore) -> str | None:
        """Warn when the card database is empty.

        Without this, an empty DB makes every lookup return "not found" and
        the agent concludes the card doesn't exist.
        """
        if self._db_known_nonempty:
            return None
        if store.get_card_count() > 0:
            self._db_known_nonempty = True
            return None
        return (
            "The card database is empty — no card data has been imported, so "
            "every lookup will come back empty. Run the refresh_data tool, or "
            "from the command line: `uv run python -m src.cli download` then "
            "`uv run python -m src.cli import`."
        )

    def _compact_card(self, card: dict[str, Any]) -> dict[str, Any]:
        """Project a card down to COMPACT_FIELDS, dropping null values."""
        return {
            field: card[field]
            for field in self.COMPACT_FIELDS
            if card.get(field) is not None
        }

    async def _search_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Search for cards.

        Args:
            arguments: {"query": str, "limit": int, "offset": int, "verbose": bool}

        Returns:
            {"cards": [...], "total_count": int, "query_time_ms": int, "offset": int}
        """
        query = arguments.get("query", "")
        limit = max(1, min(arguments.get("limit", 20), 100))
        offset = max(0, arguments.get("offset", 0))
        verbose = bool(arguments.get("verbose", False))

        start_time = time.time()

        try:
            parsed = self._parser.parse(query)
        except QueryError as e:
            return {
                "error": e.message,
                "hint": e.hint,
                "supported_syntax": e.supported_syntax,
            }

        # Wait for any ongoing refresh to complete
        async with self._refresh_lock:
            store = self._get_store()
            cards = store.execute_query(parsed, limit=limit, offset=offset)
            total_count = store.count_matches(parsed)
            warning = self._empty_db_warning(store)

        if not verbose:
            cards = [self._compact_card(card) for card in cards]

        elapsed_ms = int((time.time() - start_time) * 1000)

        result: dict[str, Any] = {
            "cards": cards,
            "total_count": total_count,
            "query_time_ms": elapsed_ms,
            "offset": offset,
        }
        if warning:
            result["warning"] = warning
        return result

    async def _get_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get a single card.

        Args:
            arguments: {"name": str} or {"id": str} (not both)

        Returns:
            Card dictionary or error
        """
        name = arguments.get("name")
        card_id = arguments.get("id")

        if name and card_id:
            return {"error": "Provide either 'name' or 'id', not both"}
        elif not name and not card_id:
            return {"error": "Either 'name' or 'id' must be provided"}

        # Wait for any ongoing refresh to complete
        async with self._refresh_lock:
            store = self._get_store()
            card = store.get_card_by_name(name) if name else store.get_card_by_id(card_id)
            warning = self._empty_db_warning(store)

        if card:
            return card
        else:
            result = {
                "error": "Card not found",
                "hint": f"Try searching with: search_cards query=\"{name or card_id}\"",
            }
            if warning:
                result["warning"] = warning
            return result

    async def _get_cards_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get multiple cards.

        Args:
            arguments: {"names": [...]} or {"ids": [...]}

        Returns:
            {"found": [...], "not_found": [...], "truncated": bool}

        Design: Empty input (no names or ids) returns {"found": [], "not_found": []}.
        This is correct behavior - an empty query should return empty results,
        not an error. The caller can check len(found) == 0 if needed.
        """
        batch_limit = 50

        names = arguments.get("names", [])
        ids = arguments.get("ids", [])

        total_requested = len(names) + len(ids)
        truncated = total_requested > batch_limit

        found = []
        not_found = []
        remaining = batch_limit

        # Wait for any ongoing refresh to complete
        async with self._refresh_lock:
            store = self._get_store()

            # Batch lookup by name
            name_slice = names[:remaining]
            if name_slice:
                card_map = store.get_cards_by_names(name_slice)
                for name in name_slice:
                    if name in card_map:
                        found.append(card_map[name])
                    else:
                        not_found.append(name)

            remaining -= len(name_slice)

            # Batch lookup by ID
            id_slice = ids[:remaining]
            if id_slice:
                card_map = store.get_cards_by_ids(id_slice)
                for card_id in id_slice:
                    if card_id in card_map:
                        found.append(card_map[card_id])
                    else:
                        not_found.append(card_id)

            warning = self._empty_db_warning(store)

        result: dict[str, Any] = {
            "found": found,
            "not_found": not_found,
        }
        if warning:
            result["warning"] = warning

        if truncated:
            result["truncated"] = True
            result["truncated_count"] = total_requested - batch_limit

        return result

    async def _random_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get a random card.

        Args:
            arguments: {"query": str} (optional)

        Returns:
            Card dictionary
        """
        query = arguments.get("query")

        parsed = None
        if query:
            try:
                parsed = self._parser.parse(query)
            except QueryError as e:
                return {
                    "error": e.message,
                    "hint": e.hint,
                }

        # Wait for any ongoing refresh to complete
        async with self._refresh_lock:
            store = self._get_store()
            card = store.get_random_card(parsed)

        if card:
            return card
        else:
            return {"error": "No cards match the filter"}

    async def _data_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get data cache status.

        Returns:
            {"last_updated": str, "card_count": int, "stale": bool | None,
             "refresh_status": str}
        """
        check_updates = bool(arguments.get("check_updates", False))

        # Acquire lock for consistency with other methods
        async with self._refresh_lock:
            store = self._get_store()
            card_count = store.get_card_count()
        status = await self._data_manager.get_status(check_updates=check_updates)

        result = {
            "last_updated": status.last_updated.isoformat() if status.last_updated else None,
            "card_count": card_count,
            "version": status.version,
            "stale": status.is_stale,
        }
        if status.is_stale is None:
            result["stale_hint"] = (
                "Staleness not checked (avoids a network call). Pass "
                "check_updates=true to compare against Scryfall."
            )

        # Include refresh status if not idle
        if self._refresh_status != "idle":
            result["refresh_status"] = self._refresh_status

        return result

    def _import_cards_blocking(self, file_path: Path) -> tuple[int, int]:
        """Import cards from JSON file (blocking I/O, runs in thread).

        Args:
            file_path: Path to the JSON file

        Returns:
            Tuple of (cards_imported, cards_skipped)

        Raises:
            ImportError: If ijson is not installed (required for streaming JSON parsing)
        """
        return import_to_temp_and_swap(file_path, self.db_path)

    async def _do_refresh(self) -> None:
        """Perform the actual download and import (runs in background)."""
        try:
            self._refresh_status = "downloading"

            # Download the same bulk data type as the current cache, so a
            # refresh never silently replaces e.g. all_cards with oracle_cards
            data_type = self._data_manager.get_cached_data_type()
            file_path = await self._data_manager.download_bulk_data(data_type)

            self._refresh_status = "importing"

            # Import into temp DB and atomically swap into place.
            # Runs outside the lock so queries continue against the old DB.
            card_count, skipped = await asyncio.to_thread(
                self._import_cards_blocking, file_path
            )

            if skipped:
                logger.warning(
                    "Refresh skipped %d malformed cards", skipped
                )

            # Brief lock: close stale store so next query reopens the new DB
            async with self._refresh_lock:
                if self._store is not None:
                    self._store.close()
                    self._store = None

            # Update metadata with card count
            self._data_manager.update_card_count(card_count)

            self._refresh_status = "completed"

        except Exception as e:
            self._refresh_status = f"error: {str(e)}"

        finally:
            self._refresh_task = None

    async def _refresh_data(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Refresh data cache.

        Returns:
            {"status": str, "message": str}
        """
        try:
            # Check if already refreshing
            if self._refresh_task is not None and not self._refresh_task.done():
                return {
                    "status": "in_progress",
                    "message": f"Data refresh already in progress: {self._refresh_status}",
                }

            # Check if refresh completed recently
            if self._refresh_status == "completed":
                self._refresh_status = "idle"
                return {
                    "status": "completed",
                    "message": "Data refresh completed successfully",
                }

            # Check if last refresh had an error
            if self._refresh_status.startswith("error:"):
                error_msg = self._refresh_status
                self._refresh_status = "idle"
                return {
                    "status": "error",
                    "message": error_msg,
                }

            # Check if update is needed
            is_stale = await self._data_manager.is_cache_stale()

            if not is_stale:
                return {
                    "status": "already_current",
                    "message": "Data is already up to date",
                }

            # Start download in background
            self._refresh_task = asyncio.create_task(self._do_refresh())

            return {
                "status": "downloading",
                "message": "Data refresh started. This may take several minutes for the "
                "full dataset (~2.5 GB download). Use data_status to check progress.",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to refresh data: {str(e)}",
            }


def create_server(data_dir: Path) -> tuple[Server, ScryfallServer]:
    """Create MCP server instance.

    Args:
        data_dir: Directory for storing card data

    Returns:
        Tuple of (MCP Server, ScryfallServer instance for cleanup)
    """
    scryfall = ScryfallServer(data_dir)

    # Create low-level MCP server
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """Return available tools."""
        tools = scryfall.list_tools()
        return [
            types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.inputSchema,
            )
            for t in tools
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[types.TextContent]:
        """Handle tool execution."""
        result = await scryfall.call_tool(name, arguments or {})
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, default=str),
            )
        ]

    return server, scryfall


async def run_server(data_dir: Path | None = None) -> None:
    """Run the MCP server.

    Args:
        data_dir: Optional data directory (defaults to ./data relative to project root)
    """
    if data_dir is None:
        # Use absolute path relative to this file's location
        project_root = Path(__file__).parent.parent
        data_dir = project_root / "data"

    data_dir.mkdir(parents=True, exist_ok=True)

    server, scryfall = create_server(data_dir)

    try:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=SERVER_NAME,
                    server_version=__version__,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        # Ensure cleanup on shutdown
        await scryfall.cleanup()


if __name__ == "__main__":
    asyncio.run(run_server())
