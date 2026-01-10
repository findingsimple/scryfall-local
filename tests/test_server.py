"""Tests for MCP server - TDD approach."""

import json
import pytest
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from src.server import ScryfallServer, create_server


class TestServerToolListing:
    """Test tool registration and listing."""

    def test_server_has_tools(self, sample_cards: list[dict[str, Any]]):
        """Server should expose expected tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                tools = server.list_tools()
                tool_names = [t.name for t in tools]

                assert "search_cards" in tool_names
                assert "get_card" in tool_names
                assert "get_cards_batch" in tool_names
                assert "random_card" in tool_names
                assert "data_status" in tool_names
                assert "refresh_data" in tool_names

    def test_tools_have_descriptions(self, sample_cards: list[dict[str, Any]]):
        """Each tool should have a description."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                tools = server.list_tools()

                for tool in tools:
                    assert tool.description
                    assert len(tool.description) > 10

    def test_tools_have_input_schemas(self, sample_cards: list[dict[str, Any]]):
        """Each tool should have an input schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                tools = server.list_tools()

                for tool in tools:
                    assert tool.inputSchema
                    assert "type" in tool.inputSchema


class TestServerSearchCards:
    """Test search_cards tool."""

    @pytest.mark.asyncio
    async def test_search_cards_basic(self, sample_cards: list[dict[str, Any]]):
        """Should search cards with basic query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool("search_cards", {"query": "c:red"})

                assert "cards" in result
                assert "total_count" in result
                assert len(result["cards"]) >= 1
                assert all("R" in c["colors"] for c in result["cards"])

    @pytest.mark.asyncio
    async def test_search_cards_complex(self, sample_cards: list[dict[str, Any]]):
        """Should handle complex queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "c:blue t:instant"},
                )

                assert "cards" in result
                for card in result["cards"]:
                    assert "U" in card["colors"]
                    assert "Instant" in card["type_line"]

    @pytest.mark.asyncio
    async def test_search_cards_with_limit(self, sample_cards: list[dict[str, Any]]):
        """Should respect limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "t:creature", "limit": 2},
                )

                assert len(result["cards"]) <= 2

    @pytest.mark.asyncio
    async def test_search_cards_error_handling(self, sample_cards: list[dict[str, Any]]):
        """Should return error for invalid queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "f:modern"},  # Unsupported syntax
                )

                assert "error" in result
                assert "hint" in result


class TestServerGetCard:
    """Test get_card tool."""

    @pytest.mark.asyncio
    async def test_get_card_by_name(self, sample_cards: list[dict[str, Any]]):
        """Should get card by exact name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_card",
                    {"name": "Lightning Bolt"},
                )

                assert "name" in result
                assert result["name"] == "Lightning Bolt"

    @pytest.mark.asyncio
    async def test_get_card_by_id(self, sample_cards: list[dict[str, Any]]):
        """Should get card by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                card_id = sample_cards[0]["id"]
                result = await server.call_tool(
                    "get_card",
                    {"id": card_id},
                )

                assert "name" in result
                assert result["id"] == card_id

    @pytest.mark.asyncio
    async def test_get_card_not_found(self, sample_cards: list[dict[str, Any]]):
        """Should handle card not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_card",
                    {"name": "Nonexistent Card"},
                )

                assert "error" in result


class TestServerGetCardsBatch:
    """Test get_cards_batch tool."""

    @pytest.mark.asyncio
    async def test_get_cards_batch_by_names(self, sample_cards: list[dict[str, Any]]):
        """Should get multiple cards by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_cards_batch",
                    {"names": ["Lightning Bolt", "Counterspell"]},
                )

                assert "found" in result
                assert "not_found" in result
                assert len(result["found"]) == 2

    @pytest.mark.asyncio
    async def test_get_cards_batch_partial_match(self, sample_cards: list[dict[str, Any]]):
        """Should report found and not found cards."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_cards_batch",
                    {"names": ["Lightning Bolt", "Nonexistent Card"]},
                )

                assert len(result["found"]) == 1
                assert len(result["not_found"]) == 1
                assert "Nonexistent Card" in result["not_found"]


class TestServerRandomCard:
    """Test random_card tool."""

    @pytest.mark.asyncio
    async def test_random_card(self, sample_cards: list[dict[str, Any]]):
        """Should return a random card."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool("random_card", {})

                assert "name" in result

    @pytest.mark.asyncio
    async def test_random_card_with_filter(self, sample_cards: list[dict[str, Any]]):
        """Should return random card matching filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "random_card",
                    {"query": "c:red"},
                )

                assert "name" in result
                assert "R" in result["colors"]


class TestServerDataStatus:
    """Test data_status tool."""

    @pytest.mark.asyncio
    async def test_data_status(self, sample_cards: list[dict[str, Any]]):
        """Should return data status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool("data_status", {})

                assert "card_count" in result
                assert "stale" in result

    @pytest.mark.asyncio
    async def test_data_status_empty(self):
        """Should handle empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                result = await server.call_tool("data_status", {})

                assert result["card_count"] == 0
                assert result["stale"] is True


class TestServerResponseFormat:
    """Test response format for agentic use."""

    @pytest.mark.asyncio
    async def test_search_includes_metadata(self, sample_cards: list[dict[str, Any]]):
        """Search results should include metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "c:red"},
                )

                # Should have metadata for Claude to understand results
                assert "total_count" in result
                assert "query_time_ms" in result or "cards" in result

    @pytest.mark.asyncio
    async def test_errors_are_structured(self, sample_cards: list[dict[str, Any]]):
        """Errors should be structured with hints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "f:modern"},  # Unsupported
                )

                assert "error" in result
                assert "hint" in result
                # Should include supported syntax for Claude
                assert "supported_syntax" in result or "hint" in result


class TestServerLowLevel:
    """Test low-level MCP server functionality."""

    def test_create_server(self):
        """Should create MCP server instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = create_server(Path(tmpdir))
            assert server is not None

    def test_server_name(self):
        """Server should have correct name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                assert "scryfall" in server.name.lower()
