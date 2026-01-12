# Known Issues and Technical Debt

This document tracks known issues, edge cases, and technical debt identified during code review.

Last updated: 2026-01-12

## Resolved Issues

### #4 - SQL consistency in query_by_color() ✅

**Status**: Resolved (2026-01-12)
**Location**: `card_store.py:583-644`
**Resolution**: Refactored `query_by_color()` to use parameterized queries instead of f-strings.

---

### #13 - FTS5 special characters ✅

**Status**: Resolved (2026-01-12)
**Location**: `card_store.py:688-706`
**Resolution**: Added `_escape_fts5()` helper method with documentation. The text is wrapped in double quotes for phrase search, where special characters are treated as literals. Falls back to LIKE on FTS5 errors.

---

### #21 - Color identity negation semantics ✅

**Status**: Resolved (2026-01-12)
**Location**: `SUPPORTED_SYNTAX.md`
**Resolution**: Added "Negation Semantics for Colors" section documenting that `-c:urg` excludes cards with ANY of U, R, or G (OR semantics, not AND).

---

### #24 - Download retry logic ✅

**Status**: Resolved (2026-01-12)
**Location**: `data_manager.py:216-309`
**Resolution**: Added retry loop with exponential backoff (1s, 2s, 4s). Cleans up partial downloads on failure. Default max_retries=3.

---

### #28 - Metadata write atomic ✅

**Status**: Resolved (2026-01-12)
**Location**: `data_manager.py:322-349`
**Resolution**: Added `_write_metadata_atomic()` method using write-to-temp-then-rename pattern.

---

### #23 - Unicode test coverage ✅

**Status**: Resolved (2026-01-12)
**Location**: `tests/test_card_store.py:2452-2592`, `tests/conftest.py:640-743`
**Resolution**: Added `unicode_cards` fixture and `TestUnicodeCardNames` test class with 7 tests covering: Séance, Lim-Dûl, Urza's, Márton, Dandân.

---

### #27 - JSON parse error logging ✅

**Status**: Resolved (2026-01-12)
**Location**: `card_store.py:527-532`
**Resolution**: Added debug logging when JSON field parsing fails, including field name and card ID.

---

### Download retry logging ✅

**Status**: Resolved (2026-01-12)
**Location**: `data_manager.py:260-323`
**Issue**: Download failures didn't indicate how many retries were attempted.
**Resolution**: Added logging for each retry attempt with delay info, success message on recovery, and error message now includes attempt count (e.g., "Download failed after 4 attempts: connection refused").

---

### SQLite threading bug in refresh ✅

**Status**: Resolved (2026-01-12)
**Location**: `server.py:492-514, 436-490`
**Issue**: SQLite connection created in main thread was being closed/accessed in worker thread during refresh, causing "SQLite objects created in a thread can only be used in that same thread" error.
**Resolution**:
1. Close existing store connection in main thread (inside `_do_refresh`) BEFORE calling `asyncio.to_thread()`
2. Create a local CardStore connection in worker thread instead of using `_get_store()` which would set `self._store`
3. Close worker thread's connection when done
4. Main thread queries will create fresh connection via `_get_store()` after refresh

**Discovery**: Found by new integration test `test_refresh_integration_full_flow`.

---

### Refresh integration test coverage ✅

**Status**: Resolved (2026-01-12)
**Location**: `tests/test_server.py:553-695`
**Issue**: No integration tests for full refresh flow.
**Resolution**: Added two integration tests:
1. `test_refresh_integration_full_flow` - Tests complete refresh cycle: download mock data, import, verify database updated
2. `test_refresh_integration_handles_download_error` - Tests error handling preserves original data

---

## Edge Cases (Won't Fix)

These are known limitations that are acceptable given the use case:

### Hardcoded HTTP timeouts (#6)
- **Location**: `data_manager.py:66`
- **Details**: 30s connect, 300s read timeout
- **Rationale**: Reasonable defaults for 2.5GB download

### Collector number alphanumeric comparison (#12)
- **Location**: `card_store.py:1127-1144`
- **Details**: Alphanumeric collector numbers like "100a" or "★" are compared by numeric prefix
- **Rationale**: Documented behavior, uses `_extract_numeric_prefix()`

### LIKE wildcards not escaped (#15)
- **Location**: `card_store.py:575-577`
- **Details**: `%` and `_` in card names would be interpreted as LIKE wildcards
- **Rationale**: No MTG cards contain these characters

### Multiple exact names overwrite (#19)
- **Location**: `query_parser.py:466`
- **Details**: `"Card A" "Card B"` keeps only "Card B"
- **Rationale**: ANDing exact names would always return empty results

### Fractional power/toughness (#25)
- **Location**: `card_store.py:1070`
- **Details**: Little Girl's "½" power casts to 0
- **Rationale**: Only affects one Un-set card

### Empty parentheses (#26)
- **Location**: `query_parser.py`
- **Details**: `() t:creature` silently ignores empty parens
- **Rationale**: Harmless edge case

### Mutable IDENTITY_MAP values (#50)
- **Location**: `query_parser.py:79-100`
- **Details**: Uses lists instead of tuples
- **Rationale**: Values are never mutated; defensive but not required

---

## False Positives from Review

The following issues from the code review were investigated and found to be already fixed or incorrect:

- #1: Race condition - Lock exists (`_refresh_lock`)
- #2: Blocking I/O - Uses `asyncio.to_thread()`
- #3: Version duplicated - Centralized in `__init__.py`
- #5: Negative limit - Validated with `max(1, ...)`
- #7: Migration SQL - Uses allowlisted column names
- #8: No WAL mode - Already enabled
- #9: Inconsistent lock - `_data_status` acquires lock
- #10: Negated CMC - Uses `INVERTED_OPERATOR_MAP`
- #11: FTS5 rowid - Uses UPSERT pattern
- #14: OR groups - Fully implemented
- #16: total_count - Uses `count_matches()`
- #17: NOT filters - All implemented
- #18: Unbalanced parens - Raises error
- #20: Invalid format - Returns empty (1=0)
- #22: Color > < - Implemented
- #29-32, #36, #38-40, #42-44, #46-47, #49, #60, #68-70: Various false positives
