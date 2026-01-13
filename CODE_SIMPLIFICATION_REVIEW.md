# Code Simplification Review: scryfall-local

**Date:** 2025-01-13
**Reviewer:** code-simplifier agent
**Scope:** Source code in `src/` directory

## Executive Summary

The codebase is well-structured, thoroughly tested, and security-conscious. However, there are significant opportunities for reducing repetition, particularly in `card_store.py`. Implementing the high-priority recommendations could reduce source code by **400-600 lines** (~25-35%) while improving maintainability.

| Metric | Current | After Simplification |
|--------|---------|---------------------|
| Total Source Lines | ~3,600 | ~3,000-3,200 |
| `card_store.py` | 1,555 | ~1,000-1,100 |
| `query_parser.py` | 623 | ~550-580 |

---

## High-Impact Opportunities

### 1. Repetitive Filter Handling in `_build_conditions_for_filters`

**File:** `src/card_store.py` (lines 785-1406)
**Impact:** ~450 lines reducible to ~100-150

The method contains 30+ nearly identical patterns for building SQL conditions:

```python
# Current pattern - repeated for: type, oracle_text, flavor_text,
# keyword, produces_token, name_partial, and their _not variants
if "type" in filters:
    type_values = filters["type"]
    if isinstance(type_values, list):
        for type_val in type_values:
            conditions.append("LOWER(type_line) LIKE ?")
            params.append(f"%{type_val.lower()}%")
    else:
        conditions.append("LOWER(type_line) LIKE ?")
        params.append(f"%{type_values.lower()}%")
```

**Recommended Refactor:**

```python
def _add_like_conditions(
    self,
    filters: dict[str, Any],
    key: str,
    column: str,
    conditions: list[str],
    params: list[Any],
    case_insensitive: bool = True,
    negated: bool = False,
) -> None:
    """Add LIKE conditions for a filter key.

    Args:
        filters: Filter dictionary
        key: Key to look up in filters
        column: SQL column name
        conditions: List to append conditions to
        params: List to append parameters to
        case_insensitive: Whether to use LOWER() for matching
        negated: Whether this is a NOT filter
    """
    if key not in filters:
        return

    values = filters[key]
    values = values if isinstance(values, list) else [values]

    operator = "NOT LIKE" if negated else "LIKE"
    col_expr = f"LOWER({column})" if case_insensitive else column

    for val in values:
        match_val = val.lower() if case_insensitive else val
        if negated:
            conditions.append(f"({column} IS NULL OR {col_expr} {operator} ?)")
        else:
            conditions.append(f"{col_expr} {operator} ?")
        params.append(f"%{match_val}%")
```

**Usage would become:**

```python
# Before: 16 lines per filter type (8 for positive, 8 for negative)
# After: 2 lines per filter type
self._add_like_conditions(filters, "type", "type_line", conditions, params)
self._add_like_conditions(filters, "type_not", "type_line", conditions, params, negated=True)
self._add_like_conditions(filters, "oracle_text", "oracle_text", conditions, params)
self._add_like_conditions(filters, "oracle_text_not", "oracle_text", conditions, params, negated=True)
# ... etc
```

---

### 2. Duplicate `_not` Filter Logic

**File:** `src/card_store.py`
**Impact:** ~150 lines reducible

Every filter has a `_not` variant duplicating 90% of the logic. Current pairs:

| Positive Filter | Negative Filter | Lines Each |
|----------------|-----------------|------------|
| `type` | `type_not` | 8 + 8 |
| `oracle_text` | `oracle_text_not` | 8 + 8 |
| `flavor_text` | `flavor_text_not` | 8 + 8 |
| `keyword` | `keyword_not` | 8 + 8 |
| `produces_token` | `produces_token_not` | 8 + 8 |
| `name_partial` | `name_partial_not` | 8 + 8 |
| `set` | `set_not` | 3 + 3 |
| `rarity` | `rarity_not` | 3 + 3 |
| `format` | `format_not` | 6 + 8 |
| `artist` | `artist_not` | 3 + 4 |
| `watermark` | `watermark_not` | 3 + 4 |
| `layout` | `layout_not` | 3 + 4 |
| ... | ... | ... |

**Recommendation:** Handle negation as a parameter (see helper function above) or use a data-driven approach with filter definitions.

---

### 3. Color Filter Duplication

**File:** `src/card_store.py` (lines 836-947)
**Impact:** ~60 lines reducible

`colors` and `color_identity` filters have nearly identical handling for all operators. The code is copy-pasted with only the column name changed.

**Current structure:**
```python
# Colors filter (lines 836-882) - ~46 lines
if "colors" in filters:
    color_filter = filters["colors"]
    colors = color_filter.get("value", [])
    operator = color_filter.get("operator", ":")
    if not colors:
        conditions.append("colors = '[]'")
    elif operator in (":", "=", ">="):
        for c in colors:
            conditions.append("colors LIKE ?")
            params.append(f'%"{c}"%')
    # ... more operators

# Color identity filter (lines 896-936) - ~40 lines (nearly identical)
if "color_identity" in filters:
    identity_filter = filters["color_identity"]
    colors = identity_filter.get("value", [])
    operator = identity_filter.get("operator", ":")
    # ... same logic with "color_identity" column
```

**Recommended Refactor:**

```python
def _add_color_conditions(
    self,
    filters: dict[str, Any],
    key: str,
    column: str,
    conditions: list[str],
    params: list[Any],
) -> None:
    """Add color-based filter conditions.

    Handles all color operators: =, :, >=, <=, >, <
    """
    if key not in filters:
        return

    color_filter = filters[key]
    colors = color_filter.get("value", [])
    operator = color_filter.get("operator", ":")

    if not colors:
        conditions.append(f"{column} = '[]'")
        return

    if operator in (":", "=", ">="):
        for c in colors:
            conditions.append(f"{column} LIKE ?")
            params.append(f'%"{c}"%')
    elif operator == "<=":
        all_colors = {"W", "U", "B", "R", "G"}
        disallowed = all_colors - set(colors)
        for c in disallowed:
            conditions.append(f"{column} NOT LIKE ?")
            params.append(f'%"{c}"%')
    # ... other operators
```

---

### 4. OR Query Logic Duplicated in `get_random_card`

**File:** `src/card_store.py` (lines 1502-1555 vs 1408-1451)
**Impact:** ~20 lines reducible

`get_random_card` duplicates the OR query building logic from `_build_where_clause`:

```python
# In get_random_card (1519-1541):
if parsed.has_or_clause and parsed.or_groups:
    group_clauses = []
    all_params: list[Any] = []
    for group_filters in parsed.or_groups:
        merged: dict[str, Any] = {}
        for f in group_filters:
            merged.update(f)
        conditions, params = self._build_conditions_for_filters(merged)
        if conditions:
            group_clauses.append(f"({' AND '.join(conditions)})")
            all_params.extend(params)
    # ... build WHERE clause
```

**Recommended Refactor:**

```python
def get_random_card(self, parsed: ParsedQuery | None = None) -> dict[str, Any] | None:
    cursor = self._conn.cursor()

    if not parsed or parsed.is_empty:
        cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    # Reuse existing method
    where_clause, params = self._build_where_clause(parsed)

    if where_clause:
        query = f"SELECT * FROM cards WHERE {where_clause} ORDER BY RANDOM() LIMIT 1"
    else:
        query = "SELECT * FROM cards ORDER BY RANDOM() LIMIT 1"
        params = []

    cursor.execute(query, params)
    row = cursor.fetchone()
    return self._row_to_dict(row) if row else None
```

---

## Medium-Impact Opportunities

### 5. Unused Query Methods

**File:** `src/card_store.py`
**Impact:** ~150 lines removable

These methods exist but are only used in tests, not by the main `execute_query` path:

| Method | Lines | Used By |
|--------|-------|---------|
| `query_by_color()` | 587-648 | Tests only |
| `query_by_cmc()` | 650-673 | Tests only |
| `query_by_type()` | 675-690 | Tests only |
| `query_by_set()` | 751-766 | Tests only |
| `query_by_rarity()` | 768-783 | Tests only |
| `query_by_oracle_text()` | 711-749 | Tests only |
| `search_by_partial_name()` | 568-585 | Tests only |

**Options:**
1. **Remove entirely** - All functionality is covered by `execute_query()`
2. **Deprecate** - Mark with deprecation warnings
3. **Keep for API convenience** - If these provide value as standalone methods

**Recommendation:** Remove and update tests to use `execute_query()` directly. This tests the actual code path used in production.

---

### 6. Token Pattern Handling in `_tokenize`

**File:** `src/query_parser.py` (lines 297-373)
**Impact:** ~30 lines reducible

The tokenizer has many similar if/elif branches that could be grouped:

```python
# Current: separate handling for similar token types
elif token_type == 'CMC':
    operator = match.group(1)
    value = float(match.group(2))
    tokens.append((token_type, (operator, value)))
elif token_type in ('POWER', 'TOUGHNESS', 'LOYALTY'):
    operator = match.group(1)
    value = match.group(2)
    if value != '*':
        value = int(value)
    tokens.append((token_type, (operator, value)))
elif token_type == 'COLLECTOR_NUMBER':
    operator = match.group(1)
    value = match.group(2)
    tokens.append((token_type, (operator, value)))
```

**Recommended Refactor:**

```python
# Define token type categories
OPERATOR_VALUE_TOKENS = {'CMC', 'YEAR'}  # (operator, float/int)
OPERATOR_STRING_TOKENS = {'POWER', 'TOUGHNESS', 'LOYALTY', 'COLLECTOR_NUMBER'}  # (operator, str/int)
SIMPLE_VALUE_TOKENS = {'TYPE', 'ORACLE', 'SET', 'RARITY', ...}  # Just the value

# In _tokenize:
if token_type in OPERATOR_VALUE_TOKENS:
    tokens.append((token_type, (match.group(1), float(match.group(2)))))
elif token_type in OPERATOR_STRING_TOKENS:
    op, val = match.group(1), match.group(2)
    tokens.append((token_type, (op, int(val) if val.isdigit() else val)))
elif token_type in SIMPLE_VALUE_TOKENS:
    tokens.append((token_type, match.group(1)))
```

---

### 7. Streaming Import Duplication

**Files:** `src/cli.py` (lines 50-91), `src/server.py` (lines 436-490)
**Impact:** ~40 lines reducible

Both files implement streaming JSON import with minor differences:

| Aspect | cli.py | server.py |
|--------|--------|-----------|
| Function name | `import_cards_streaming` | `_import_cards_blocking` |
| Progress callback | Yes | No |
| Store management | Passed in | Creates own |
| Error handling | Raises | Raises |

**Recommended Refactor:**

Create `src/import_utils.py`:

```python
def stream_import_cards(
    json_file: Path,
    db_path: Path,
    batch_size: int = 1000,
    progress_callback: Callable[[int], None] | None = None,
) -> int:
    """Stream import cards from JSON to SQLite.

    Args:
        json_file: Path to JSON file
        db_path: Path to SQLite database
        batch_size: Cards per batch insert
        progress_callback: Optional callback(card_count) for progress

    Returns:
        Total cards imported
    """
    import ijson
    from src.card_store import CardStore

    store = CardStore(db_path)
    batch: list[dict] = []
    card_count = 0

    try:
        with open(json_file, "rb") as f:
            for card in ijson.items(f, "item"):
                batch.append(card)
                if len(batch) >= batch_size:
                    store.insert_cards(batch)
                    card_count += len(batch)
                    batch = []
                    if progress_callback:
                        progress_callback(card_count)

        if batch:
            store.insert_cards(batch)
            card_count += len(batch)
            if progress_callback:
                progress_callback(card_count)
    finally:
        store.close()

    return card_count
```

---

## Low-Impact Opportunities

### 8. Operator Normalization Repeated

**File:** `src/query_parser.py` (lines 541-587)
**Impact:** ~15 lines reducible

Multiple places normalize `:` to `=`:

```python
# This appears 6+ times in _get_filter_value:
if operator == ':':
    operator = '='
```

**Recommendation:** Normalize once during tokenization:

```python
# In _tokenize, after extracting operator:
operator = '=' if operator == ':' else operator
```

---

### 9. `_parse_color_value` vs `_parse_identity_value`

**File:** `src/query_parser.py` (lines 150-195)
**Impact:** ~20 lines reducible

These functions share ~80% of their code:

```python
def _parse_color_value(value: str) -> list[str]:
    value = value.lower()
    if value in ("c", "colorless"):
        return []
    # ... rest of logic

def _parse_identity_value(value: str) -> list[str]:
    value = value.lower()
    if value in IDENTITY_MAP:  # <-- Only difference
        return IDENTITY_MAP[value]
    if value in ("c", "colorless"):
        return []
    # ... same logic
```

**Recommendation:** Merge with a flag or lookup parameter.

---

### 10. BLOCK_MAP Aliases

**File:** `src/card_store.py` (lines 72-108)
**Impact:** Minor (code clarity)

Several block names have redundant aliases:

```python
"ice age": ["ice", "all", "csp"],
"iceage": ["ice", "all", "csp"],  # Same values
"time spiral": ["tsp", "plc", "fut"],
"timespiral": ["tsp", "plc", "fut"],  # Same values
```

**Recommendation:** Generate aliases programmatically:

```python
_BLOCK_DATA = {
    "ice age": ["ice", "all", "csp"],
    "time spiral": ["tsp", "plc", "fut"],
    # ...
}

BLOCK_MAP = {}
for name, sets in _BLOCK_DATA.items():
    BLOCK_MAP[name] = sets
    BLOCK_MAP[name.replace(" ", "")] = sets  # Auto-generate spaceless alias
```

---

### 11. Test Fixture Consolidation

**File:** `tests/conftest.py`
**Impact:** ~50 lines reducible

`sample_cards` (lines 10-244) and `sample_cards_with_keywords` (lines 277-379) have overlapping data. Cards like Serra Angel already have keywords in `sample_cards`.

**Recommendation:** Have `sample_cards_with_keywords` filter/extend `sample_cards` rather than defining separate cards.

---

## Implementation Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| **P1** | Refactor `_build_conditions_for_filters` with helpers | Medium | High |
| **P1** | Unify positive/negative filter handling | Medium | High |
| **P2** | Extract shared color filter logic | Low | Medium |
| **P2** | Reuse `_build_where_clause` in `get_random_card` | Low | Low |
| **P3** | Remove unused `query_by_*` methods | Low | Medium |
| **P3** | Extract shared streaming import logic | Low | Low |
| **P4** | Consolidate token pattern handling | Low | Low |
| **P4** | Consolidate test fixtures | Low | Low |

---

## Risks and Considerations

1. **Test Coverage:** All refactoring should maintain 100% test pass rate. The existing test suite is comprehensive.

2. **Performance:** Helper functions add minimal overhead. SQLite query execution dominates runtime.

3. **Backwards Compatibility:** The unused `query_by_*` methods may be used by external code if this is published as a library. Consider deprecation warnings before removal.

4. **Readability Trade-off:** Some explicit repetition can be clearer than abstraction. The current code is very readable despite being verbose.

---

## Conclusion

The codebase is production-quality and well-maintained. The identified simplifications would:

- Reduce total source lines by ~25-35%
- Lower maintenance burden for filter additions
- Make the filter system more consistent
- Reduce risk of copy-paste errors

The highest-value change is refactoring `_build_conditions_for_filters` with helper functions, which addresses ~70% of the identified redundancy.
