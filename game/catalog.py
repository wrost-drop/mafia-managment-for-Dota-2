"""Immutable catalogue of the approved hero and ability rules."""

from .models import AbilityDefinition, AbilityKind, HeroDefinition, Role


def ability(key: str, name: str, kind: AbilityKind, **kwargs: object) -> AbilityDefinition:
    return AbilityDefinition(key, name, kind, **kwargs)


HEROES: tuple[HeroDefinition, ...] = (
    HeroDefinition("phantom_lancer", "Phantom Lancer", Role.MAFIA, (
        ability("juxtapose", "Juxtapose", AbilityKind.ACTIVE, target_count=1, directed=True),
        ability("spirit_lance", "Spirit Lance", AbilityKind.PASSIVE),
    )),
    HeroDefinition("doom", "Doom", Role.MAFIA, (ability("doom", "Doom", AbilityKind.ULTIMATE, uses=1, target_count=1, directed=True),)),
    HeroDefinition("axe", "Axe", Role.MAFIA, (
        ability("calling_blade", "Calling Blade", AbilityKind.ACTIVE, cooldown=1),
        ability("berserkers_call", "Berserker Call", AbilityKind.ACTIVE, cooldown=3, target_count=1, directed=True),
    )),
    HeroDefinition("rubick", "Rubick", Role.MAFIA, (ability("spell_steal", "Spell Steal", AbilityKind.ACTIVE, target_count=1, directed=True),)),
    HeroDefinition("pugna", "Pugna", Role.SHERIFF, (
        ability("nether_ward", "Nether Ward", AbilityKind.ACTIVE, cooldown=4, target_count=1, directed=True),
        ability("life_drain", "Life Drain", AbilityKind.PASSIVE),
    )),
    HeroDefinition("wraith_king", "Wraith King", Role.SHERIFF, (ability("reincarnation", "Reincarnation", AbilityKind.PASSIVE, uses=1),)),
    HeroDefinition("anti_mage", "Anti-Mage", Role.SHERIFF, (
        ability("counterspell_ally", "Counterspell Ally", AbilityKind.ACTIVE, cooldown=2, target_count=1, directed=True),
        ability("mana_break", "Mana Break", AbilityKind.PASSIVE),
    )),
    HeroDefinition("spirit_breaker", "Spirit Breaker", Role.DOCTOR, (
        ability("planar_pocket", "Planar Pocket", AbilityKind.ACTIVE, cooldown=2, target_count=1, directed=True),
        ability("bulldoze", "Bulldoze", AbilityKind.PASSIVE),
    )),
    HeroDefinition("abaddon", "Abaddon", Role.DOCTOR, (
        ability("mist_coil", "Mist Coil", AbilityKind.ULTIMATE, uses=1),
        ability("borrow_time", "Borrow Time", AbilityKind.PASSIVE, uses=1),
    )),
    HeroDefinition("omniknight", "Omniknight", Role.DOCTOR, (
        ability("guardian_angel", "Guardian Angel", AbilityKind.ULTIMATE, target_count=1, directed=True),
        ability("degen_aura", "Degen Aura", AbilityKind.PASSIVE),
    )),
    HeroDefinition("bane", "Bane", Role.SPECIAL, (
        ability("sleep", "Sleep", AbilityKind.ACTIVE, cooldown=3, target_count=1, directed=True),
        ability("curse", "Curse", AbilityKind.PASSIVE),
    )),
    HeroDefinition("vengeful_spirit", "Vengeful Spirit", Role.SPECIAL, (
        ability("swap", "Swap", AbilityKind.ACTIVE, cooldown=2, target_count=1, directed=True),
        ability("vengeance_aura", "Vengeance Aura", AbilityKind.PASSIVE),
    )),
    HeroDefinition("viper", "Viper", Role.SPECIAL, (
        ability("viper_strike", "Viper Strike", AbilityKind.ACTIVE, cooldown=2, target_count=1, directed=True),
        ability("nethertoxin", "Nethertoxin", AbilityKind.PASSIVE),
    )),
    HeroDefinition("chaos_knight", "Chaos Knight", Role.CIVILIAN, (ability("dice", "Dice", AbilityKind.PASSIVE),)),
    HeroDefinition("hoodwink", "Hoodwink", Role.CIVILIAN, (ability("mistwoods", "Mistwoods", AbilityKind.PASSIVE),)),
    HeroDefinition("invoker", "Invoker", Role.CIVILIAN, (ability("orbs", "Сферы", AbilityKind.PASSIVE),)),
    HeroDefinition("keeper_of_the_light", "Keeper Of The Light", Role.CIVILIAN, (ability("chakra_magic", "Chakra Magic", AbilityKind.ACTIVE, cooldown=3, target_count=1, directed=True),)),
    HeroDefinition("lone_druid", "Lone Druid", Role.CIVILIAN, (ability("summon_spirit_bear", "Summon Spirit Bear", AbilityKind.PASSIVE),)),
    HeroDefinition("winter_wyvern", "Winter Wyvern", Role.CIVILIAN, (ability("winters_curse", "Winter's Curse", AbilityKind.ULTIMATE, uses=1, target_count=1, directed=True),)),
    HeroDefinition("oracle", "Oracle", Role.CIVILIAN, (ability("fortunes_end", "Fortune's End", AbilityKind.ACTIVE, cooldown=5, target_count=1, directed=True),)),
)

HERO_BY_KEY = {hero.key: hero for hero in HEROES}
ABILITY_BY_KEY = {item.key: item for hero in HEROES for item in hero.abilities}
