"""Shared utilities for importing card data."""

import logging
from pathlib import Path
from typing import Any, Callable

from src.card_store import CardStore

logger = logging.getLogger(__name__)


def _card_preview(card: Any) -> str:
    """Return a short string representation of a card for log messages."""
    if isinstance(card, dict):
        return str({k: card[k] for k in list(card)[:3]})
    return repr(card)[:120]


def import_cards_streaming(
    json_file: Path,
    store: CardStore,
    batch_size: int = 1000,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Import cards from JSON using streaming parser.

    Uses ijson to parse the JSON file incrementally, reducing memory usage
    from ~2.5GB to a small fixed amount regardless of file size.

    Cards that are not dicts or are missing the ``"id"`` key (the primary key)
    are skipped with a warning rather than aborting the entire import.

    Note: This function does NOT manage the store lifecycle. The caller is
    responsible for opening and closing the store connection.

    Args:
        json_file: Path to the JSON file containing card data
        store: CardStore instance to import cards into
        batch_size: Number of cards per batch insert (default 1000)
        progress_callback: Optional callback(card_count) for progress updates

    Returns:
        Tuple of (cards_imported, cards_skipped)

    Raises:
        ImportError: If ijson is not installed
        FileNotFoundError: If json_file does not exist
    """
    # Lazy import ijson - only needed for data refresh, not basic queries
    try:
        import ijson
    except ImportError as e:
        raise ImportError(
            "ijson is required for importing card data. "
            "Install it with: pip install ijson"
        ) from e

    batch: list[dict[str, Any]] = []
    card_count = 0
    skipped = 0

    with open(json_file, "rb") as f:
        # ijson.items streams through the JSON array one item at a time
        for card in ijson.items(f, "item"):
            if not isinstance(card, dict) or not card.get("id"):
                skipped += 1
                logger.warning(
                    "Skipping malformed card (missing id): %s",
                    _card_preview(card),
                )
                continue
            batch.append(card)
            if len(batch) >= batch_size:
                store.insert_cards(batch)
                card_count += len(batch)
                batch = []
                if progress_callback:
                    progress_callback(card_count)

    # Insert remaining cards
    if batch:
        store.insert_cards(batch)
        card_count += len(batch)
        if progress_callback:
            progress_callback(card_count)

    return card_count, skipped


def import_to_temp_and_swap(
    json_file: Path,
    db_path: Path,
    batch_size: int = 1000,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Import cards into a temp database, then atomically swap it into place.

    Imports into db_path.with_suffix('.db.tmp'), then uses Path.replace()
    for an atomic swap. If import fails, the original database is untouched.

    Args:
        json_file: Path to the JSON file containing card data
        db_path: Final destination path for the database
        batch_size: Number of cards per batch insert (default 1000)
        progress_callback: Optional callback(card_count) for progress updates

    Returns:
        Tuple of (cards_imported, cards_skipped)

    Raises:
        ImportError: If ijson is not installed
        FileNotFoundError: If json_file does not exist
    """
    temp_path = db_path.with_suffix(".db.tmp")

    try:
        # Clean up any leftover temp files from a previous failed run
        _cleanup_temp_files(temp_path)

        # Import into temp database
        with CardStore(temp_path) as store:
            card_count, skipped = import_cards_streaming(
                json_file, store, batch_size=batch_size,
                progress_callback=progress_callback,
            )
            # Flush WAL into main file so temp DB is self-contained
            store.checkpoint()

        # Atomically swap temp DB into place (POSIX rename is atomic on same fs)
        temp_path.replace(db_path)

        # Clean up old WAL/SHM companion files from the previous database
        for suffix in ("-wal", "-shm"):
            companion = Path(str(db_path) + suffix)
            if companion.exists():
                try:
                    companion.unlink()
                except OSError:
                    pass

        return card_count, skipped

    except BaseException:
        # On any failure, clean up temp files and re-raise (old DB untouched)
        _cleanup_temp_files(temp_path)
        raise


def _cleanup_temp_files(temp_path: Path) -> None:
    """Remove temp database and its WAL/SHM companion files."""
    for path in (
        temp_path,
        Path(str(temp_path) + "-wal"),
        Path(str(temp_path) + "-shm"),
    ):
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
