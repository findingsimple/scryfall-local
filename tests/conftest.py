"""Shared test fixtures for Scryfall Local MCP Server."""

from decimal import Decimal

import pytest
from typing import Any


@pytest.fixture
def sample_cards() -> list[dict[str, Any]]:
    """Sample card data for testing - covers various card types and attributes.

    Design: Only cards with keyword abilities have the 'keywords' field populated.
    This matches Scryfall's data model where instants/sorceries/artifacts without
    keyword abilities don't have keywords. Cards in this fixture:
    - Lightning Bolt, Counterspell, Dark Ritual: No keywords (spell effects, not abilities)
    - Shivan Dragon, Serra Angel, Nicol Bolas: Have Flying/Vigilance keywords
    - Llanowar Elves: No keywords (mana ability is not a keyword)
    - Sol Ring: No keywords (artifact with activated ability)
    """
    return [
        {
            "id": "e2d1f479-3c2b-4b2a-8c9a-1a2b3c4d5e6f",
            "oracle_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "common",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/e/2/e2d1f479.jpg",
                "normal": "https://cards.scryfall.io/normal/front/e/2/e2d1f479.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "1.50", "usd_foil": "3.00"},
        },
        {
            "id": "f1e2d3c4-b5a6-9870-fedc-ba0987654321",
            "oracle_id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
            "name": "Counterspell",
            "mana_cost": "{U}{U}",
            "cmc": 2.0,
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "colors": ["U"],
            "color_identity": ["U"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "uncommon",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/f/1/f1e2d3c4.jpg",
                "normal": "https://cards.scryfall.io/normal/front/f/1/f1e2d3c4.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "2.00", "usd_foil": "5.00"},
        },
        {
            "id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
            "oracle_id": "c3d4e5f6-a7b8-9012-cdef-345678901234",
            "name": "Shivan Dragon",
            "mana_cost": "{4}{R}{R}",
            "cmc": 6.0,
            "type_line": "Creature — Dragon",
            "oracle_text": "Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn.",
            "keywords": ["Flying"],
            "power": "5",
            "toughness": "5",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "rare",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/a/1/a1b2c3d4.jpg",
                "normal": "https://cards.scryfall.io/normal/front/a/1/a1b2c3d4.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "5.00", "usd_foil": None},
        },
        {
            "id": "b2c3d4e5-f6a7-8901-2345-678901bcdef0",
            "oracle_id": "d4e5f6a7-b8c9-0123-def0-456789012345",
            "name": "Serra Angel",
            "mana_cost": "{3}{W}{W}",
            "cmc": 5.0,
            "type_line": "Creature — Angel",
            "oracle_text": "Flying, vigilance",
            "keywords": ["Flying", "Vigilance"],
            "power": "4",
            "toughness": "4",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "uncommon",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/b/2/b2c3d4e5.jpg",
                "normal": "https://cards.scryfall.io/normal/front/b/2/b2c3d4e5.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "1.00", "usd_foil": "2.50"},
        },
        {
            "id": "c3d4e5f6-a7b8-9012-3456-789012cdef01",
            "oracle_id": "e5f6a7b8-c9d0-1234-ef01-567890123456",
            "name": "Llanowar Elves",
            "mana_cost": "{G}",
            "cmc": 1.0,
            "type_line": "Creature — Elf Druid",
            "oracle_text": "{T}: Add {G}.",
            "power": "1",
            "toughness": "1",
            "colors": ["G"],
            "color_identity": ["G"],
            "produced_mana": ["G"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "common",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/c/3/c3d4e5f6.jpg",
                "normal": "https://cards.scryfall.io/normal/front/c/3/c3d4e5f6.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "0.50", "usd_foil": "1.00"},
        },
        {
            "id": "d4e5f6a7-b8c9-0123-4567-890123def012",
            "oracle_id": "f6a7b8c9-d0e1-2345-f012-678901234567",
            "name": "Dark Ritual",
            "mana_cost": "{B}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Add {B}{B}{B}.",
            "colors": ["B"],
            "color_identity": ["B"],
            "produced_mana": ["B"],
            "set": "leb",
            "set_name": "Limited Edition Beta",
            "rarity": "common",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/d/4/d4e5f6a7.jpg",
                "normal": "https://cards.scryfall.io/normal/front/d/4/d4e5f6a7.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "0.75", "usd_foil": "1.50"},
        },
        {
            "id": "e5f6a7b8-c9d0-1234-5678-901234ef0123",
            "oracle_id": "a7b8c9d0-e1f2-3456-0123-789012345678",
            "name": "Nicol Bolas, the Ravager",
            "mana_cost": "{1}{U}{B}{R}",
            "cmc": 4.0,
            "type_line": "Legendary Creature — Elder Dragon",
            "oracle_text": "Flying\nWhen Nicol Bolas, the Ravager enters the battlefield, each opponent discards a card.\n{4}{U}{B}{R}: Exile Nicol Bolas, the Ravager, then return him to the battlefield transformed under his owner's control. Activate only as a sorcery.",
            "keywords": ["Flying"],
            "power": "4",
            "toughness": "4",
            "colors": ["U", "B", "R"],
            "color_identity": ["U", "B", "R"],
            "set": "m19",
            "set_name": "Core Set 2019",
            "rarity": "mythic",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/e/5/e5f6a7b8.jpg",
                "normal": "https://cards.scryfall.io/normal/front/e/5/e5f6a7b8.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
                "vintage": "legal",
                "commander": "legal",
            },
            "prices": {"usd": "15.00", "usd_foil": "25.00"},
        },
        {
            "id": "f6a7b8c9-d0e1-2345-6789-012345f01234",
            "oracle_id": "b8c9d0e1-f2a3-4567-1234-890123456789",
            "name": "Sol Ring",
            "mana_cost": "{1}",
            "cmc": 1.0,
            "type_line": "Artifact",
            "oracle_text": "{T}: Add {C}{C}.",
            "colors": [],
            "color_identity": [],
            "produced_mana": ["C"],
            "set": "cmd",
            "set_name": "Commander",
            "rarity": "uncommon",
            "image_uris": {
                "small": "https://cards.scryfall.io/small/front/f/6/f6a7b8c9.jpg",
                "normal": "https://cards.scryfall.io/normal/front/f/6/f6a7b8c9.jpg",
            },
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "banned",
                "vintage": "restricted",
                "commander": "legal",
            },
            "prices": {"usd": "3.00", "usd_foil": "8.00"},
        },
    ]


@pytest.fixture
def lightning_bolt(sample_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Single card fixture for Lightning Bolt."""
    return sample_cards[0]


@pytest.fixture
def blue_instant(sample_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Single card fixture for Counterspell (blue instant)."""
    return sample_cards[1]


@pytest.fixture
def dragon(sample_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Single card fixture for Shivan Dragon (creature with flying)."""
    return sample_cards[2]


@pytest.fixture
def multicolor_card(sample_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Single card fixture for Nicol Bolas (multicolor legendary)."""
    return sample_cards[6]


@pytest.fixture
def colorless_artifact(sample_cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Single card fixture for Sol Ring (colorless artifact)."""
    return sample_cards[7]


@pytest.fixture
def sample_cards_with_keywords() -> list[dict[str, Any]]:
    """Cards with various keywords for testing keyword filtering."""
    return [
        {
            "id": "kw-test-flying",
            "oracle_id": "kw-oracle-flying",
            "name": "Flying Test Creature",
            "mana_cost": "{1}{W}",
            "cmc": 2.0,
            "type_line": "Creature — Bird",
            "oracle_text": "Flying",
            "keywords": ["Flying"],
            "power": "2",
            "toughness": "1",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "common",
            "image_uris": {},
            "legalities": {"commander": "legal"},
            "prices": {},
        },
        {
            "id": "kw-test-deathtouch",
            "oracle_id": "kw-oracle-deathtouch",
            "name": "Deathtouch Test Creature",
            "mana_cost": "{B}",
            "cmc": 1.0,
            "type_line": "Creature — Snake",
            "oracle_text": "Deathtouch",
            "keywords": ["Deathtouch"],
            "power": "1",
            "toughness": "1",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "common",
            "image_uris": {},
            "legalities": {"commander": "legal"},
            "prices": {},
        },
        {
            "id": "kw-test-multi",
            "oracle_id": "kw-oracle-multi",
            "name": "Multi-Keyword Angel",
            "mana_cost": "{3}{W}{W}",
            "cmc": 5.0,
            "type_line": "Creature — Angel",
            "oracle_text": "Flying, vigilance, lifelink",
            "keywords": ["Flying", "Vigilance", "Lifelink"],
            "power": "4",
            "toughness": "4",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "rare",
            "image_uris": {},
            "legalities": {"commander": "legal"},
            "prices": {},
        },
        {
            "id": "kw-test-first-strike",
            "oracle_id": "kw-oracle-first-strike",
            "name": "First Strike Knight",
            "mana_cost": "{1}{W}",
            "cmc": 2.0,
            "type_line": "Creature — Human Knight",
            "oracle_text": "First strike",
            "keywords": ["First Strike"],
            "power": "2",
            "toughness": "2",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "common",
            "image_uris": {},
            "legalities": {"commander": "legal"},
            "prices": {},
        },
        {
            "id": "kw-test-none",
            "oracle_id": "kw-oracle-none",
            "name": "No Keywords Spell",
            "mana_cost": "{U}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Draw a card.",
            "keywords": [],
            "colors": ["U"],
            "color_identity": ["U"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "common",
            "image_uris": {},
            "legalities": {"commander": "legal"},
            "prices": {},
        },
    ]


@pytest.fixture
def cards_with_decimal_values() -> list[dict[str, Any]]:
    """Cards with Decimal values simulating ijson streaming parser output."""
    return [
        {
            "id": "decimal-test-1",
            "oracle_id": "decimal-oracle-1",
            "name": "Decimal Test Card",
            "mana_cost": "{2}{R}",
            "cmc": Decimal("3.0"),  # ijson returns Decimal for numbers
            "type_line": "Creature — Test",
            "oracle_text": "Test card with Decimal CMC",
            "power": "2",
            "toughness": "2",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "common",
            "image_uris": {"normal": "https://example.com/image.jpg"},
            "legalities": {"commander": "legal"},
            "prices": {"usd": "1.50", "eur": "1.25"},
        },
        {
            "id": "decimal-test-2",
            "oracle_id": "decimal-oracle-2",
            "name": "Another Decimal Card",
            "mana_cost": "{X}{U}{U}",
            "cmc": Decimal("2.0"),
            "type_line": "Instant",
            "oracle_text": "Another test with Decimal",
            "colors": ["U"],
            "color_identity": ["U"],
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "rare",
            "image_uris": {},
            "legalities": {"modern": "legal"},
            "prices": {},
        },
    ]


@pytest.fixture
def double_faced_cards() -> list[dict[str, Any]]:
    """Double-faced cards for testing card_faces extraction.

    These cards have layouts where data is stored in card_faces[] instead of
    at the top level. The fixture covers:
    - Transform (Delver of Secrets)
    - Modal DFC (Shatterskull Smashing)
    - Split (Fire // Ice)
    - Adventure (Bonecrusher Giant)
    """
    return [
        # Transform card - creature that flips to another creature
        {
            "id": "dfc-transform-delver",
            "oracle_id": "dfc-oracle-delver",
            "name": "Delver of Secrets // Insectile Aberration",
            "layout": "transform",
            "mana_cost": None,  # At top level it's null
            "cmc": 1.0,
            "type_line": None,  # At top level it's null
            "oracle_text": None,  # At top level it's null
            "power": None,
            "toughness": None,
            "colors": [],  # Empty at top level for some transform cards
            "color_identity": ["U"],
            "keywords": ["Transform"],
            "set": "isd",
            "set_name": "Innistrad",
            "rarity": "common",
            "card_faces": [
                {
                    "name": "Delver of Secrets",
                    "mana_cost": "{U}",
                    "type_line": "Creature — Human Wizard",
                    "oracle_text": "At the beginning of your upkeep, look at the top card of your library. You may reveal that card. If an instant or sorcery card is revealed this way, transform Delver of Secrets.",
                    "power": "1",
                    "toughness": "1",
                    "colors": ["U"],
                    "flavor_text": "\"If my hypothesis is correct...\""
                },
                {
                    "name": "Insectile Aberration",
                    "mana_cost": "",
                    "type_line": "Creature — Human Insect",
                    "oracle_text": "Flying",
                    "power": "3",
                    "toughness": "2",
                    "colors": ["U"],
                    "flavor_text": "\"...I will be both famous and dead.\""
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "2.00"},
        },
        # Modal DFC - land on back, instant/sorcery on front
        {
            "id": "dfc-mdfc-shatterskull",
            "oracle_id": "dfc-oracle-shatterskull",
            "name": "Shatterskull Smashing // Shatterskull, the Hammer Pass",
            "layout": "modal_dfc",
            "mana_cost": None,
            "cmc": 2.0,
            "type_line": None,
            "oracle_text": None,
            "power": None,
            "toughness": None,
            "colors": [],
            "color_identity": ["R"],
            "keywords": [],
            "set": "znr",
            "set_name": "Zendikar Rising",
            "rarity": "mythic",
            "card_faces": [
                {
                    "name": "Shatterskull Smashing",
                    "mana_cost": "{X}{R}{R}",
                    "type_line": "Sorcery",
                    "oracle_text": "Shatterskull Smashing deals X damage divided as you choose among up to two target creatures and/or planeswalkers. If X is 6 or more, Shatterskull Smashing deals twice X damage divided as you choose among them instead.",
                    "colors": ["R"],
                },
                {
                    "name": "Shatterskull, the Hammer Pass",
                    "mana_cost": "",
                    "type_line": "Land",
                    "oracle_text": "As Shatterskull, the Hammer Pass enters the battlefield, you may pay 3 life. If you don't, it enters the battlefield tapped.\n{T}: Add {R}.",
                    "colors": [],
                }
            ],
            "image_uris": {},
            "legalities": {"standard": "not_legal", "modern": "legal", "commander": "legal"},
            "prices": {"usd": "8.00"},
        },
        # Split card - two spells on one card
        {
            "id": "dfc-split-fire-ice",
            "oracle_id": "dfc-oracle-fire-ice",
            "name": "Fire // Ice",
            "layout": "split",
            "mana_cost": "{1}{R} // {1}{U}",  # Split cards often have combined mana cost
            "cmc": 4.0,
            "type_line": "Instant // Instant",
            "oracle_text": None,  # Often null, in faces
            "colors": ["R", "U"],  # Combined colors at top level
            "color_identity": ["R", "U"],
            "keywords": [],
            "set": "mh2",
            "set_name": "Modern Horizons 2",
            "rarity": "rare",
            "card_faces": [
                {
                    "name": "Fire",
                    "mana_cost": "{1}{R}",
                    "type_line": "Instant",
                    "oracle_text": "Fire deals 2 damage divided as you choose among one or two targets.",
                    "colors": ["R"],
                },
                {
                    "name": "Ice",
                    "mana_cost": "{1}{U}",
                    "type_line": "Instant",
                    "oracle_text": "Tap target permanent.\nDraw a card.",
                    "colors": ["U"],
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "1.50"},
        },
        # Adventure card - creature with adventure spell
        {
            "id": "dfc-adventure-bonecrusher",
            "oracle_id": "dfc-oracle-bonecrusher",
            "name": "Bonecrusher Giant // Stomp",
            "layout": "adventure",
            "mana_cost": None,
            "cmc": 3.0,
            "type_line": None,
            "oracle_text": None,
            "power": None,
            "toughness": None,
            "colors": [],
            "color_identity": ["R"],
            "keywords": ["Adventure"],
            "set": "eld",
            "set_name": "Throne of Eldraine",
            "rarity": "rare",
            "card_faces": [
                {
                    "name": "Bonecrusher Giant",
                    "mana_cost": "{2}{R}",
                    "type_line": "Creature — Giant",
                    "oracle_text": "Whenever Bonecrusher Giant becomes the target of a spell, Bonecrusher Giant deals 2 damage to that spell's controller.",
                    "power": "4",
                    "toughness": "3",
                    "colors": ["R"],
                },
                {
                    "name": "Stomp",
                    "mana_cost": "{1}{R}",
                    "type_line": "Instant — Adventure",
                    "oracle_text": "Damage can't be prevented this turn. Stomp deals 2 damage to any target.",
                    "colors": ["R"],
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "0.50"},
        },
        # Transform planeswalker - creature that transforms to planeswalker
        {
            "id": "dfc-transform-jace",
            "oracle_id": "dfc-oracle-jace",
            "name": "Jace, Vryn's Prodigy // Jace, Telepath Unbound",
            "layout": "transform",
            "mana_cost": None,
            "cmc": 2.0,
            "type_line": None,
            "oracle_text": None,
            "power": None,
            "toughness": None,
            "loyalty": None,  # Null at top level, back face has loyalty
            "colors": [],
            "color_identity": ["U"],
            "keywords": ["Transform"],
            "set": "ori",
            "set_name": "Magic Origins",
            "rarity": "mythic",
            "card_faces": [
                {
                    "name": "Jace, Vryn's Prodigy",
                    "mana_cost": "{1}{U}",
                    "type_line": "Legendary Creature — Human Wizard",
                    "oracle_text": "{T}: Draw a card, then discard a card. If there are five or more cards in your graveyard, exile Jace, Vryn's Prodigy, then return him to the battlefield transformed under his owner's control.",
                    "power": "0",
                    "toughness": "2",
                    "colors": ["U"],
                },
                {
                    "name": "Jace, Telepath Unbound",
                    "mana_cost": "",
                    "type_line": "Legendary Planeswalker — Jace",
                    "oracle_text": "+1: Up to one target creature gets -2/-0 until your next turn.\n−3: You may cast target instant or sorcery card from your graveyard this turn. If that spell would be put into your graveyard, exile it instead.\n−9: You get an emblem with \"Whenever you cast a spell, target opponent mills five cards.\"",
                    "colors": ["U"],
                    "loyalty": "5",
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "15.00"},
        },
    ]


@pytest.fixture
def token_creating_cards() -> list[dict[str, Any]]:
    """Cards that create tokens (with all_parts containing token references).

    These cards have all_parts arrays that reference the tokens they create.
    """
    return [
        # Creates a single type of token (Zombie)
        {
            "id": "token-test-gravecrawler",
            "oracle_id": "token-oracle-gc",
            "name": "Grave Titan",
            "mana_cost": "{4}{B}{B}",
            "cmc": 6.0,
            "type_line": "Creature — Giant",
            "oracle_text": "Deathtouch\nWhenever Grave Titan enters the battlefield or attacks, create two 2/2 black Zombie creature tokens.",
            "keywords": ["Deathtouch"],
            "power": "6",
            "toughness": "6",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "m11",
            "set_name": "Magic 2011",
            "rarity": "mythic",
            "all_parts": [
                {
                    "object": "related_card",
                    "id": "token-zombie-1",
                    "component": "token",
                    "name": "Zombie",
                    "type_line": "Token Creature — Zombie",
                    "uri": "https://api.scryfall.com/cards/token-zombie-1"
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "10.00"},
        },
        # Creates multiple types of tokens (Goblin and Soldier)
        {
            "id": "token-test-multi",
            "oracle_id": "token-oracle-multi",
            "name": "Assemble the Legion",
            "mana_cost": "{3}{R}{W}",
            "cmc": 5.0,
            "type_line": "Enchantment",
            "oracle_text": "At the beginning of your upkeep, put a muster counter on Assemble the Legion. Then create a 1/1 red and white Soldier creature token with haste for each muster counter on Assemble the Legion.",
            "keywords": [],
            "colors": ["R", "W"],
            "color_identity": ["R", "W"],
            "set": "gtc",
            "set_name": "Gatecrash",
            "rarity": "rare",
            "all_parts": [
                {
                    "object": "related_card",
                    "id": "token-soldier-1",
                    "component": "token",
                    "name": "Soldier",
                    "type_line": "Token Creature — Soldier",
                    "uri": "https://api.scryfall.com/cards/token-soldier-1"
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "2.00"},
        },
        # Card with both token and combo_piece components
        {
            "id": "token-test-siege",
            "oracle_id": "token-oracle-siege",
            "name": "Siege-Gang Commander",
            "mana_cost": "{3}{R}{R}",
            "cmc": 5.0,
            "type_line": "Creature — Goblin",
            "oracle_text": "When Siege-Gang Commander enters the battlefield, create three 1/1 red Goblin creature tokens.\n{1}{R}, Sacrifice a Goblin: Siege-Gang Commander deals 2 damage to any target.",
            "keywords": [],
            "power": "2",
            "toughness": "2",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "dom",
            "set_name": "Dominaria",
            "rarity": "rare",
            "all_parts": [
                {
                    "object": "related_card",
                    "id": "token-goblin-1",
                    "component": "token",
                    "name": "Goblin",
                    "type_line": "Token Creature — Goblin",
                    "uri": "https://api.scryfall.com/cards/token-goblin-1"
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "1.00"},
        },
        # Card with non-token all_parts (combo_piece) - should NOT populate produces_tokens
        {
            "id": "token-test-combo",
            "oracle_id": "token-oracle-combo",
            "name": "Meld Test Card",
            "mana_cost": "{2}{W}",
            "cmc": 3.0,
            "type_line": "Creature — Angel",
            "oracle_text": "At the beginning of your end step, if you control Meld Partner, meld them.",
            "keywords": [],
            "power": "3",
            "toughness": "2",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "emn",
            "set_name": "Eldritch Moon",
            "rarity": "rare",
            "all_parts": [
                {
                    "object": "related_card",
                    "id": "meld-partner-1",
                    "component": "meld_part",
                    "name": "Meld Partner",
                    "type_line": "Creature — Angel",
                    "uri": "https://api.scryfall.com/cards/meld-partner-1"
                },
                {
                    "object": "related_card",
                    "id": "meld-result-1",
                    "component": "meld_result",
                    "name": "Meld Result",
                    "type_line": "Creature — Eldrazi Angel",
                    "uri": "https://api.scryfall.com/cards/meld-result-1"
                }
            ],
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "5.00"},
        },
        # Card without all_parts (no tokens)
        {
            "id": "token-test-none",
            "oracle_id": "token-oracle-none",
            "name": "No Token Creator",
            "mana_cost": "{1}{G}",
            "cmc": 2.0,
            "type_line": "Creature — Elf",
            "oracle_text": "{T}: Add {G}.",
            "keywords": [],
            "power": "1",
            "toughness": "1",
            "colors": ["G"],
            "color_identity": ["G"],
            "set": "m21",
            "set_name": "Core Set 2021",
            "rarity": "common",
            "image_uris": {},
            "legalities": {"modern": "legal", "legacy": "legal", "commander": "legal"},
            "prices": {"usd": "0.25"},
        },
    ]
