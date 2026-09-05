"""Stateful, dependency-free game engine used by the future API layer."""

from __future__ import annotations

from dataclasses import dataclass, field
import random

from .catalog import ABILITY_BY_KEY, HERO_BY_KEY
from .models import AbilityKind, Action, Event, LifeState, Phase, PlayerState, Role, ROLE_ABILITIES


class RuleViolation(ValueError):
    """Raised when the moderator enters an action forbidden by the rules."""


@dataclass(slots=True)
class GameState:
    players: dict[str, PlayerState]
    phase: Phase = Phase.DAY
    round_number: int = 0
    pending_actions: list[Action] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    random_seed: int | None = None

    def start_night(self) -> None:
        if self.phase is not Phase.DAY:
            raise RuleViolation("Night can begin only after a day.")
        self.phase = Phase.NIGHT
        self.round_number += 1
        self.pending_actions.clear()
        self._reduce_cooldowns()
        self._start_of_night_passives()
        for clone in self.players.values():
            if clone.life_state is LifeState.CLONE:
                targets = [item for item in self.players.values() if item.is_alive and item.id != clone.id]
                if targets:
                    chosen = random.Random(self.random_seed).choice(targets)
                    self.pending_actions.append(Action(clone.id, "swap", (chosen.id,)))

    def set_invoker_orb(self, player_id: str, orb: str) -> None:
        player = self._player(player_id)
        if player.hero_key != "invoker" or not player.is_alive:
            raise RuleViolation("Only a living Invoker can choose an orb.")
        if orb not in {"quas", "wex", "exort"}:
            raise RuleViolation("Orb must be quas, wex, or exort.")
        player.metadata["invoker_orb"] = orb

    def set_nethertoxin_zone(self, player_id: str, first_seat: int) -> None:
        player = self._player(player_id)
        if player.hero_key != "viper" or not 0 <= first_seat <= len(self.players) - 3:
            raise RuleViolation("Invalid Nethertoxin zone.")
        player.metadata["nethertoxin_seats"] = [first_seat, first_seat + 1, first_seat + 2]

    def start_voting(self) -> None:
        if self.phase is not Phase.DAY:
            raise RuleViolation("Voting can begin only during a day.")
        self.phase = Phase.VOTING
        self.votes.clear()

    def cast_vote(self, voter_id: str, target_id: str) -> None:
        if self.phase is not Phase.VOTING:
            raise RuleViolation("Votes can be cast only during voting.")
        voter, target = self._player(voter_id), self._player(target_id)
        if not voter.is_alive or voter.life_state is LifeState.DELAYED_DEATH:
            raise RuleViolation("This player cannot vote.")
        if voter.metadata.get("asleep_day") == self.round_number:
            raise RuleViolation("A sleeping player cannot vote.")
        if not target.is_alive:
            raise RuleViolation("A dead player cannot be voted for.")
        self.votes[voter_id] = target_id

    def resolve_voting(self) -> list[Event]:
        if self.phase is not Phase.VOTING:
            raise RuleViolation("Only voting can be resolved.")
        counts: dict[str, int] = {}
        for target_id in self.votes.values():
            counts[target_id] = counts.get(target_id, 0) + 1
        events: list[Event] = []
        if counts:
            maximum = max(counts.values())
            leaders = [player_id for player_id, count in counts.items() if count == maximum]
            if len(leaders) == 1:
                target = self._player(leaders[0])
                self._kill(target, target, events)
                events.append(Event("executed", "Player was executed by vote.", data={"target_id": target.id}))
            else:
                events.append(Event("vote_tie", "Vote ended in a tie."))
        self.events.extend(events)
        self.phase = Phase.DAY
        return events

    def add_action(self, action: Action) -> None:
        if self.phase is not Phase.NIGHT:
            raise RuleViolation("Hero actions can be selected only at night.")
        actor = self._player(action.actor_id)
        if not actor.is_alive or actor.life_state is LifeState.DELAYED_DEATH:
            raise RuleViolation("This player cannot act.")
        ability = self._ability_for(actor, action.ability_key)
        if ability is None:
            raise RuleViolation("This hero does not have that ability.")
        if ability.kind is AbilityKind.PASSIVE:
            raise RuleViolation("Passive abilities cannot be selected manually.")
        if ability.kind is AbilityKind.ULTIMATE and ability.key in actor.used_ultimates:
            raise RuleViolation("This ultimate was already used.")
        if actor.cooldowns.get(ability.key, 0) > 0:
            raise RuleViolation("This ability is on cooldown.")
        if len(action.target_ids) != ability.target_count:
            raise RuleViolation("Incorrect number of targets.")
        if len(set(action.target_ids)) != len(action.target_ids):
            raise RuleViolation("Targets must be distinct.")
        for target_id in action.target_ids:
            target = self._player(target_id)
            if not target.is_alive and ability.key != "guardian_angel":
                raise RuleViolation("A dead player cannot be targeted.")
        if ability.kind is AbilityKind.ACTIVE and any(
            self._ability_for(self._player(item.actor_id), item.ability_key).kind is AbilityKind.ACTIVE and item.actor_id == actor.id
            for item in self.pending_actions
        ):
            raise RuleViolation("A hero can use only one active ability per night.")
        if ability.kind is AbilityKind.ROLE and any(item.actor_id == actor.id and self._ability_for(actor, item.ability_key).kind is AbilityKind.ROLE for item in self.pending_actions):
            raise RuleViolation("A role action was already selected.")
        if ability.key == "doctor_heal" and action.actor_id in action.target_ids:
            self_heals = actor.metadata.get("self_heals", 0)
            limit = 2 if actor.hero_key == "spirit_breaker" else 1
            if self_heals >= limit:
                raise RuleViolation("This doctor has no self-heals left.")
        self.pending_actions.append(action)

    def resolve_night(self) -> list[Event]:
        """Locks selected actions and advances to day.

        This central transaction point is deliberately separate from UI code.
        Individual effect resolvers will be registered here as the moderator
        rules are converted into executable outcomes.
        """
        if self.phase is not Phase.NIGHT:
            raise RuleViolation("Only a night can be resolved.")
        events: list[Event] = []
        for action in self.pending_actions:
            actor = self._player(action.actor_id)
            ability = self._ability_for(actor, action.ability_key)
            if ability.cooldown is not None:
                # A one-round cooldown skips the next night and is available
                # on the night after it, hence the additional current round.
                actor.cooldowns[ability.key] = ability.cooldown + 1
            if ability.kind is AbilityKind.ULTIMATE:
                actor.used_ultimates.add(ability.key)
            events.append(Event("action_locked", f"{ability.name} locked for resolution.", data={"actor_id": actor.id, "targets": action.target_ids}))
        events.extend(self._apply_actions())
        self.events.extend(events)
        self.phase = Phase.DAY
        self.pending_actions.clear()
        events.extend(self._finalize_delayed_deaths())
        return events

    def _reduce_cooldowns(self) -> None:
        for player in self.players.values():
            for key, remaining in tuple(player.cooldowns.items()):
                if remaining > 0:
                    player.cooldowns[key] = remaining - 1

    def _apply_actions(self) -> list[Event]:
        """Resolve a night as one batch, never in click/entry order.

        Target-changing abilities are collected first.  Role actions are not
        redirected: this follows the agreed definition of a directed action.
        """
        events: list[Event] = []
        actions = list(self.pending_actions)
        targets = {id(action): list(action.target_ids) for action in actions}
        redirects: dict[str, str] = {}
        reflects: set[str] = set()

        # The order is a rules order, never the order in which the moderator
        # entered actions.  Protection is established before a kill resolves.
        priority = {"fortune_s_end": 0, "doom": 0, "doctor_heal": 1, "mafia_kill": 3, "juxtapose": 3}
        for action in sorted(actions, key=lambda item: priority.get(item.ability_key, 2)):
            actor = self._player(action.actor_id)
            key = action.ability_key
            if key == "planar_pocket" and action.target_ids:
                redirects[action.target_ids[0]] = actor.id
            elif key == "berserkers_call" and action.target_ids:
                redirects[action.target_ids[0]] = actor.id
            elif key == "counterspell_ally" and action.target_ids:
                reflects.add(action.target_ids[0])
            elif key == "swap" and action.target_ids:
                other = action.target_ids[0]
                for candidate in actions:
                    ability = self._ability_for(self._player(candidate.actor_id), candidate.ability_key)
                    if ability.kind is AbilityKind.ROLE or not ability.directed:
                        continue
                    targets[id(candidate)] = [other if target == actor.id else actor.id if target == other else target for target in targets[id(candidate)]]

        for action in sorted(actions, key=lambda item: priority.get(item.ability_key, 2)):
            actor = self._player(action.actor_id)
            ability = self._ability_for(actor, action.ability_key)
            action_targets = targets[id(action)]
            if ability.kind is not AbilityKind.ROLE and ability.directed:
                action_targets = [redirects.get(target, target) for target in action_targets]
                if action_targets and action_targets[0] in reflects:
                    action_targets = [actor.id]
                    events.append(Event("reflected", "Directed ability reflected to its owner.", data={"actor_id": actor.id, "ability": ability.key}))
                curse_owner = self._curse_owner(actor)
                if curse_owner and ability.kind is AbilityKind.ACTIVE:
                    for target_id in action_targets:
                        cursed = self._player(target_id)
                        cursed.life_state = LifeState.CURSED
                        cursed.metadata["curse_owner"] = curse_owner.id
                        events.append(Event("cursed", "Bane's curse replaced the action.", data={"target_id": target_id}))
                    continue
                if self._evades(action_targets, ability):
                    events.append(Event("evaded", "Hoodwink evaded a hero ability.", data={"ability": ability.key, "targets": action_targets}))
                    continue
            if self._is_blocked(actor, ability):
                events.append(Event("blocked", "Action blocked by Doom or delayed death.", data={"actor_id": actor.id, "ability": ability.key}))
                continue
            if ability.kind is not AbilityKind.ROLE and ability.key not in {"doom", "juxtapose"} and any(self._protected(target) for target in action_targets):
                events.append(Event("blocked", "Action blocked by Fortune's End.", data={"actor_id": actor.id, "ability": ability.key}))
                continue
            if ability.key in {"doom", "sleep", "viper_strike"} and any(self._player(target).hero_key == "spirit_breaker" for target in action_targets):
                events.append(Event("bulldoze", "Spirit Breaker ignored a negative hero effect.", data={"ability": ability.key}))
                continue
            events.extend(self._apply_one(actor, ability.key, action_targets))
            for target_id in action_targets:
                viper = self._player(target_id)
                if viper.hero_key == "viper" and actor.seat in viper.metadata.get("nethertoxin_seats", []) and ability.cooldown is not None:
                    actor.cooldowns[ability.key] = actor.cooldowns.get(ability.key, 0) + 1
                    events.append(Event("nethertoxin", "Nethertoxin increased cooldown.", (actor.id,), {"ability": ability.key}))
        return events

    def _apply_one(self, actor: PlayerState, key: str, targets: list[str]) -> list[Event]:
        events: list[Event] = []
        target = self._player(targets[0]) if targets else None
        if key == "fortune_s_end":
            target.metadata["protected_round"] = self.round_number
        elif key == "doom":
            target.metadata["doomed_until_round"] = self.round_number + 1
        elif key == "sleep":
            target.metadata["asleep_day"] = self.round_number
        elif key == "viper_strike":
            target.exhausted_until_round = self.round_number
        elif key == "spell_steal":
            hero = HERO_BY_KEY[target.hero_key]
            candidate = next((item for item in hero.abilities if item.kind is AbilityKind.ACTIVE), hero.abilities[0])
            stolen_from = actor.metadata.setdefault("stolen_from", [])
            if target.id in stolen_from:
                events.append(Event("steal_failed", "Rubick already stole from this player.", (actor.id,)))
            else:
                stolen_from.append(target.id)
                actor.metadata["stolen_ability"] = candidate.key
                events.append(Event("ability_stolen", "Rubick stole an ability.", (actor.id,), {"ability": candidate.key}))
        elif key == "nether_ward":
            target.metadata["nether_ward_owner"] = actor.id
            target.metadata["nether_ward_round"] = self.round_number
            neighbors = {target.seat - 1, target.seat + 1}
            users = [self._player(candidate.actor_id) for candidate in self.pending_actions if candidate.actor_id != actor.id and self._player(candidate.actor_id).seat in neighbors and self._ability_for(self._player(candidate.actor_id), candidate.ability_key).kind is AbilityKind.ACTIVE]
            if len(users) == 2:
                events.append(Event("ward_result", "Nether Ward revealed adjacent roles.", (actor.id,), {"roles": [item.role.value for item in users]}))
        elif key == "calling_blade":
            actor.metadata["calling_blade_round"] = self.round_number
        elif key == "chakra_magic" and target.role is not Role.MAFIA:
            for ability_key, remaining in target.cooldowns.items():
                target.cooldowns[ability_key] = max(0, remaining - 1)
        elif key == "sheriff_check":
            events.append(Event("check_result", "Sheriff learned a role.", (actor.id,), {"target_id": target.id, "role": target.role.value}))
            if actor.hero_key == "pugna" and any(item.actor_id != actor.id and target.id in item.target_ids and self._ability_for(self._player(item.actor_id), item.ability_key).kind is AbilityKind.ACTIVE for item in self.pending_actions):
                actor.cooldowns["nether_ward"] = max(0, actor.cooldowns.get("nether_ward", 0) - 1)
            if actor.hero_key == "anti_mage" and target.role is Role.MAFIA and actor.charges.get("mana_break", 1) > 0:
                actor.charges["mana_break"] = actor.charges.get("mana_break", 1) - 1
                for item in HERO_BY_KEY[target.hero_key].abilities:
                    if item.kind is AbilityKind.ACTIVE:
                        target.cooldowns[item.key] = target.cooldowns.get(item.key, 0) + 1
        elif key == "doctor_heal":
            target.metadata["healed_round"] = self.round_number
            if target.id == actor.id:
                actor.metadata["self_heals"] = actor.metadata.get("self_heals", 0) + 1
        elif key == "mafia_kill":
            self._kill(target, actor, events)
        elif key == "juxtapose":
            self._kill(target, actor, events, delayed=True)
        elif key == "guardian_angel":
            if target.role not in {Role.MAFIA, Role.SHERIFF, Role.DOCTOR} and target.life_state is LifeState.DEAD:
                target.life_state = LifeState.ALIVE
                events.append(Event("revived", "Guardian Angel revived a player.", data={"target_id": target.id}))
        elif key == "winters_curse":
            living = [item for item in self.players.values() if item.is_alive]
            mafia = sum(item.role is Role.MAFIA for item in living)
            if len(living) == 4 and mafia == 1:
                target.metadata["winter_curse_round"] = self.round_number
                events.append(Event("winter_curse", "All directed effects are locked to the target.", data={"target_id": target.id}))
            else:
                events.append(Event("winter_curse_failed", "Winter's Curse condition was not met.", (actor.id,)))
        elif key == "mist_coil":
            actor.metadata["mist_coil_armed"] = True
        else:
            events.append(Event("effect_resolved", "Ability has no immediate state change.", data={"actor_id": actor.id, "ability": key, "targets": targets}))
        return events

    def _kill(self, target: PlayerState, actor: PlayerState, events: list[Event], delayed: bool = False) -> None:
        if target.metadata.get("healed_round") == self.round_number and actor.metadata.get("calling_blade_round") != self.round_number:
            events.append(Event("saved", "Doctor saved the target.", data={"target_id": target.id}))
            return
        if delayed:
            target.life_state = LifeState.DELAYED_DEATH
            target.metadata["dies_after_round"] = self.round_number + 1
            events.append(Event("delayed_death", "Target is replaced by a Phantom Lancer clone.", data={"target_id": target.id}))
            return
        if target.hero_key == "wraith_king" and not target.metadata.get("reincarnated"):
            target.metadata["reincarnated"] = True
            events.append(Event("reincarnated", "Wraith King returned to life.", data={"target_id": target.id}))
            return
        if target.hero_key == "abaddon" and not target.metadata.get("mist_coil_used"):
            recipient = next((item for item in self.players.values() if item.role is Role.CIVILIAN and item.is_alive), None)
            if recipient is not None:
                recipient.role = Role.DOCTOR
                target.metadata["mist_coil_used"] = True
                target.life_state = LifeState.DELAYED_DEATH
                target.metadata["dies_after_round"] = self.round_number
                events.append(Event("doctor_transferred", "Doctor role was transferred.", (recipient.id,), {"recipient_id": recipient.id}))
                return
        if target.hero_key == "abaddon" and not target.metadata.get("borrow_time_used"):
            target.metadata["borrow_time_used"] = True
            target.life_state = LifeState.DELAYED_DEATH
            target.metadata["dies_after_round"] = self.round_number
            events.append(Event("borrow_time", "Abaddon remains until the next morning.", data={"target_id": target.id}))
            return
        target.life_state = LifeState.DEAD
        events.append(Event("killed", "Target died.", data={"target_id": target.id}))
        self._on_death(target, events)

    def _on_death(self, player: PlayerState, events: list[Event]) -> None:
        for item in self.players.values():
            if item.hero_key == "anti_mage" and player.role in {Role.SHERIFF, Role.DOCTOR, Role.SPECIAL}:
                item.charges["mana_break"] = item.charges.get("mana_break", 1) + 1
            if item.hero_key == "omniknight" and player.role in {Role.SHERIFF, Role.DOCTOR}:
                item.charges["guardian_angel"] = 1
        if player.hero_key == "vengeful_spirit":
            clone_id = f"{player.id}-clone-{self.round_number}"
            self.players[clone_id] = PlayerState(clone_id, "Vengeful Spirit clone", Role.SPECIAL, "vengeful_spirit", player.seat, LifeState.CLONE, metadata={"clone_owner": player.id, "dies_after_round": self.round_number + 1})
            events.append(Event("clone_created", "Vengeful Spirit clone remains.", data={"clone_id": clone_id}))
        if player.hero_key == "invoker":
            self._resolve_invoker_death(player, events)
        if player.hero_key == "bane":
            for target in self.players.values():
                if target.metadata.get("curse_owner") == player.id:
                    target.metadata.pop("curse_owner", None)
                    target.life_state = LifeState.ALIVE

    def _resolve_invoker_death(self, player: PlayerState, events: list[Event]) -> None:
        orb = player.metadata.get("invoker_orb")
        candidates = [item for item in self.players.values() if item.is_alive and item.id != player.id]
        if not candidates or orb is None:
            return
        target = random.Random(self.random_seed).choice(candidates)
        if orb == "quas":
            target.metadata["asleep_day"] = self.round_number
        elif orb == "wex":
            for item in self.players.values():
                if abs(item.seat - player.seat) == 1:
                    for ability in HERO_BY_KEY[item.hero_key].abilities:
                        if ability.kind is AbilityKind.ACTIVE:
                            item.cooldowns[ability.key] = item.cooldowns.get(ability.key, 0) + 1
        elif orb == "exort":
            targets = [item for item in candidates if item.role in {Role.CIVILIAN, Role.SPECIAL}]
            if targets:
                reveal = random.Random(self.random_seed).choice(targets)
                events.append(Event("sunstrike_reveal", "Sunstrike revealed role and hero.", data={"target_id": reveal.id, "role": reveal.role.value, "hero": reveal.hero_key}))

    def _start_of_night_passives(self) -> None:
        for player in list(self.players.values()):
            if player.hero_key == "chaos_knight" and player.is_alive and random.Random(self.random_seed).randint(1, 10) == 10:
                targets = [item for item in self.players.values() if item.is_alive and item.id != player.id]
                if targets:
                    target = random.Random(self.random_seed).choice(targets)
                    self.events.append(Event("dice_result", "Chaos Knight learned a role.", (player.id,), {"target_id": target.id, "role": target.role.value}))
            if player.life_state is LifeState.CLONE and player.metadata.get("dies_after_round") == self.round_number:
                player.life_state = LifeState.DEAD

    def _curse_owner(self, actor: PlayerState) -> PlayerState | None:
        if actor.metadata.get("asleep_day") != self.round_number and actor.metadata.get("asleep_night") != self.round_number:
            return None
        return next((item for item in self.players.values() if item.hero_key == "bane" and item.is_alive), None)

    def _evades(self, target_ids: list[str], ability) -> bool:
        if ability.kind is AbilityKind.ROLE:
            return False
        return any(self._player(item).hero_key == "hoodwink" and random.Random(self.random_seed).random() < .05 for item in target_ids)

    def _finalize_delayed_deaths(self) -> list[Event]:
        events: list[Event] = []
        for player in self.players.values():
            if player.life_state is LifeState.DELAYED_DEATH and player.metadata.get("dies_after_round") == self.round_number:
                player.life_state = LifeState.DEAD
                events.append(Event("delayed_death_finalized", "Phantom Lancer clone disappeared.", data={"target_id": player.id}))
        self.events.extend(events)
        return events

    def _protected(self, player_id: str) -> bool:
        return self._player(player_id).metadata.get("protected_round") == self.round_number

    def _is_blocked(self, player: PlayerState, ability) -> bool:
        if player.life_state is LifeState.DELAYED_DEATH:
            return True
        if player.metadata.get("doomed_until_round", -1) >= self.round_number:
            return ability.kind is not AbilityKind.ULTIMATE
        return False

    def _player(self, player_id: str) -> PlayerState:
        try:
            return self.players[player_id]
        except KeyError as exc:
            raise RuleViolation("Unknown player.") from exc

    def _ability_for(self, actor: PlayerState, ability_key: str):
        role_ability = ROLE_ABILITIES.get(actor.role)
        if role_ability is not None and role_ability.key == ability_key:
            return role_ability
        hero = HERO_BY_KEY.get(actor.hero_key)
        if hero is None:
            return None
        return next((ability for ability in hero.abilities if ability.key == ability_key), None)

    def winner(self) -> Role | None:
        living = [player for player in self.players.values() if player.life_state is LifeState.ALIVE]
        mafia = sum(player.role is Role.MAFIA for player in living)
        non_mafia = len(living) - mafia
        if mafia == 0:
            return Role.CIVILIAN
        if mafia >= non_mafia:
            return Role.MAFIA
        return None
