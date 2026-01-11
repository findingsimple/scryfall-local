"""CLI for downloading and managing Scryfall bulk data."""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Callable

import ijson

from src.data_manager import DataManager
from src.card_store import CardStore


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def print_progress_bar(downloaded: int, total: int) -> None:
    """Print a progress bar to stdout.

    Matches the Callable[[int, int], None] signature expected by
    DataManager.download_bulk_data progress_callback parameter.
    """
    bar_length = 40
    if total == 0:
        return

    percent = downloaded / total
    filled = int(bar_length * percent)
    bar = "█" * filled + "░" * (bar_length - filled)

    downloaded_str = format_size(downloaded)
    total_str = format_size(total)

    sys.stdout.write(f"\r  [{bar}] {percent*100:.1f}% ({downloaded_str} / {total_str})")
    sys.stdout.flush()


def import_cards_streaming(
    json_file: Path,
    store: CardStore,
    progress_callback: Callable[[int, int | None], None] | None = None,
) -> int:
    """Import cards from JSON using streaming parser.

    Uses ijson to parse the JSON file incrementally, reducing memory usage
    from ~2.5GB to a small fixed amount regardless of file size.

    Args:
        json_file: Path to the JSON file containing card data
        store: CardStore instance to import cards into
        progress_callback: Optional callback(imported_count, total) for progress updates.
                          total may be None if unknown.

    Returns:
        Total number of cards imported
    """
    batch_size = 1000
    batch: list[dict] = []
    card_count = 0

    with open(json_file, "rb") as f:
        # ijson.items streams through the JSON array one item at a time
        for card in ijson.items(f, "item"):
            batch.append(card)
            if len(batch) >= batch_size:
                store.insert_cards(batch)
                card_count += len(batch)
                batch = []
                if progress_callback:
                    progress_callback(card_count, None)

    # Insert remaining cards
    if batch:
        store.insert_cards(batch)
        card_count += len(batch)
        if progress_callback:
            progress_callback(card_count, None)

    return card_count


async def download_data(
    data_dir: Path, data_type: str = "all_cards", force: bool = False
) -> None:
    """Download bulk data with progress bar."""
    manager = DataManager(data_dir)

    print("Checking for updates...")

    try:
        # Check if update is needed (skip if force=True)
        if not force:
            is_stale = await manager.is_cache_stale()

            if not is_stale:
                status = await manager.get_status()
                print("Data is already up to date!")
                print(f"  Last updated: {status.last_updated}")
                print(f"  Cards: {status.card_count:,}")
                print("  Use --force to re-download anyway.")
                return

        # Get info about the download
        info = await manager.get_bulk_data_info(data_type)
        if not info:
            print(f"Error: Unknown data type '{data_type}'")
            return

        size = info.get("size", 0)
        print(f"Downloading {info.get('name', data_type)}...")
        print(f"  Size: {format_size(size)}")
        print(f"  Updated: {info.get('updated_at', 'unknown')}")
        print()

        # Download with progress
        file_path = await manager.download_bulk_data(
            data_type,
            progress_callback=print_progress_bar,
        )

        print()  # New line after progress bar
        print(f"Downloaded to: {file_path}")

        # Import into database using streaming parser
        print()
        print("Importing cards into database...")

        db_path = data_dir / "cards.db"

        def import_progress(imported: int, total: int | None) -> None:
            sys.stdout.write(f"\r  Importing... {imported:,} cards")
            sys.stdout.flush()

        with CardStore(db_path) as store:
            total_cards = import_cards_streaming(file_path, store, import_progress)

        print()
        print(f"Import complete! {total_cards:,} cards imported.")

        # Update metadata with card count
        manager.update_card_count(total_cards)

        print()
        print("Done! You can now use the MCP server.")

    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        await manager.close()


async def show_status(data_dir: Path) -> None:
    """Show current data status."""
    manager = DataManager(data_dir)

    try:
        status = await manager.get_status()

        print("Scryfall Local Data Status")
        print("-" * 40)

        if status.last_updated:
            print(f"  Last updated: {status.last_updated}")
        else:
            print("  Last updated: Never")

        print(f"  Card count:   {status.card_count:,}")
        print(f"  Version:      {status.version or 'Unknown'}")
        print(f"  Stale:        {'Yes' if status.is_stale else 'No'}")

        if status.is_stale:
            print()
            print("Run 'python -m src.cli download' to update.")

    finally:
        await manager.close()


async def import_data(data_dir: Path, json_file: Path | None = None) -> None:
    """Import cards from JSON file into database."""
    manager = DataManager(data_dir)

    # Find JSON file if not specified
    if json_file is None:
        json_files = list(data_dir.glob("*.json"))
        json_files = [f for f in json_files if f.name != "metadata.json"]

        if not json_files:
            print("Error: No JSON data file found in data directory.")
            print("Run 'python -m src.cli download' first.")
            return

        # Use most recent file
        json_file = max(json_files, key=lambda f: f.stat().st_mtime)

    if not json_file.exists():
        print(f"Error: File not found: {json_file}")
        return

    print(f"Importing from: {json_file.name}")
    print(f"  File size: {format_size(json_file.stat().st_size)}")
    print()

    # Import into database
    db_path = data_dir / "cards.db"

    # Remove old database if exists
    if db_path.exists():
        print("Removing old database...")
        db_path.unlink()

    store = CardStore(db_path)

    print("Importing cards using streaming parser...")

    def import_progress(imported: int, total: int | None) -> None:
        sys.stdout.write(f"\r  Importing... {imported:,} cards")
        sys.stdout.flush()

    total_cards = import_cards_streaming(json_file, store, import_progress)

    print()
    print()
    print(f"Import complete! {total_cards:,} cards in database.")

    # Update metadata
    manager.update_card_count(total_cards)

    store.close()
    await manager.close()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Scryfall Local - Download and manage MTG card data",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./data"),
        help="Directory for storing data (default: ./data)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download or update bulk card data",
    )
    download_parser.add_argument(
        "--type",
        choices=["all_cards", "oracle_cards", "default_cards"],
        default="all_cards",
        help="Type of bulk data to download (default: all_cards)",
    )
    download_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if data is current",
    )

    # Import command
    import_parser = subparsers.add_parser(
        "import",
        help="Import cards from downloaded JSON into database",
    )
    import_parser.add_argument(
        "--file",
        type=Path,
        help="JSON file to import (auto-detects if not specified)",
    )

    # Status command
    subparsers.add_parser(
        "status",
        help="Show current data status",
    )

    args = parser.parse_args()

    # Create data directory
    args.data_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "download":
        asyncio.run(download_data(args.data_dir, args.type, args.force))
    elif args.command == "import":
        asyncio.run(import_data(args.data_dir, getattr(args, "file", None)))
    elif args.command == "status":
        asyncio.run(show_status(args.data_dir))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
