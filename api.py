from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import GameRecord, PlayerRecord, SessionLocal
from game.catalog import HERO_BY_KEY, HEROES
from game.engine import GameState, RuleViolation
from game.factory import create_automatic_game, create_manual_game
from game.models import Action, LifeState, Phase, PlayerState, Role, AbilityKind

router = APIRouter(prefix="/api", tags=["games"])


async def session() -> AsyncSession:
    async with SessionLocal() as value:
        yield value


class CreateGame(BaseModel):
    players: list[str] = Field(min_length=8, max_length=15)
    seed: int | None = None


class ManualPlayer(BaseModel):
    id: str
    nickname: str
    role: Role
    hero_key: str


class CreateManualGame(BaseModel):
    players: list[ManualPlayer] = Field(min_length=8, max_length=15)


class NightAction(BaseModel):
    actor_id: str
    ability_key: str
    target_ids: list[str] = []


class Vote(BaseModel):
    voter_id: str
    target_id: str


class InvokerOrb(BaseModel):
    orb: str


class NethertoxinZone(BaseModel):
    first_seat: int = Field(ge=0)


def serialize(game: GameState) -> dict:
    players_data = []
    for player in game.players.values():
        hero = HERO_BY_KEY.get(player.hero_key)
        abilities_info = []
        if hero:
            for ab in hero.abilities:
                abilities_info.append({
                    "key": ab.key,
                    "name": ab.name,
                    "kind": ab.kind.value,
                    "cooldown": ab.cooldown,
                    "current_cooldown": player.cooldowns.get(ab.key, 0),
                    "is_used": ab.key in player.used_ultimates,
                    "notes": ab.notes,
                    "target_count": ab.target_count,
                })

        players_data.append({
            "id": player.id,
            "nickname": player.nickname,
            "role": player.role.value,
            "hero_key": player.hero_key,
            "hero_name": hero.name if hero else player.hero_key,
            "life_state": player.life_state.value,
            "seat": player.seat,
            "cooldowns": player.cooldowns,
            "used_ultimates": list(player.used_ultimates),
            "abilities": abilities_info
        })

    return {
        "phase": game.phase.value,
        "round_number": game.round_number,
        "players": players_data,
        "pending_actions": [
            {"actor_id": a.actor_id, "ability_key": a.ability_key, "target_ids": list(a.target_ids)}
            for a in game.pending_actions
        ]
    }


async def load_game(game_id: int, db: AsyncSession) -> tuple[GameRecord, GameState]:
    record = await db.get(GameRecord, game_id)
    if record is None:
        raise HTTPException(404, "Игра не найдена")
    rows = (await db.scalars(select(PlayerRecord).where(PlayerRecord.game_id == game_id))).all()
    players = {}
    for row in rows:
        state = row.state or {}
        players[str(row.id)] = PlayerState(
            str(row.id),
            row.nickname,
            Role(row.role),
            row.hero_key,
            row.seat,
            LifeState(row.life_state),
            state.get("exhausted_until_round"),
            state.get("cooldowns", {}),
            state.get("charges", {}),
            set(state.get("used_ultimates", [])),
            state.get("metadata", {}),
        )
    game = GameState(players, Phase(record.phase), record.round_number)
    game.pending_actions = [
        Action(item["actor_id"], item["ability_key"], tuple(item["target_ids"]))
        for item in (record.state or {}).get("pending_actions", [])
    ]
    game.votes = (record.state or {}).get("votes", {})
    return record, game


async def save_game(record: GameRecord, game: GameState, db: AsyncSession) -> None:
    record.phase, record.round_number = game.phase.value, game.round_number
    record.state = {
        "pending_actions": [
            {"actor_id": action.actor_id, "ability_key": action.ability_key, "target_ids": list(action.target_ids)}
            for action in game.pending_actions
        ],
        "votes": game.votes,
    }
    rows = (await db.scalars(select(PlayerRecord).where(PlayerRecord.game_id == record.id))).all()
    for row in rows:
        state = game.players[str(row.id)]
        row.life_state = state.life_state.value
        row.state = {
            "exhausted_until_round": state.exhausted_until_round,
            "cooldowns": state.cooldowns,
            "charges": state.charges,
            "used_ultimates": sorted(state.used_ultimates),
            "metadata": state.metadata,
        }
    await db.commit()


@router.get("/heroes")
async def get_heroes() -> dict:
    return {
        role.value: [
            {
                "key": h.key,
                "name": h.name,
                "abilities": [
                    {"key": a.key, "name": a.name, "kind": a.kind.value, "notes": a.notes}
                    for a in h.abilities
                ],
            }
            for h in HEROES if h.role == role
        ]
        for role in Role
    }


@router.post("/games")
async def create_game(payload: CreateGame, db: AsyncSession = Depends(session)) -> dict:
    try:
        game = create_automatic_game(payload.players, payload.seed)
    except (RuleViolation, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    record = GameRecord()
    db.add(record)
    await db.flush()
    for player in game.players.values():
        db.add(PlayerRecord(game_id=record.id, nickname=player.nickname, role=player.role.value, hero_key=player.hero_key, seat=player.seat))
    await db.commit()
    return {"id": record.id}


@router.post("/games/manual")
async def create_manual(payload: CreateManualGame, db: AsyncSession = Depends(session)) -> dict:
    try:
        game = create_manual_game({item.id: (item.nickname, item.role, item.hero_key) for item in payload.players})
    except (RuleViolation, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    record = GameRecord()
    db.add(record)
    await db.flush()
    for player in game.players.values():
        db.add(PlayerRecord(game_id=record.id, nickname=player.nickname, role=player.role.value, hero_key=player.hero_key, seat=player.seat))
    await db.commit()
    return {"id": record.id}


@router.get("/games/{game_id}")
async def get_game(game_id: int, db: AsyncSession = Depends(session)) -> dict:
    _, game = await load_game(game_id, db)
    return serialize(game)


@router.post("/games/{game_id}/night")
async def start_night(game_id: int, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        game.start_night()
    except RuleViolation as error:
        raise HTTPException(409, str(error)) from error
    await save_game(record, game, db)
    return serialize(game)


@router.post("/games/{game_id}/actions")
async def add_action(game_id: int, payload: NightAction, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        game.add_action(Action(payload.actor_id, payload.ability_key, tuple(payload.target_ids)))
    except RuleViolation as error:
        raise HTTPException(422, str(error)) from error
    await save_game(record, game, db)
    return {"accepted": True, "action_count": len(game.pending_actions)}


@router.post("/games/{game_id}/resolve-night")
async def resolve_night(game_id: int, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        events = game.resolve_night()
    except RuleViolation as error:
        raise HTTPException(409, str(error)) from error
    await save_game(record, game, db)
    return {"game": serialize(game), "events": [event.message for event in events]}


@router.post("/games/{game_id}/voting")
async def start_voting(game_id: int, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        game.start_voting()
    except RuleViolation as error:
        raise HTTPException(409, str(error)) from error
    await save_game(record, game, db)
    return serialize(game)


@router.post("/games/{game_id}/votes")
async def cast_vote(game_id: int, payload: Vote, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        game.cast_vote(payload.voter_id, payload.target_id)
    except RuleViolation as error:
        raise HTTPException(422, str(error)) from error
    await save_game(record, game, db)
    return {"accepted": True, "votes": game.votes}


@router.post("/games/{game_id}/resolve-voting")
async def resolve_voting(game_id: int, db: AsyncSession = Depends(session)) -> dict:
    record, game = await load_game(game_id, db)
    try:
        events = game.resolve_voting()
    except RuleViolation as error:
        raise HTTPException(409, str(error)) from error
    await save_game(record, game, db)
    return {"game": serialize(game), "events": [event.message for event in events]}