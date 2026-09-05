import unittest

from game.catalog import ABILITY_BY_KEY, HERO_BY_KEY
from game.engine import GameState, RuleViolation
from game.factory import create_automatic_game, create_manual_game
from game.models import AbilityKind, Action, LifeState, PlayerState, Role
from game.rules import role_distribution


class RulesTest(unittest.TestCase):
    def test_distribution_matches_approved_ranges(self) -> None:
        self.assertEqual(role_distribution(8)[Role.MAFIA], 2)
        self.assertEqual(role_distribution(13)[Role.SPECIAL], 2)
        self.assertEqual(role_distribution(15)[Role.MAFIA], 4)
        self.assertEqual(sum(role_distribution(15).values()), 15)

    def test_catalogue_contains_every_approved_hero(self) -> None:
        self.assertEqual(len(HERO_BY_KEY), 20)
        self.assertEqual(HERO_BY_KEY["axe"].role, Role.MAFIA)
        self.assertEqual(ABILITY_BY_KEY["doom"].kind, AbilityKind.ULTIMATE)
        self.assertEqual(ABILITY_BY_KEY["counterspell_ally"].cooldown, 2)

    def test_rejects_unsupported_game_sizes(self) -> None:
        with self.assertRaises(ValueError):
            role_distribution(7)
        with self.assertRaises(ValueError):
            role_distribution(16)

    def test_engine_allows_one_active_ability_and_applies_cooldown(self) -> None:
        game = GameState({
            "axe": PlayerState("axe", "Axe player", Role.MAFIA, "axe", 0),
            "target": PlayerState("target", "Target", Role.CIVILIAN, "oracle", 1),
        })
        game.start_night()
        game.add_action(Action("axe", "calling_blade"))
        with self.assertRaises(RuleViolation):
            game.add_action(Action("axe", "berserkers_call", ("target",)))
        game.resolve_night()
        game.start_night()
        with self.assertRaises(RuleViolation):
            game.add_action(Action("axe", "calling_blade"))
        game.resolve_night()
        game.start_night()
        game.add_action(Action("axe", "calling_blade"))

    def test_role_actions_are_not_redirected_and_check_is_private(self) -> None:
        game = GameState({
            "pugna": PlayerState("pugna", "Pugna", Role.SHERIFF, "pugna", 0),
            "target": PlayerState("target", "Target", Role.MAFIA, "axe", 1),
        })
        game.start_night()
        game.add_action(Action("pugna", "sheriff_check", ("target",)))
        events = game.resolve_night()
        result = next(event for event in events if event.code == "check_result")
        self.assertEqual(result.visible_to, ("pugna",))
        self.assertEqual(result.data["role"], "mafia")

    def test_doctor_heal_prevents_regular_mafia_kill(self) -> None:
        game = GameState({
            "axe": PlayerState("axe", "Axe", Role.MAFIA, "axe", 0),
            "doctor": PlayerState("doctor", "Doctor", Role.DOCTOR, "abaddon", 1),
            "target": PlayerState("target", "Target", Role.CIVILIAN, "oracle", 2),
        })
        game.start_night()
        game.add_action(Action("doctor", "doctor_heal", ("target",)))
        game.add_action(Action("axe", "mafia_kill", ("target",)))
        game.resolve_night()
        self.assertTrue(game.players["target"].is_alive)

    def test_automatic_game_assigns_unique_role_compatible_heroes(self) -> None:
        game = create_automatic_game([f"player {number}" for number in range(8)], seed=7)
        real_players = [player for player in game.players.values() if not player.metadata.get("bot")]
        self.assertEqual(len(real_players), 8)
        self.assertEqual(len({player.hero_key for player in real_players}), 8)
        self.assertEqual(sum(player.role is Role.MAFIA for player in real_players), 2)

    def test_voting_executes_single_leader(self) -> None:
        game = GameState({
            "one": PlayerState("one", "One", Role.MAFIA, "axe", 0),
            "two": PlayerState("two", "Two", Role.CIVILIAN, "oracle", 1),
        })
        game.start_voting()
        game.cast_vote("one", "two")
        game.cast_vote("two", "two")
        game.resolve_voting()
        self.assertFalse(game.players["two"].is_alive)

    def test_wraith_king_reincarnates_once(self) -> None:
        game = GameState({
            "mafia": PlayerState("mafia", "Mafia", Role.MAFIA, "axe", 0),
            "king": PlayerState("king", "King", Role.SHERIFF, "wraith_king", 1),
        })
        game.start_night()
        game.add_action(Action("mafia", "mafia_kill", ("king",)))
        game.resolve_night()
        self.assertTrue(game.players["king"].is_alive)
        game.start_night()
        game.add_action(Action("mafia", "mafia_kill", ("king",)))
        game.resolve_night()
        self.assertFalse(game.players["king"].is_alive)

    def test_redirect_reflect_and_swap_combination_resolves(self) -> None:
        game = GameState({
            "axe": PlayerState("axe", "Axe", Role.MAFIA, "axe", 0),
            "breaker": PlayerState("breaker", "Breaker", Role.DOCTOR, "spirit_breaker", 1),
            "mage": PlayerState("mage", "Mage", Role.SHERIFF, "anti_mage", 2),
            "venge": PlayerState("venge", "Venge", Role.SPECIAL, "vengeful_spirit", 3),
        })
        game.start_night()
        game.add_action(Action("axe", "berserkers_call", ("venge",)))
        game.add_action(Action("breaker", "planar_pocket", ("mage",)))
        game.add_action(Action("mage", "counterspell_ally", ("breaker",)))
        game.add_action(Action("venge", "swap", ("mage",)))
        events = game.resolve_night()
        self.assertTrue(any(event.code in {"reflected", "effect_resolved"} for event in events))

    def test_doom_does_not_block_an_ultimate_and_oracle_does_not_block_doom(self) -> None:
        game = GameState({
            "doom": PlayerState("doom", "Doom", Role.MAFIA, "doom", 0),
            "oracle": PlayerState("oracle", "Oracle", Role.CIVILIAN, "oracle", 1),
            "omni": PlayerState("omni", "Omni", Role.DOCTOR, "omniknight", 2),
            "dead": PlayerState("dead", "Dead", Role.CIVILIAN, "chaos_knight", 3, LifeState.DEAD),
        })
        game.start_night()
        game.add_action(Action("oracle", "fortunes_end", ("doom",)))
        game.add_action(Action("doom", "doom", ("omni",)))
        game.add_action(Action("omni", "guardian_angel", ("dead",)))
        game.resolve_night()
        self.assertTrue(game.players["dead"].is_alive)

    def test_sleep_prevents_vote(self) -> None:
        game = GameState({
            "bane": PlayerState("bane", "Bane", Role.SPECIAL, "bane", 0),
            "target": PlayerState("target", "Target", Role.CIVILIAN, "oracle", 1),
        })
        game.start_night()
        game.add_action(Action("bane", "sleep", ("target",)))
        game.resolve_night()
        game.start_voting()
        with self.assertRaises(RuleViolation):
            game.cast_vote("target", "bane")


if __name__ == "__main__":
    unittest.main()
