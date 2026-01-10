"""Tests for Scryfall query parser - TDD approach."""

import pytest
from src.query_parser import QueryParser, ParsedQuery, QueryError


class TestQueryParserBasicName:
    """Test name-based queries."""

    def test_parse_exact_name_quoted(self):
        """Exact name match with quotes."""
        parser = QueryParser()
        result = parser.parse('"Lightning Bolt"')

        assert result.filters["name_exact"] == "Lightning Bolt"

    def test_parse_partial_name_unquoted(self):
        """Partial name match without quotes."""
        parser = QueryParser()
        result = parser.parse("bolt")

        assert result.filters["name_partial"] == "bolt"

    def test_parse_partial_name_multiple_words(self):
        """Partial name with multiple unquoted words (implicit AND)."""
        parser = QueryParser()
        result = parser.parse("lightning bolt")

        # Two separate partial name filters ANDed together
        assert "name_partial" in result.filters or len(result.conditions) >= 2


class TestQueryParserColors:
    """Test color-based queries."""

    def test_parse_single_color(self):
        """Single color filter: c:blue."""
        parser = QueryParser()
        result = parser.parse("c:blue")

        assert result.filters["colors"] == {"operator": ":", "value": ["U"]}

    def test_parse_color_symbol(self):
        """Color by symbol: c:u."""
        parser = QueryParser()
        result = parser.parse("c:u")

        assert result.filters["colors"]["value"] == ["U"]

    def test_parse_multiple_colors(self):
        """Multiple colors: c:urg."""
        parser = QueryParser()
        result = parser.parse("c:urg")

        colors = result.filters["colors"]["value"]
        assert set(colors) == {"U", "R", "G"}

    def test_parse_color_greater_equal(self):
        """Color with >= operator: c>=rg."""
        parser = QueryParser()
        result = parser.parse("c>=rg")

        assert result.filters["colors"]["operator"] == ">="
        assert set(result.filters["colors"]["value"]) == {"R", "G"}

    def test_parse_color_less_equal(self):
        """Color with <= operator: c<=w."""
        parser = QueryParser()
        result = parser.parse("c<=w")

        assert result.filters["colors"]["operator"] == "<="
        assert result.filters["colors"]["value"] == ["W"]

    def test_parse_colorless(self):
        """Colorless cards: c:c."""
        parser = QueryParser()
        result = parser.parse("c:c")

        assert result.filters["colors"]["value"] == []


class TestQueryParserManaValue:
    """Test mana value (CMC) queries."""

    def test_parse_cmc_exact(self):
        """Exact CMC: cmc:3."""
        parser = QueryParser()
        result = parser.parse("cmc:3")

        assert result.filters["cmc"] == {"operator": "=", "value": 3}

    def test_parse_cmc_equals(self):
        """CMC with explicit equals: cmc=3."""
        parser = QueryParser()
        result = parser.parse("cmc=3")

        assert result.filters["cmc"] == {"operator": "=", "value": 3}

    def test_parse_cmc_greater_equal(self):
        """CMC greater or equal: cmc>=5."""
        parser = QueryParser()
        result = parser.parse("cmc>=5")

        assert result.filters["cmc"] == {"operator": ">=", "value": 5}

    def test_parse_cmc_less_than(self):
        """CMC less than: cmc<2."""
        parser = QueryParser()
        result = parser.parse("cmc<2")

        assert result.filters["cmc"] == {"operator": "<", "value": 2}

    def test_parse_mv_alias(self):
        """MV is alias for CMC: mv:3."""
        parser = QueryParser()
        result = parser.parse("mv:3")

        assert result.filters["cmc"] == {"operator": "=", "value": 3}


class TestQueryParserType:
    """Test type-based queries."""

    def test_parse_type_simple(self):
        """Simple type: t:creature."""
        parser = QueryParser()
        result = parser.parse("t:creature")

        assert result.filters["type"] == ["creature"]

    def test_parse_type_quoted(self):
        """Quoted type: t:"legendary creature"."""
        parser = QueryParser()
        result = parser.parse('t:"legendary creature"')

        assert result.filters["type"] == ["legendary creature"]

    def test_parse_type_alias(self):
        """Type alias: type:instant."""
        parser = QueryParser()
        result = parser.parse("type:instant")

        assert result.filters["type"] == ["instant"]


class TestQueryParserOracleText:
    """Test oracle text queries."""

    def test_parse_oracle_simple(self):
        """Simple oracle text: o:flying."""
        parser = QueryParser()
        result = parser.parse("o:flying")

        assert result.filters["oracle_text"] == ["flying"]

    def test_parse_oracle_quoted(self):
        """Quoted oracle text: o:"enters the battlefield"."""
        parser = QueryParser()
        result = parser.parse('o:"enters the battlefield"')

        assert result.filters["oracle_text"] == ["enters the battlefield"]

    def test_parse_oracle_alias(self):
        """Oracle alias: oracle:draw."""
        parser = QueryParser()
        result = parser.parse("oracle:draw")

        assert result.filters["oracle_text"] == ["draw"]


class TestQueryParserSet:
    """Test set queries."""

    def test_parse_set(self):
        """Set filter: set:neo."""
        parser = QueryParser()
        result = parser.parse("set:neo")

        assert result.filters["set"] == "neo"

    def test_parse_set_alias_e(self):
        """Set alias: e:m19."""
        parser = QueryParser()
        result = parser.parse("e:m19")

        assert result.filters["set"] == "m19"

    def test_parse_set_alias_s(self):
        """Set alias: s:cmd."""
        parser = QueryParser()
        result = parser.parse("s:cmd")

        assert result.filters["set"] == "cmd"


class TestQueryParserRarity:
    """Test rarity queries."""

    def test_parse_rarity_full(self):
        """Full rarity name: r:mythic."""
        parser = QueryParser()
        result = parser.parse("r:mythic")

        assert result.filters["rarity"] == "mythic"

    def test_parse_rarity_short(self):
        """Short rarity: r:m."""
        parser = QueryParser()
        result = parser.parse("r:m")

        assert result.filters["rarity"] == "mythic"

    def test_parse_rarity_alias(self):
        """Rarity alias: rarity:rare."""
        parser = QueryParser()
        result = parser.parse("rarity:rare")

        assert result.filters["rarity"] == "rare"

    def test_parse_all_rarities(self):
        """Test all rarity values."""
        parser = QueryParser()

        for rarity in ["common", "uncommon", "rare", "mythic"]:
            result = parser.parse(f"r:{rarity}")
            assert result.filters["rarity"] == rarity


class TestQueryParserBooleanOperators:
    """Test boolean operators (AND, OR, NOT)."""

    def test_parse_implicit_and(self):
        """Implicit AND: c:blue t:instant."""
        parser = QueryParser()
        result = parser.parse("c:blue t:instant")

        # Should have both filters
        assert "colors" in result.filters
        assert "type" in result.filters

    def test_parse_explicit_or(self):
        """Explicit OR: c:blue OR c:red."""
        parser = QueryParser()
        result = parser.parse("c:blue OR c:red")

        # Result should indicate OR operation
        assert result.has_or_clause
        assert len(result.or_groups) >= 2

    def test_parse_negation(self):
        """Negation: -t:creature."""
        parser = QueryParser()
        result = parser.parse("-t:creature")

        assert result.filters["type_not"] == ["creature"]

    def test_parse_complex_boolean(self):
        """Complex: c:blue t:instant -cmc:0."""
        parser = QueryParser()
        result = parser.parse("c:blue t:instant -cmc:0")

        assert "colors" in result.filters
        assert result.filters["type"] == ["instant"]
        assert result.filters.get("cmc_not") == {"operator": "=", "value": 0}

    def test_parse_parentheses(self):
        """Parentheses grouping: (c:blue OR c:red) t:instant."""
        parser = QueryParser()
        result = parser.parse("(c:blue OR c:red) t:instant")

        # Should group the OR clause and AND with type
        assert "type" in result.filters
        assert result.has_or_clause


class TestQueryParserColorIdentity:
    """Test color identity queries."""

    def test_parse_identity_single_color(self):
        """Color identity filter: id:r."""
        parser = QueryParser()
        result = parser.parse("id:r")

        assert result.filters["color_identity"] == {"operator": ":", "value": ["R"]}

    def test_parse_identity_multiple_colors(self):
        """Color identity filter: id:wubrg."""
        parser = QueryParser()
        result = parser.parse("id:wubrg")

        assert result.filters["color_identity"]["value"] == ["W", "U", "B", "R", "G"]

    def test_parse_identity_named_esper(self):
        """Color identity filter: id:esper (named combination)."""
        parser = QueryParser()
        result = parser.parse("id:esper")

        assert set(result.filters["color_identity"]["value"]) == {"W", "U", "B"}

    def test_parse_identity_named_grixis(self):
        """Color identity filter: identity:grixis."""
        parser = QueryParser()
        result = parser.parse("identity:grixis")

        assert set(result.filters["color_identity"]["value"]) == {"U", "B", "R"}

    def test_parse_identity_ci_alias(self):
        """Color identity filter with ci: alias."""
        parser = QueryParser()
        result = parser.parse("ci:rg")

        assert set(result.filters["color_identity"]["value"]) == {"R", "G"}

    def test_parse_identity_colorless(self):
        """Color identity filter for colorless: id:c."""
        parser = QueryParser()
        result = parser.parse("id:colorless")

        assert result.filters["color_identity"]["value"] == []

    def test_parse_identity_subset_operator(self):
        """Color identity filter with subset operator: id<=rg."""
        parser = QueryParser()
        result = parser.parse("id<=rg")

        assert result.filters["color_identity"]["operator"] == "<="
        assert set(result.filters["color_identity"]["value"]) == {"R", "G"}

    def test_parse_identity_named_guild(self):
        """Color identity filter with guild name: id:izzet."""
        parser = QueryParser()
        result = parser.parse("id:izzet")

        assert set(result.filters["color_identity"]["value"]) == {"U", "R"}


class TestQueryParserFormat:
    """Test format legality queries."""

    def test_parse_format_standard(self):
        """Format filter: f:standard."""
        parser = QueryParser()
        result = parser.parse("f:standard")

        assert result.filters["format"] == "standard"

    def test_parse_format_modern(self):
        """Format filter: f:modern."""
        parser = QueryParser()
        result = parser.parse("f:modern")

        assert result.filters["format"] == "modern"

    def test_parse_format_commander(self):
        """Format filter: f:commander."""
        parser = QueryParser()
        result = parser.parse("f:commander")

        assert result.filters["format"] == "commander"

    def test_parse_format_long_form(self):
        """Format filter with full keyword: format:legacy."""
        parser = QueryParser()
        result = parser.parse("format:legacy")

        assert result.filters["format"] == "legacy"


class TestQueryParserPowerToughness:
    """Test power and toughness queries."""

    def test_parse_power_exact(self):
        """Power filter: pow:3."""
        parser = QueryParser()
        result = parser.parse("pow:3")

        assert result.filters["power"] == {"operator": "=", "value": 3}

    def test_parse_power_greater_equal(self):
        """Power filter: pow>=4."""
        parser = QueryParser()
        result = parser.parse("pow>=4")

        assert result.filters["power"] == {"operator": ">=", "value": 4}

    def test_parse_power_less_than(self):
        """Power filter: power<2."""
        parser = QueryParser()
        result = parser.parse("power<2")

        assert result.filters["power"] == {"operator": "<", "value": 2}

    def test_parse_power_star(self):
        """Power filter with star: pow:*."""
        parser = QueryParser()
        result = parser.parse("pow:*")

        assert result.filters["power"] == {"operator": "=", "value": "*"}

    def test_parse_toughness_exact(self):
        """Toughness filter: tou:4."""
        parser = QueryParser()
        result = parser.parse("tou:4")

        assert result.filters["toughness"] == {"operator": "=", "value": 4}

    def test_parse_toughness_greater_equal(self):
        """Toughness filter: tou>=5."""
        parser = QueryParser()
        result = parser.parse("tou>=5")

        assert result.filters["toughness"] == {"operator": ">=", "value": 5}

    def test_parse_toughness_long_form(self):
        """Toughness filter with full keyword: toughness<=3."""
        parser = QueryParser()
        result = parser.parse("toughness<=3")

        assert result.filters["toughness"] == {"operator": "<=", "value": 3}


class TestQueryParserPrice:
    """Test price queries."""

    def test_parse_usd_less_than(self):
        """Price filter: usd<1."""
        parser = QueryParser()
        result = parser.parse("usd<1")

        assert result.filters["price"] == {"currency": "usd", "operator": "<", "value": 1.0}

    def test_parse_usd_greater_equal(self):
        """Price filter: usd>=10."""
        parser = QueryParser()
        result = parser.parse("usd>=10")

        assert result.filters["price"] == {"currency": "usd", "operator": ">=", "value": 10.0}

    def test_parse_usd_decimal(self):
        """Price filter with decimal: usd<0.50."""
        parser = QueryParser()
        result = parser.parse("usd<0.50")

        assert result.filters["price"] == {"currency": "usd", "operator": "<", "value": 0.50}

    def test_parse_eur_price(self):
        """Price filter in EUR: eur>=5."""
        parser = QueryParser()
        result = parser.parse("eur>=5")

        assert result.filters["price"] == {"currency": "eur", "operator": ">=", "value": 5.0}

    def test_parse_tix_price(self):
        """Price filter in TIX: tix<1."""
        parser = QueryParser()
        result = parser.parse("tix<1")

        assert result.filters["price"] == {"currency": "tix", "operator": "<", "value": 1.0}


class TestQueryParserKeyword:
    """Test keyword ability queries."""

    def test_parse_keyword_simple(self):
        """Keyword filter: kw:flying."""
        parser = QueryParser()
        result = parser.parse("kw:flying")

        assert result.filters["keyword"] == ["Flying"]

    def test_parse_keyword_title_case_normalization(self):
        """Keyword should normalize to title case."""
        parser = QueryParser()
        result = parser.parse("kw:DEATHTOUCH")

        assert result.filters["keyword"] == ["Deathtouch"]

    def test_parse_keyword_alias_keyword(self):
        """Keyword alias: keyword:vigilance."""
        parser = QueryParser()
        result = parser.parse("keyword:vigilance")

        assert result.filters["keyword"] == ["Vigilance"]

    def test_parse_keyword_alias_keywords(self):
        """Keyword alias: keywords:trample."""
        parser = QueryParser()
        result = parser.parse("keywords:trample")

        assert result.filters["keyword"] == ["Trample"]

    def test_parse_keyword_quoted(self):
        """Quoted keyword for multi-word: kw:"first strike"."""
        parser = QueryParser()
        result = parser.parse('kw:"first strike"')

        assert result.filters["keyword"] == ["First Strike"]

    def test_parse_keyword_negation(self):
        """Negated keyword: -kw:flying."""
        parser = QueryParser()
        result = parser.parse("-kw:flying")

        assert result.filters["keyword_not"] == ["Flying"]

    def test_parse_keyword_combined_with_type(self):
        """Keyword combined with type: t:creature kw:flying."""
        parser = QueryParser()
        result = parser.parse("t:creature kw:flying")

        assert result.filters["type"] == ["creature"]
        assert result.filters["keyword"] == ["Flying"]

    def test_parse_keyword_combined_with_color(self):
        """Keyword combined with color: c:white kw:vigilance."""
        parser = QueryParser()
        result = parser.parse("c:white kw:vigilance")

        assert result.filters["colors"]["value"] == ["W"]
        assert result.filters["keyword"] == ["Vigilance"]

    def test_parse_multiple_keywords(self):
        """Multiple keywords: kw:flying kw:vigilance (AND)."""
        parser = QueryParser()
        result = parser.parse("kw:flying kw:vigilance")

        assert result.filters["keyword"] == ["Flying", "Vigilance"]

    def test_parse_multiple_keywords_with_negation(self):
        """Multiple keywords with negation: kw:flying -kw:trample."""
        parser = QueryParser()
        result = parser.parse("kw:flying -kw:trample")

        assert result.filters["keyword"] == ["Flying"]
        assert result.filters["keyword_not"] == ["Trample"]


class TestQueryParserErrorHandling:
    """Test error handling and helpful messages."""

    def test_invalid_syntax_raises_error(self):
        """Invalid syntax should raise QueryError with helpful message."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("c:")  # Missing value

        assert "syntax" in str(exc_info.value).lower() or "value" in str(exc_info.value).lower()

    def test_unsupported_filter_gives_hint(self):
        """Unsupported filter should give hint about supported syntax."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("a:rebecca")  # Artist not supported yet

        error = exc_info.value
        assert error.hint is not None
        assert "supported" in error.hint.lower() or len(error.supported_syntax) > 0

    def test_error_includes_supported_syntax(self):
        """Error should include list of supported syntax."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("artist:rebecca")  # Not supported yet

        error = exc_info.value
        assert isinstance(error.supported_syntax, list)
        assert len(error.supported_syntax) > 0


class TestQueryParserComplexQueries:
    """Test complex real-world queries."""

    def test_dragon_with_flying(self):
        """Find dragons with flying: t:dragon o:flying."""
        parser = QueryParser()
        result = parser.parse("t:dragon o:flying")

        assert result.filters["type"] == ["dragon"]
        assert result.filters["oracle_text"] == ["flying"]

    def test_blue_instant_low_cmc(self):
        """Blue instants CMC 2 or less: c:blue t:instant cmc<=2."""
        parser = QueryParser()
        result = parser.parse("c:blue t:instant cmc<=2")

        assert result.filters["colors"]["value"] == ["U"]
        assert result.filters["type"] == ["instant"]
        assert result.filters["cmc"]["operator"] == "<="
        assert result.filters["cmc"]["value"] == 2

    def test_multicolor_legendary(self):
        """Multicolor legendary creatures: c>=ur t:"legendary creature"."""
        parser = QueryParser()
        result = parser.parse('c>=ur t:"legendary creature"')

        assert set(result.filters["colors"]["value"]) == {"U", "R"}
        assert result.filters["colors"]["operator"] == ">="
        assert result.filters["type"] == ["legendary creature"]

    def test_mythic_from_set(self):
        """Mythics from specific set: set:m19 r:mythic."""
        parser = QueryParser()
        result = parser.parse("set:m19 r:mythic")

        assert result.filters["set"] == "m19"
        assert result.filters["rarity"] == "mythic"


class TestParsedQueryObject:
    """Test ParsedQuery object properties."""

    def test_parsed_query_to_string(self):
        """ParsedQuery should have readable string representation."""
        parser = QueryParser()
        result = parser.parse("c:blue t:instant")

        string_repr = str(result)
        assert "blue" in string_repr.lower() or "U" in string_repr
        assert "instant" in string_repr.lower()

    def test_parsed_query_is_empty(self):
        """Empty query should be detectable."""
        parser = QueryParser()
        result = parser.parse("")

        assert result.is_empty

    def test_parsed_query_filter_count(self):
        """Should track number of filters."""
        parser = QueryParser()
        result = parser.parse("c:blue t:instant cmc:2")

        assert result.filter_count >= 3
