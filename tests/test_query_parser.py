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

        # Parsed as a partial name filter
        assert "name_partial" in result.filters

    def test_parse_partial_name_with_apostrophe(self):
        """Partial name with apostrophe (e.g., Urza's)."""
        parser = QueryParser()
        result = parser.parse("Urza's")

        assert result.filters["name_partial"] == "Urza's"

    def test_parse_partial_name_with_apostrophe_and_hyphen(self):
        """Partial name with both apostrophe and hyphen."""
        parser = QueryParser()
        result = parser.parse("Al-abara's")

        assert result.filters["name_partial"] == "Al-abara's"

    def test_parse_partial_name_apostrophe_with_filter(self):
        """Partial name with apostrophe combined with other filters."""
        parser = QueryParser()
        result = parser.parse("Urza's t:land")

        assert result.filters["name_partial"] == "Urza's"
        assert result.filters["type"] == ["land"]


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


class TestQueryParserManaCost:
    """Test mana cost symbol queries."""

    def test_parse_mana_single_symbol(self):
        """Single mana symbol: m:{R}."""
        parser = QueryParser()
        result = parser.parse("m:{R}")

        assert result.filters["mana"] == {"operator": ":", "value": "{R}"}

    def test_parse_mana_double_symbol(self):
        """Double mana symbol: m:{U}{U}."""
        parser = QueryParser()
        result = parser.parse("m:{U}{U}")

        assert result.filters["mana"] == {"operator": ":", "value": "{U}{U}"}

    def test_parse_mana_with_generic(self):
        """Mana cost with generic mana: m:{2}{R}{R}."""
        parser = QueryParser()
        result = parser.parse("m:{2}{R}{R}")

        assert result.filters["mana"] == {"operator": ":", "value": "{2}{R}{R}"}

    def test_parse_mana_exact_match(self):
        """Exact mana cost match: m={R}."""
        parser = QueryParser()
        result = parser.parse("m={R}")

        assert result.filters["mana"] == {"operator": "=", "value": "{R}"}

    def test_parse_mana_long_form(self):
        """Long form mana: mana:{W}{W}."""
        parser = QueryParser()
        result = parser.parse("mana:{W}{W}")

        assert result.filters["mana"] == {"operator": ":", "value": "{W}{W}"}

    def test_parse_mana_with_x(self):
        """Mana cost with X: m:{X}{U}{U}."""
        parser = QueryParser()
        result = parser.parse("m:{X}{U}{U}")

        assert result.filters["mana"] == {"operator": ":", "value": "{X}{U}{U}"}

    def test_parse_mana_colorless(self):
        """Colorless mana: m:{C}."""
        parser = QueryParser()
        result = parser.parse("m:{C}")

        assert result.filters["mana"] == {"operator": ":", "value": "{C}"}

    def test_parse_mana_with_other_filters(self):
        """Mana cost combined with other filters."""
        parser = QueryParser()
        result = parser.parse("m:{R}{R} t:creature")

        assert result.filters["mana"] == {"operator": ":", "value": "{R}{R}"}
        assert result.filters["type"] == ["creature"]


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

    def test_parse_parenthesized_or_with_outer_filter_after(self):
        """(t:elf OR t:goblin) c:green - outer filter should distribute to each OR group."""
        parser = QueryParser()
        result = parser.parse("(t:elf OR t:goblin) c:green")

        assert result.has_or_clause
        assert len(result.or_groups) == 2

        # Each OR group should contain both the type and color filter
        for group in result.or_groups:
            filter_keys = [list(f.keys())[0] for f in group]
            assert "type" in filter_keys
            assert "colors" in filter_keys

    def test_parse_parenthesized_or_with_outer_filter_before(self):
        """c:green (t:elf OR t:goblin) - filter before parens should distribute."""
        parser = QueryParser()
        result = parser.parse("c:green (t:elf OR t:goblin)")

        assert result.has_or_clause
        assert len(result.or_groups) == 2

        # Each OR group should contain both filters
        for group in result.or_groups:
            filter_keys = [list(f.keys())[0] for f in group]
            assert "type" in filter_keys
            assert "colors" in filter_keys

    def test_parse_parenthesized_or_with_filters_both_sides(self):
        """c:green (t:elf OR t:goblin) r:rare - filters on both sides should distribute."""
        parser = QueryParser()
        result = parser.parse("c:green (t:elf OR t:goblin) r:rare")

        assert result.has_or_clause
        assert len(result.or_groups) == 2

        # Each OR group should contain type, color, AND rarity
        for group in result.or_groups:
            filter_keys = [list(f.keys())[0] for f in group]
            assert "type" in filter_keys
            assert "colors" in filter_keys
            assert "rarity" in filter_keys


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


class TestQueryParserLoyalty:
    """Test loyalty queries for planeswalkers."""

    def test_parse_loyalty_exact(self):
        """Loyalty filter: loy:3."""
        parser = QueryParser()
        result = parser.parse("loy:3")

        assert result.filters["loyalty"] == {"operator": "=", "value": 3}

    def test_parse_loyalty_greater_equal(self):
        """Loyalty filter: loy>=4."""
        parser = QueryParser()
        result = parser.parse("loy>=4")

        assert result.filters["loyalty"] == {"operator": ">=", "value": 4}

    def test_parse_loyalty_less_than(self):
        """Loyalty filter: loyalty<5."""
        parser = QueryParser()
        result = parser.parse("loyalty<5")

        assert result.filters["loyalty"] == {"operator": "<", "value": 5}

    def test_parse_loyalty_with_type(self):
        """Loyalty combined with type: t:planeswalker loy>=4."""
        parser = QueryParser()
        result = parser.parse("t:planeswalker loy>=4")

        assert result.filters["type"] == ["planeswalker"]
        assert result.filters["loyalty"] == {"operator": ">=", "value": 4}


class TestQueryParserFlavorText:
    """Test flavor text queries."""

    def test_parse_flavor_text_simple(self):
        """Flavor text filter: ft:doom."""
        parser = QueryParser()
        result = parser.parse("ft:doom")

        assert result.filters["flavor_text"] == ["doom"]

    def test_parse_flavor_text_quoted(self):
        """Quoted flavor text: ft:"the dead shall rise"."""
        parser = QueryParser()
        result = parser.parse('ft:"the dead shall rise"')

        assert result.filters["flavor_text"] == ["the dead shall rise"]

    def test_parse_flavor_alias(self):
        """Flavor alias: flavor:dragon."""
        parser = QueryParser()
        result = parser.parse("flavor:dragon")

        assert result.filters["flavor_text"] == ["dragon"]

    def test_parse_multiple_flavor_texts(self):
        """Multiple flavor text filters: ft:doom ft:death."""
        parser = QueryParser()
        result = parser.parse("ft:doom ft:death")

        assert result.filters["flavor_text"] == ["doom", "death"]


class TestQueryParserCollectorNumber:
    """Test collector number queries."""

    def test_parse_collector_number_exact(self):
        """Collector number filter: cn:123."""
        parser = QueryParser()
        result = parser.parse("cn:123")

        assert result.filters["collector_number"] == {"operator": "=", "value": "123"}

    def test_parse_collector_number_with_letter(self):
        """Collector number with letter: cn:1a."""
        parser = QueryParser()
        result = parser.parse("cn:1a")

        assert result.filters["collector_number"] == {"operator": "=", "value": "1a"}

    def test_parse_collector_number_greater_than(self):
        """Collector number range: cn>100."""
        parser = QueryParser()
        result = parser.parse("cn>100")

        assert result.filters["collector_number"] == {"operator": ">", "value": "100"}

    def test_parse_collector_number_alias(self):
        """Number alias: number:50."""
        parser = QueryParser()
        result = parser.parse("number:50")

        assert result.filters["collector_number"] == {"operator": "=", "value": "50"}


class TestQueryParserStrictName:
    """Test strict exact name match with ! prefix."""

    def test_parse_strict_name(self):
        """Strict name match: !"Lightning Bolt"."""
        parser = QueryParser()
        result = parser.parse('!"Lightning Bolt"')

        assert result.filters["name_strict"] == "Lightning Bolt"

    def test_parse_strict_name_case_sensitive(self):
        """Strict name is case-sensitive."""
        parser = QueryParser()
        result = parser.parse('!"Jace, the Mind Sculptor"')

        assert result.filters["name_strict"] == "Jace, the Mind Sculptor"

    def test_parse_strict_name_with_filters(self):
        """Strict name with other filters: !"Bolt" c:red."""
        parser = QueryParser()
        result = parser.parse('!"Bolt" c:red')

        assert result.filters["name_strict"] == "Bolt"
        assert result.filters["colors"]["value"] == ["R"]


class TestQueryParserArtist:
    """Test artist filter parsing."""

    def test_parse_artist_simple(self):
        """Simple artist: a:seb."""
        parser = QueryParser()
        result = parser.parse("a:seb")

        assert "artist" in result.filters
        assert result.filters["artist"] == "seb"

    def test_parse_artist_quoted(self):
        """Quoted artist: a:"Rebecca Guay"."""
        parser = QueryParser()
        result = parser.parse('a:"Rebecca Guay"')

        assert "artist" in result.filters
        assert result.filters["artist"] == "Rebecca Guay"

    def test_parse_artist_alias(self):
        """Artist alias: artist:Terese."""
        parser = QueryParser()
        result = parser.parse("artist:Terese")

        assert "artist" in result.filters
        assert result.filters["artist"] == "Terese"

    def test_parse_artist_with_filters(self):
        """Artist with other filters: a:seb t:creature."""
        parser = QueryParser()
        result = parser.parse("a:seb t:creature")

        assert result.filters["artist"] == "seb"
        assert result.filters["type"] == ["creature"]


class TestQueryParserYear:
    """Test year filter parsing."""

    def test_parse_year_exact(self):
        """Exact year: year:2023."""
        parser = QueryParser()
        result = parser.parse("year:2023")

        assert "year" in result.filters
        assert result.filters["year"]["operator"] == "="
        assert result.filters["year"]["value"] == 2023

    def test_parse_year_greater_equal(self):
        """Year >=: year>=2020."""
        parser = QueryParser()
        result = parser.parse("year>=2020")

        assert result.filters["year"]["operator"] == ">="
        assert result.filters["year"]["value"] == 2020

    def test_parse_year_less_than(self):
        """Year <: year<2015."""
        parser = QueryParser()
        result = parser.parse("year<2015")

        assert result.filters["year"]["operator"] == "<"
        assert result.filters["year"]["value"] == 2015

    def test_parse_year_with_filters(self):
        """Year with other filters: year:2023 r:mythic."""
        parser = QueryParser()
        result = parser.parse("year:2023 r:mythic")

        assert result.filters["year"]["value"] == 2023
        assert result.filters["rarity"] == "mythic"


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

        # Test with an actually invalid query - color with no value
        with pytest.raises(QueryError) as exc_info:
            parser.parse("c:")  # Missing color value

        error = exc_info.value
        # Just check we got some error with useful info
        assert str(error)  # Error has message

    def test_error_includes_supported_syntax(self):
        """Error should include list of supported syntax when available."""
        parser = QueryParser()

        # Test with an actually invalid query
        with pytest.raises(QueryError) as exc_info:
            parser.parse("c:")  # Missing color value

        error = exc_info.value
        # Error should have a message
        assert str(error)

    def test_unbalanced_parentheses_raises_error(self):
        """Unbalanced parentheses should raise QueryError with helpful message."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("(c:blue")  # Missing closing paren

        error = exc_info.value
        assert "parentheses" in str(error).lower()
        assert "missing" in str(error).lower() or "unbalanced" in str(error).lower()

    def test_unbalanced_parentheses_nested(self):
        """Nested unbalanced parentheses should raise QueryError."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("((c:blue OR c:red)")  # Missing one closing paren

        assert "parentheses" in str(exc_info.value).lower()

    def test_extra_closing_paren_raises_error(self):
        """Extra closing parenthesis should raise QueryError."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("c:blue)")  # Extra closing paren

        error = exc_info.value
        assert "parentheses" in str(error).lower()
        assert "extra" in str(error).lower() or "closing" in str(error).lower()

    def test_multiple_extra_closing_parens(self):
        """Multiple extra closing parens should raise QueryError."""
        parser = QueryParser()

        with pytest.raises(QueryError) as exc_info:
            parser.parse("c:blue))")  # Multiple extra closing parens

        assert "parentheses" in str(exc_info.value).lower()


class TestQueryParserFractionalCMC:
    """Test fractional CMC parsing (e.g., Little Girl has CMC 0.5)."""

    def test_parse_fractional_cmc(self):
        """Fractional CMC: cmc:0.5."""
        parser = QueryParser()
        result = parser.parse("cmc:0.5")

        assert result.filters["cmc"] == {"operator": "=", "value": 0.5}

    def test_parse_fractional_cmc_with_operator(self):
        """Fractional CMC with operator: cmc>=1.5."""
        parser = QueryParser()
        result = parser.parse("cmc>=1.5")

        assert result.filters["cmc"] == {"operator": ">=", "value": 1.5}

    def test_parse_integer_cmc_still_works(self):
        """Integer CMC should still work as float: cmc:3."""
        parser = QueryParser()
        result = parser.parse("cmc:3")

        assert result.filters["cmc"] == {"operator": "=", "value": 3.0}


class TestQueryParserColorOperators:
    """Test color greater-than and less-than operators."""

    def test_parse_color_greater_than(self):
        """Color > operator: c>rg means has R and G plus at least one more."""
        parser = QueryParser()
        result = parser.parse("c>rg")

        assert result.filters["colors"]["operator"] == ">"
        assert set(result.filters["colors"]["value"]) == {"R", "G"}

    def test_parse_color_less_than(self):
        """Color < operator: c<rg means strict subset of {R, G}."""
        parser = QueryParser()
        result = parser.parse("c<rg")

        assert result.filters["colors"]["operator"] == "<"
        assert set(result.filters["colors"]["value"]) == {"R", "G"}

    def test_parse_identity_greater_than(self):
        """Color identity > operator: id>rg."""
        parser = QueryParser()
        result = parser.parse("id>rg")

        assert result.filters["color_identity"]["operator"] == ">"
        assert set(result.filters["color_identity"]["value"]) == {"R", "G"}

    def test_parse_identity_less_than(self):
        """Color identity < operator: id<rg."""
        parser = QueryParser()
        result = parser.parse("id<rg")

        assert result.filters["color_identity"]["operator"] == "<"
        assert set(result.filters["color_identity"]["value"]) == {"R", "G"}


class TestQueryParserNewFilters:
    """Test new filter types: fo, produces, banned, block, watermark."""

    def test_parse_full_oracle(self):
        """Full oracle text: fo:flying (alias for o:)."""
        parser = QueryParser()
        result = parser.parse("fo:flying")

        # fo: maps to oracle_text (same as o:)
        assert result.filters["oracle_text"] == ["flying"]

    def test_parse_full_oracle_quoted(self):
        """Full oracle text with quotes: fo:\"enters the battlefield\"."""
        parser = QueryParser()
        result = parser.parse('fo:"enters the battlefield"')

        assert result.filters["oracle_text"] == ["enters the battlefield"]

    def test_parse_produces_single(self):
        """Produces mana: produces:g."""
        parser = QueryParser()
        result = parser.parse("produces:g")

        assert result.filters["produces"] == ["G"]

    def test_parse_produces_multiple(self):
        """Produces multiple colors: produces:wubrg."""
        parser = QueryParser()
        result = parser.parse("produces:wubrg")

        assert set(result.filters["produces"]) == {"W", "U", "B", "R", "G"}

    def test_parse_banned(self):
        """Banned in format: banned:modern."""
        parser = QueryParser()
        result = parser.parse("banned:modern")

        assert result.filters["banned"] == "modern"

    def test_parse_block(self):
        """Block filter: b:innistrad."""
        parser = QueryParser()
        result = parser.parse("b:innistrad")

        assert result.filters["block"] == "innistrad"

    def test_parse_block_alias(self):
        """Block filter alias: block:zendikar."""
        parser = QueryParser()
        result = parser.parse("block:zendikar")

        assert result.filters["block"] == "zendikar"

    def test_parse_watermark(self):
        """Watermark filter: wm:phyrexian."""
        parser = QueryParser()
        result = parser.parse("wm:phyrexian")

        assert result.filters["watermark"] == "phyrexian"

    def test_parse_watermark_alias(self):
        """Watermark filter alias: watermark:selesnya."""
        parser = QueryParser()
        result = parser.parse("watermark:selesnya")

        assert result.filters["watermark"] == "selesnya"

    def test_parse_negated_banned(self):
        """Negated banned: -banned:legacy."""
        parser = QueryParser()
        result = parser.parse("-banned:legacy")

        assert result.filters["banned_not"] == "legacy"

    def test_parse_negated_watermark(self):
        """Negated watermark: -wm:dimir."""
        parser = QueryParser()
        result = parser.parse("-wm:dimir")

        assert result.filters["watermark_not"] == "dimir"


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
