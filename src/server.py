"""MCP Server for local Scryfall card data.

Provides tools for querying Magic: The Gathering cards from locally cached
Scryfall bulk data. Uses the low-level MCP Server class for educational purposes.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

from src.card_store import CardStore
from src.data_manager import DataManager
from src.query_parser import QueryParser, QueryError, SUPPORTED_SYNTAX


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

    name = "scryfall-local"
    version = "0.1.0"

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

    def _get_store(self) -> CardStore:
        """Get or create card store."""
        if self._store is None:
            self._store = CardStore(self.db_path)
        return self._store

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
                "Supports: name, colors (c:blue), mana value (cmc:3), type (t:creature), "
                "oracle text (o:flying), set (set:neo), rarity (r:mythic). "
                "Boolean operators: implicit AND, OR, - (negation).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Scryfall search query (e.g., 'c:blue t:instant cmc<=2')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return (default 20, max 100)",
                            "default": 20,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_card",
                description="Get a single Magic: The Gathering card by exact name or Scryfall ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Exact card name (e.g., 'Lightning Bolt')",
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
                description="Get multiple Magic: The Gathering cards by name or ID in a single call. "
                "More efficient than multiple get_card calls.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of exact card names",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of Scryfall card IDs",
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
                "Returns card count, last updated time, and whether data is stale.",
                inputSchema={
                    "type": "object",
                    "properties": {},
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

    async def _search_cards(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Search for cards.

        Args:
            arguments: {"query": str, "limit": int}

        Returns:
            {"cards": [...], "total_count": int, "query_time_ms": int}
        """
        query = arguments.get("query", "")
        limit = min(arguments.get("limit", 20), 100)

        start_time = time.time()

        try:
            parsed = self._parser.parse(query)
        except QueryError as e:
            return {
                "error": e.message,
                "hint": e.hint,
                "supported_syntax": e.supported_syntax,
            }

        store = self._get_store()
        cards = store.execute_query(parsed, limit=limit)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "cards": cards,
            "total_count": len(cards),
            "query_time_ms": elapsed_ms,
        }

    async def _get_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get a single card.

        Args:
            arguments: {"name": str} or {"id": str}

        Returns:
            Card dictionary or error
        """
        store = self._get_store()

        name = arguments.get("name")
        card_id = arguments.get("id")

        if name:
            card = store.get_card_by_name(name)
        elif card_id:
            card = store.get_card_by_id(card_id)
        else:
            return {"error": "Either 'name' or 'id' must be provided"}

        if card:
            return card
        else:
            return {
                "error": "Card not found",
                "hint": f"Try searching with: search_cards query=\"{name or card_id}\"",
            }

    async def _get_cards_batch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get multiple cards.

        Args:
            arguments: {"names": [...]} or {"ids": [...]}

        Returns:
            {"found": [...], "not_found": [...]}
        """
        store = self._get_store()

        names = arguments.get("names", [])
        ids = arguments.get("ids", [])

        found = []
        not_found = []

        for name in names[:50]:  # Limit to 50
            card = store.get_card_by_name(name)
            if card:
                found.append(card)
            else:
                not_found.append(name)

        for card_id in ids[:50]:
            card = store.get_card_by_id(card_id)
            if card:
                found.append(card)
            else:
                not_found.append(card_id)

        return {
            "found": found,
            "not_found": not_found,
        }

    async def _random_card(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get a random card.

        Args:
            arguments: {"query": str} (optional)

        Returns:
            Card dictionary
        """
        store = self._get_store()
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

        card = store.get_random_card(parsed)

        if card:
            return card
        else:
            return {"error": "No cards match the filter"}

    async def _data_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get data cache status.

        Returns:
            {"last_updated": str, "card_count": int, "stale": bool}
        """
        store = self._get_store()
        status = await self._data_manager.get_status()

        return {
            "last_updated": status.last_updated.isoformat() if status.last_updated else None,
            "card_count": store.get_card_count(),
            "version": status.version,
            "stale": status.is_stale,
        }

    async def _refresh_data(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Refresh data cache.

        Returns:
            {"status": str, "message": str}
        """
        try:
            is_stale = await self._data_manager.is_cache_stale()

            if not is_stale:
                return {
                    "status": "already_current",
                    "message": "Data is already up to date",
                }

            # Download new data
            return {
                "status": "downloading",
                "message": "Data refresh initiated. This may take several minutes for the full dataset.",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to refresh data: {str(e)}",
            }


def create_server(data_dir: Path) -> Server:
    """Create MCP server instance.

    Args:
        data_dir: Directory for storing card data

    Returns:
        Configured MCP Server
    """
    scryfall = ScryfallServer(data_dir)

    # Create low-level MCP server
    server = Server("scryfall-local")

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
                text=str(result) if not isinstance(result, dict) else str(result),
            )
        ]

    return server


async def run_server(data_dir: Path | None = None) -> None:
    """Run the MCP server.

    Args:
        data_dir: Optional data directory (defaults to ./data)
    """
    if data_dir is None:
        data_dir = Path("./data")

    data_dir.mkdir(parents=True, exist_ok=True)

    server = create_server(data_dir)

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="scryfall-local",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run_server())
