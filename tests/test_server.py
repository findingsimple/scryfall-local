"""Tests for MCP server - TDD approach."""

import json
import pytest
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

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
    async def test_search_cards_with_offset(self, sample_cards: list[dict[str, Any]]):
        """Should support pagination with offset parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Get first page
                page1 = await server.call_tool(
                    "search_cards",
                    {"query": "", "limit": 2, "offset": 0},
                )
                # Get second page
                page2 = await server.call_tool(
                    "search_cards",
                    {"query": "", "limit": 2, "offset": 2},
                )

                assert "offset" in page1
                assert page1["offset"] == 0
                assert page2["offset"] == 2

                # Check no overlap between pages
                if len(page1["cards"]) > 0 and len(page2["cards"]) > 0:
                    page1_ids = {c["id"] for c in page1["cards"]}
                    page2_ids = {c["id"] for c in page2["cards"]}
                    assert len(page1_ids & page2_ids) == 0

    @pytest.mark.asyncio
    async def test_search_cards_total_count_is_actual_total(self, sample_cards: list[dict[str, Any]]):
        """total_count should be actual total matches, not page size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Request only 2 cards
                result = await server.call_tool(
                    "search_cards",
                    {"query": "", "limit": 2},
                )

                # total_count should be total cards, not 2
                assert result["total_count"] == len(sample_cards)
                assert len(result["cards"]) == 2
                assert result["total_count"] > len(result["cards"])

    @pytest.mark.asyncio
    async def test_search_cards_error_handling(self, sample_cards: list[dict[str, Any]]):
        """Should return error for invalid queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "search_cards",
                    {"query": "c:"},  # Invalid syntax - missing color value
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

    @pytest.mark.asyncio
    async def test_get_card_both_name_and_id_error(self, sample_cards: list[dict[str, Any]]):
        """Should error when both name and id are provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_card",
                    {"name": "Lightning Bolt", "id": "some-id"},
                )

                assert "error" in result
                assert "not both" in result["error"]


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

    @pytest.mark.asyncio
    async def test_get_cards_batch_truncation(self, sample_cards: list[dict[str, Any]]):
        """Should indicate when input is truncated due to batch limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Request more than 50 cards (the batch limit)
                names = [f"Card {i}" for i in range(60)]

                result = await server.call_tool(
                    "get_cards_batch",
                    {"names": names},
                )

                assert result.get("truncated") is True
                assert result.get("truncated_count") == 10

    @pytest.mark.asyncio
    async def test_get_cards_batch_no_truncation(self, sample_cards: list[dict[str, Any]]):
        """Should not include truncated field when under limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                result = await server.call_tool(
                    "get_cards_batch",
                    {"names": ["Lightning Bolt"]},
                )

                assert "truncated" not in result


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
                    {"query": "c:"},  # Invalid syntax - missing color value
                )

                assert "error" in result
                assert "hint" in result
                # Should include supported syntax for Claude
                assert "supported_syntax" in result or "hint" in result


class TestServerLowLevel:
    """Test low-level MCP server functionality."""

    def test_create_server(self):
        """Should create MCP server instance and return ScryfallServer for cleanup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server, scryfall = create_server(Path(tmpdir))
            assert server is not None
            assert scryfall is not None
            # Clean up
            scryfall.close()

    def test_server_name(self):
        """Server should have correct name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                assert "scryfall" in server.name.lower()


class TestServerBackgroundRefresh:
    """Test background refresh task handling."""

    @pytest.mark.asyncio
    async def test_refresh_in_progress_returns_status(self, sample_cards: list[dict[str, Any]]):
        """Should return status when refresh already in progress."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Simulate a refresh in progress with a real-ish task mock
                server._refresh_status = "downloading"
                mock_task = MagicMock()
                mock_task.done.return_value = False
                server._refresh_task = mock_task

                result = await server.call_tool("refresh_data", {})

                assert "already in progress" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_refresh_completed_status_resets(self, sample_cards: list[dict[str, Any]]):
        """Should reset status and report completion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Simulate completed refresh
                server._refresh_status = "completed"
                server._refresh_task = None

                result = await server.call_tool("refresh_data", {})

                assert "completed" in result.get("message", "").lower()
                assert server._refresh_status == "idle"

    @pytest.mark.asyncio
    async def test_refresh_error_status_resets(self, sample_cards: list[dict[str, Any]]):
        """Should reset status and report error from previous refresh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Simulate failed refresh
                server._refresh_status = "error: Network timeout"
                server._refresh_task = None

                result = await server.call_tool("refresh_data", {})

                assert "error" in result.get("message", "").lower()
                assert server._refresh_status == "idle"

    @pytest.mark.asyncio
    async def test_server_cleanup_cancels_refresh_task(self, sample_cards: list[dict[str, Any]]):
        """Server cleanup should cancel any running refresh task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            server = ScryfallServer(Path(tmpdir))
            server._init_db(sample_cards)

            # Create a mock task that simulates a running async task
            cancelled = False

            async def mock_coro():
                nonlocal cancelled
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    cancelled = True
                    raise

            task = asyncio.create_task(mock_coro())
            server._refresh_task = task

            # Cleanup the server (should cancel the task)
            await server.cleanup()

            # Task should be cancelled and set to None
            assert server._refresh_task is None
            assert cancelled or task.cancelled()

    @pytest.mark.asyncio
    async def test_data_status_includes_refresh_status(self, sample_cards: list[dict[str, Any]]):
        """data_status should include refresh_status when not idle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Set a non-idle status
                server._refresh_status = "downloading"

                result = await server.call_tool("data_status", {})

                assert result.get("refresh_status") == "downloading"

    @pytest.mark.asyncio
    async def test_data_status_excludes_idle_refresh_status(self, sample_cards: list[dict[str, Any]]):
        """data_status should not include refresh_status when idle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with ScryfallServer(Path(tmpdir)) as server:
                server._init_db(sample_cards)

                # Ensure idle status
                server._refresh_status = "idle"

                result = await server.call_tool("data_status", {})

                assert "refresh_status" not in result
