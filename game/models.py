from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    MAFIA = "mafia"
    SHERIFF = "sheriff"
    DOCTOR = "doctor"
    SPECIAL = "special"
    CIVILIAN = "civilian"


class AbilityKind(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"
    ULTIMATE = "ultimate"
    ROLE = "role"


class EffectKind(str, Enum):
    KILL = "kill"
    HEAL = "heal"
    CHECK = "check"
    REDIRECT = "redirect"
    REFLECT = "reflect"
    BLOCK = "block"
    EXHAUST = "exhaust"
    REVEAL = "reveal"


class Phase(str, Enum):
    DAY = "day"
    NIGHT = "night"
    VOTING = "voting"
    FINISHED = "finished"


class LifeState(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    DELAYED_DEATH = "delayed_death"
    CURSED = "cursed"
    CLONE = "clone"


@dataclass(frozen=True, slots=True)
class AbilityDefinition:
    key: str
    name: str
    kind: AbilityKind
    cooldown: int | None = None
    uses: int | None = None
    target_count: int = 0
    directed: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class HeroDefinition:
    key: str
    name: str
    role: Role
    abilities: tuple[AbilityDefinition, ...]


@dataclass(slots=True)
class PlayerState:
    id: str
    nickname: str
    role: Role
    hero_key: str
    seat: int
    life_state: LifeState = LifeState.ALIVE
    exhausted_until_round: int | None = None
    cooldowns: dict[str, int] = field(default_factory=dict)
    charges: dict[str, int] = field(default_factory=dict)
    used_ultimates: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_alive(self) -> bool:
        return self.life_state in {LifeState.ALIVE, LifeState.DELAYED_DEATH, LifeState.CLONE}

    def passive_enabled(self, round_number: int) -> bool:
        return self.exhausted_until_round is None or round_number > self.exhausted_until_round


@dataclass(frozen=True, slots=True)
class Action:
    actor_id: str
    ability_key: str
    target_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Event:
    code: str
    message: str
    visible_to: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)


ROLE_ABILITIES: dict[Role, AbilityDefinition] = {
    Role.MAFIA: AbilityDefinition("mafia_kill", "Убийство мафии", AbilityKind.ROLE, target_count=1),
    Role.SHERIFF: AbilityDefinition("sheriff_check", "Проверка шерифа", AbilityKind.ROLE, target_count=1),
    Role.DOCTOR: AbilityDefinition("doctor_heal", "Лечение доктора", AbilityKind.ROLE, target_count=1),
}
