from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .models import Base, Plan


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine, db: async_sessionmaker) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.begin() as session:
        count = await session.scalar(select(func.count(Plan.id)))
        if not count:
            session.add_all(
                [
                    Plan(months=1, price=10_000),
                    Plan(months=2, price=20_000),
                    Plan(months=3, price=30_000),
                ]
            )
