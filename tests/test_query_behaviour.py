"""End-to-end query behaviour tests: query string in, expected card names out.

These tests exercise the full parse -> SQL -> results pipeline against a
small, purpose-built card set where every expectation is obvious by
inspection. They pin the semantics that the flat filters-dict parser got
wrong: repeated filters (ranges), parenthesized groups, group negation,
and per-branch conditions in OR queries.
"""

import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.card_store import CardStore
from src.query_parser import QueryError, QueryParser

BEHAVIOUR_CARDS: list[dict[str, Any]] = [
    {
        "id": "b0000000-0000-0000-0000-000000000001",
        "name": "Alpha Strike",
        "cmc": 1.0,
        "colors": ["R"],
        "type_line": "Instant",
        "oracle_text": "Alpha Strike deals 1 damage to any target.",
        "set": "aaa",
        "rarity": "common",
    },
    {
        "id": "b0000000-0000-0000-0000-000000000002",
        "name": "Bolt Hound",
        "cmc": 2.0,
        "colors": ["R"],
        "type_line": "Creature — Dog",
        "oracle_text": "Haste",
        "keywords": ["Haste"],
        "set": "aaa",
        "rarity": "rare",
    },
    {
        "id": "b0000000-0000-0000-0000-000000000003",
        "name": "Cloud Sprite",
        "cmc": 1.0,
        "colors": ["U"],
        "type_line": "Creature — Faerie",
        "oracle_text": "Flying",
        "keywords": ["Flying"],
        "set": "bbb",
        "rarity": "common",
    },
    {
        "id": "b0000000-0000-0000-0000-000000000004",
        "name": "Dusk Angel",
        "cmc": 4.0,
        "colors": ["W"],
        "type_line": "Creature — Angel",
        "oracle_text": "Flying, vigilance",
        "keywords": ["Flying", "Vigilance"],
        "set": "bbb",
        "rarity": "rare",
    },
    {
        "id": "b0000000-0000-0000-0000-000000000005",
        "name": "Ember Giant",
        "cmc": 5.0,
        "colors": ["R"],
        "type_line": "Creature — Giant",
        "oracle_text": "Trample",
        "keywords": ["Trample"],
        "set": "ccc",
        "rarity": "uncommon",
    },
    {
        "id": "b0000000-0000-0000-0000-000000000006",
        "name": "Steam Djinn",
        "cmc": 6.0,
        "colors": ["U", "R"],
        "type_line": "Creature — Djinn",
        "oracle_text": "Steam Djinn deals 2 damage to each opponent.",
        "set": "ccc",
        "rarity": "mythic",
    },
    {
        # Deliberately sparse: no oracle_text, no flavor_text, no colors.
        # Pins NULL-column semantics under negation — a card with no rules
        # text must still appear in -o:... results (IS NULL guard).
        "id": "b0000000-0000-0000-0000-000000000007",
        "name": "Barren Field",
        "cmc": 0.0,
        "type_line": "Land",
        "set": "ccc",
        "rarity": "common",
    },
]

ALL_NAMES = sorted(card["name"] for card in BEHAVIOUR_CARDS)


@pytest.fixture
def behaviour_store():
    """CardStore loaded with the behaviour test cards."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = CardStore(Path(tmpdir) / "behaviour.db")
        store.insert_cards(BEHAVIOUR_CARDS)
        yield store
        store.close()


@pytest.fixture
def search(behaviour_store):
    """Run a query string end-to-end, returning sorted matching card names."""
    parser = QueryParser()

    def _search(query: str) -> list[str]:
        parsed = parser.parse(query)
        cards = behaviour_store.execute_query(parsed, limit=50)
        return sorted(card["name"] for card in cards)

    return _search


class TestRepeatedFilters:
    """Repeated filter keys must AND together, not overwrite each other."""

    def test_cmc_range(self, search):
        assert search("cmc>=2 cmc<=4") == ["Bolt Hound", "Dusk Angel"]

    def test_cmc_range_narrow(self, search):
        assert search("cmc>=1 cmc<=1") == ["Alpha Strike", "Cloud Sprite"]

    def test_repeated_color_filters_require_both(self, search):
        assert search("c:red c:blue") == ["Steam Djinn"]

    def test_contradictory_set_filters_match_nothing(self, search):
        assert search("set:aaa set:bbb") == []

    def test_repeated_oracle_text_still_ands(self, search):
        # Multi-value text filters used the FTS path before and must still work
        assert search("o:flying o:vigilance") == ["Dusk Angel"]


class TestParenthesizedGroups:
    """Parenthesized groups must be honored, not silently discarded."""

    def test_bare_group(self, search):
        assert search("(o:flying)") == ["Cloud Sprite", "Dusk Angel"]

    def test_group_and_outer_filter(self, search):
        assert search("(t:creature) c:red") == ["Bolt Hound", "Ember Giant", "Steam Djinn"]

    def test_nested_group(self, search):
        assert search("((o:flying))") == ["Cloud Sprite", "Dusk Angel"]

    def test_empty_parens_match_all(self, search):
        # Real Scryfall rejects "()"; treating it as no-op (match all) is a
        # deliberate lenient choice pinned here.
        assert search("()") == ALL_NAMES

    def test_two_or_groups_cross_product(self, search):
        # (red OR blue) AND (instant OR haste) — requires cross-product
        # distribution, which the old single-paren-group logic could not do
        assert search("(c:red OR c:blue) (t:instant OR o:haste)") == [
            "Alpha Strike",
            "Bolt Hound",
        ]


class TestGroupNegation:
    """Negating a group must apply De Morgan, not be silently dropped."""

    def test_negated_single_filter_group(self, search):
        # Barren Field has NULL oracle_text and must still match the negation
        assert search("-(o:flying)") == [
            "Alpha Strike",
            "Barren Field",
            "Bolt Hound",
            "Ember Giant",
            "Steam Djinn",
        ]

    def test_negated_and_group(self, search):
        # NOT(creature AND flying) = NOT creature OR NOT flying
        assert search("-(t:creature o:flying)") == [
            "Alpha Strike",
            "Barren Field",
            "Bolt Hound",
            "Ember Giant",
            "Steam Djinn",
        ]

    def test_negated_or_group(self, search):
        # NOT(instant OR trample) = NOT instant AND NOT trample
        assert search("-(t:instant OR o:trample)") == [
            "Barren Field",
            "Bolt Hound",
            "Cloud Sprite",
            "Dusk Angel",
            "Steam Djinn",
        ]

    def test_double_negation_is_positive(self, search):
        assert search("--o:flying") == ["Cloud Sprite", "Dusk Angel"]

    def test_negated_exact_name(self, search):
        assert search('-"Alpha Strike"') == [n for n in ALL_NAMES if n != "Alpha Strike"]

    def test_negated_strict_name(self, search):
        assert search('-!"Alpha Strike"') == [n for n in ALL_NAMES if n != "Alpha Strike"]


class TestOrBranchConditions:
    """Each OR branch keeps its own conditions, including repeated keys."""

    def test_or_with_range_in_branch(self, search):
        # Old code merged each branch's filters into a dict, so the range
        # in the first branch collapsed to just cmc<=5 (wrongly matching
        # Bolt Hound at cmc 2)
        assert search("cmc>=4 cmc<=5 OR cmc<=1") == [
            "Alpha Strike",
            "Barren Field",
            "Cloud Sprite",
            "Dusk Angel",
            "Ember Giant",
        ]

    def test_or_distributes_outer_filters(self, search):
        assert search("(o:haste OR o:trample) r:rare") == ["Bolt Hound"]

    def test_lowercase_or_is_boolean_or(self, search):
        # Matches live Scryfall (verified July 2026: "sword or plowshares"
        # and "sword OR plowshares" both return the union, 83 cards) —
        # lowercase or IS the boolean operator, not a name word
        assert search("hound or sprite") == search("hound OR sprite") == [
            "Bolt Hound",
            "Cloud Sprite",
        ]


class TestQueryComplexityAndErrors:
    """Structural errors are reported, not silently mis-answered."""

    def test_too_complex_query_rejected(self, search):
        # 9 OR-pairs cross-multiply to 512 groups, past the 500-group cap
        query = " ".join("(a:x OR a:y)" for _ in range(9))
        with pytest.raises(QueryError, match="too complex"):
            search(query)

    def test_missing_closing_paren(self, search):
        with pytest.raises(QueryError, match="missing closing"):
            search("(t:creature")

    def test_extra_closing_paren(self, search):
        with pytest.raises(QueryError, match="extra closing"):
            search("t:creature)")


class TestCountMatchesConsistency:
    """count_matches must agree with execute_query for group queries."""

    @pytest.mark.parametrize(
        "query",
        [
            "cmc>=2 cmc<=4",
            "-(t:creature o:flying)",
            "(c:red OR c:blue) (t:instant OR o:haste)",
            "cmc>=4 cmc<=5 OR cmc<=1",
            "o:flying o:vigilance",
        ],
    )
    def test_count_matches_execute_query(self, behaviour_store, query):
        parser = QueryParser()
        parsed = parser.parse(query)
        results = behaviour_store.execute_query(parsed, limit=50)
        assert behaviour_store.count_matches(parsed) == len(results)


class TestNullColumnNegation:
    """Cards with NULL text columns must appear in negated results."""

    def test_null_oracle_text_matches_leaf_negation(self, search):
        assert "Barren Field" in search("-o:flying")

    def test_null_flavor_text_matches_negation(self, search):
        # No fixture card has flavor text, so everything matches
        assert search("-ft:dragon") == ALL_NAMES


class TestColorEquals:
    """c= means exactly those colors (Scryfall); c: means at least (c>=)."""

    def test_color_equals_is_exact(self, search):
        # c=r matches mono-red only — Steam Djinn (UR) is excluded
        assert search("c=r") == ["Alpha Strike", "Bolt Hound", "Ember Giant"]

    def test_color_colon_is_at_least(self, search):
        # c:r means "at least red" (Scryfall: c: is equivalent to c>=),
        # so the UR card is included
        assert search("c:r") == [
            "Alpha Strike",
            "Bolt Hound",
            "Ember Giant",
            "Steam Djinn",
        ]

    def test_color_equals_multicolor(self, search):
        # c=ur matches exactly blue+red
        assert search("c=ur") == ["Steam Djinn"]

    def test_color_equals_no_exact_match(self, search):
        # No card is exactly white+blue
        assert search("c=wu") == []


class TestColorNegation:
    """Color negation is the exact complement of the positive filter."""

    def test_negated_color_group(self, search):
        # Colorless Barren Field is not red and must be included
        assert search("-(c:red)") == ["Barren Field", "Cloud Sprite", "Dusk Angel"]

    def test_negated_multicolor_is_missing_any(self, search):
        # -c:ur = NOT(blue AND red) = missing blue or missing red,
        # per SUPPORTED_SYNTAX.md — only the UR card is excluded
        assert search("-c:ur") == [n for n in ALL_NAMES if n != "Steam Djinn"]

    def test_negated_subset_operator(self, search):
        # -(c<=wu) = not a subset of {W,U}; colorless IS a subset, so
        # Barren Field must be excluded from the negation
        assert search("-(c<=wu)") == [
            "Alpha Strike",
            "Bolt Hound",
            "Ember Giant",
            "Steam Djinn",
        ]

    def test_negated_color_equals_is_exact_complement(self, search):
        # -(c=r) = everything that is not exactly mono-red, including
        # multicolor cards containing red and colorless cards
        assert search("-(c=r)") == [
            "Barren Field",
            "Cloud Sprite",
            "Dusk Angel",
            "Steam Djinn",
        ]

    @pytest.mark.parametrize("operator", [":", "=", ">=", "<=", ">", "<"])
    def test_color_negation_partitions_universe(self, search, operator):
        # For every operator, c<op>wu and -(c<op>wu) must tile the card
        # universe exactly: no card in both, no card in neither
        positive = search(f"c{operator}wu")
        negative = search(f"-(c{operator}wu)")
        assert sorted(positive + negative) == ALL_NAMES
        assert not set(positive) & set(negative)


class TestQuotedNameSemantics:
    """Quoted names are substring matches (Scryfall); !"..." is the exact form."""

    def test_quoted_name_is_substring(self, search):
        # "Bolt" is a substring of Bolt Hound — Scryfall quotes are not exact
        assert search('"Bolt"') == ["Bolt Hound"]

    def test_quoted_name_is_case_insensitive(self, search):
        assert search('"bolt"') == ["Bolt Hound"]

    def test_quoted_phrase_with_space(self, search):
        assert search('"cloud sprite"') == ["Cloud Sprite"]

    def test_quoted_partial_word(self, search):
        # substring, not word match: "loud" is inside Cloud Sprite
        assert search('"loud"') == ["Cloud Sprite"]

    def test_strict_name_is_exact(self, search):
        assert search('!"Alpha Strike"') == ["Alpha Strike"]

    def test_strict_name_is_not_substring(self, search):
        assert search('!"Alpha"') == []

    def test_strict_name_is_case_insensitive(self, search):
        # Scryfall: "If you prefix words or quoted phrases with ! you will
        # find cards with that exact name only. This is still case-insensitive."
        assert search('!"alpha strike"') == ["Alpha Strike"]

    def test_negated_quoted_name(self, search):
        assert search('-"bolt"') == [n for n in ALL_NAMES if n != "Bolt Hound"]

    def test_negated_strict_name(self, search):
        assert search('-!"alpha strike"') == [
            n for n in ALL_NAMES if n != "Alpha Strike"
        ]

    def test_strict_partition_universe(self, search):
        positive = search('!"Alpha Strike"')
        negative = search('-(!"Alpha Strike")')
        assert sorted(positive + negative) == ALL_NAMES
        assert not set(positive) & set(negative)


class TestIsFilterBehaviour:
    """is: filters run end-to-end through the layout/type machinery."""

    def test_is_permanent(self, search):
        # Everything except the instant
        assert search("is:permanent") == [n for n in ALL_NAMES if n != "Alpha Strike"]

    def test_is_spell(self, search):
        # Everything except the land
        assert search("is:spell") == [n for n in ALL_NAMES if n != "Barren Field"]

    def test_negated_is_permanent(self, search):
        assert search("-is:permanent") == ["Alpha Strike"]

    def test_is_spell_partitions_universe(self, search):
        positive = search("is:spell")
        negative = search("-(is:spell)")
        assert sorted(positive + negative) == ALL_NAMES
        assert not set(positive) & set(negative)

    def test_is_permanent_partitions_universe(self, search):
        positive = search("is:permanent")
        negative = search("-(is:permanent)")
        assert sorted(positive + negative) == ALL_NAMES
        assert not set(positive) & set(negative)


class TestNegationWithFts:
    """Negated conditions mixed with positive FTS-eligible filters."""

    def test_negated_group_with_positive_type(self, search):
        # type goes through FTS MATCH, the negated oracle_text through LIKE,
        # in the same single AND group
        assert search("-(o:flying) t:creature") == [
            "Bolt Hound",
            "Ember Giant",
            "Steam Djinn",
        ]

    def test_nested_or_inside_negated_group(self, search):
        # NOT((flying OR trample) AND creature)
        #   = (NOT flying AND NOT trample) OR NOT creature
        assert search("-((o:flying OR o:trample) t:creature)") == [
            "Alpha Strike",
            "Barren Field",
            "Bolt Hound",
            "Steam Djinn",
        ]


class TestComplexityCap:
    """The OR-group cap catches genuine blowup but not flat OR chains."""

    def test_long_flat_or_chain_allowed(self):
        # 65 OR-ed terms grow linearly, not multiplicatively — must parse
        letters = "abcdefghijklmnopqrstuvwxyz"
        terms = [f"o:{a}{b}" for a in letters[:3] for b in letters][:65]
        parsed = QueryParser().parse(" OR ".join(terms))
        assert parsed.groups is not None and len(parsed.groups) == 65

    def test_cap_trips_via_negated_cross_product(self, search):
        # Negating (25 ANDs OR 25 ANDs) De Morgans into 25x25 = 625 groups
        letters = "abcdefghijklmnopqrstuvwxy"
        branch_a = " ".join(f"o:a{c}" for c in letters)
        branch_b = " ".join(f"o:b{c}" for c in letters)
        with pytest.raises(QueryError, match="too complex"):
            search(f"-(({branch_a}) OR ({branch_b}))")

    def test_cap_applies_to_sole_negated_group(self, monkeypatch):
        # Regression: a negated AND group produced as the ONLY term used to
        # bypass the cap (seeding skipped the check). Inject a small cap and
        # assert the property at that threshold.
        monkeypatch.setattr(QueryParser, "MAX_OR_GROUPS", 8)
        letters = "abcdefghi"  # 9 terms -> 9 groups > 8
        query = "-(" + " ".join(f"o:x{c}" for c in letters) + ")"
        with pytest.raises(QueryError, match="too complex"):
            QueryParser().parse(query)


class TestMultiGroupPagination:
    """Offset pagination is stable across multi-group (OR) queries."""

    def test_offset_walk_covers_all_results_once(self, behaviour_store):
        parser = QueryParser()
        parsed = parser.parse("t:creature OR t:instant")
        full = [c["name"] for c in behaviour_store.execute_query(parsed, limit=50)]
        assert len(full) == 6

        walked: list[str] = []
        for offset in range(0, len(full), 2):
            page = behaviour_store.execute_query(parsed, limit=2, offset=offset)
            walked.extend(c["name"] for c in page)
        assert walked == full


class TestLegacyViewConsistency:
    """The legacy filters view must never contradict the canonical groups."""

    def test_negated_group_filters_show_negation(self):
        parsed = QueryParser().parse("-(o:flying)")
        assert parsed.filters == {"oracle_text_not": ["flying"]}

    def test_double_negated_group_filters_show_positive(self):
        parsed = QueryParser().parse("-(-o:flying)")
        assert parsed.filters == {"oracle_text": ["flying"]}
