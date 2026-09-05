from __future__ import annotations

from pathlib import Path

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = f"sqlite+aiosqlite:///{Path(__file__).with_name('dota_mafia.db')}"
engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class GameRecord(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    phase: Mapped[str] = mapped_column(String(16), default="day")
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    players: Mapped[list["PlayerRecord"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class PlayerRecord(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    nickname: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    hero_key: Mapped[str] = mapped_column(String(64))
    seat: Mapped[int] = mapped_column(Integer)
    life_state: Mapped[str] = mapped_column(String(24), default="alive")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    game: Mapped[GameRecord] = relationship(back_populates="players")


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
