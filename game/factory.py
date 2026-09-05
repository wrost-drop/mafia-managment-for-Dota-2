"""Game creation and safe automatic/manual hero assignment."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from .catalog import HEROES
from .engine import GameState, RuleViolation
from .models import PlayerState, Role
from .rules import role_distribution


def create_automatic_game(nicknames: Sequence[str], seed: int | None = None) -> GameState:
    if len(set(nicknames)) != len(nicknames) or any(not name.strip() for name in nicknames):
        raise RuleViolation("Player names must be non-empty and unique.")
    distribution = role_distribution(len(nicknames))
    roles = [role for role, count in distribution.items() for _ in range(count)]
    rng = random.Random(seed)
    rng.shuffle(roles)
    available = {role: [hero for hero in HEROES if hero.role is role] for role in Role}
    for heroes in available.values():
        rng.shuffle(heroes)
    used: set[str] = set()
    players: dict[str, PlayerState] = {}
    for seat, (nickname, role) in enumerate(zip(nicknames, roles, strict=True)):
        hero = next((item for item in available[role] if item.key not in used), None)
        if hero is None:
            raise RuleViolation(f"Not enough unique heroes for {role.value}.")
        used.add(hero.key)
        player_id = f"player-{seat + 1}"
        players[player_id] = PlayerState(player_id, nickname.strip(), role, hero.key, seat)
    lone_druid = next((item for item in players.values() if item.hero_key == "lone_druid"), None)
    if lone_druid is not None:
        bear_id = "spirit-bear"
        players[bear_id] = PlayerState(bear_id, "Spirit Bear", Role.CIVILIAN, "spirit_bear", len(players), metadata={"bot": True, "owner": lone_druid.id})
    return GameState(players)


def create_manual_game(assignments: Mapping[str, tuple[str, Role, str]]) -> GameState:
    if not 8 <= len(assignments) <= 15:
        raise RuleViolation("A game requires from 8 to 15 players.")
    players: dict[str, PlayerState] = {}
    heroes: set[str] = set()
    for seat, (player_id, (nickname, role, hero_key)) in enumerate(assignments.items()):
        from .catalog import HERO_BY_KEY

        hero = HERO_BY_KEY.get(hero_key)
        if hero is None or hero.role is not role:
            raise RuleViolation("Hero must belong to the assigned role.")
        if hero_key in heroes:
            raise RuleViolation("A hero may be assigned only once.")
        heroes.add(hero_key)
        players[player_id] = PlayerState(player_id, nickname, role, hero_key, seat)
    return GameState(players)
