from __future__ import annotations

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import SelfAccount, Subscription, User


async def ensure_user(session: AsyncSession, tg: TgUser, referrer_id: int | None = None) -> None:
    """کاربر رو می‌سازه یا نام‌ش رو به‌روز می‌کنه. دعوت‌کننده فقط در اولین ساخت ثبت می‌شه."""
    ref: int | None = None
    if referrer_id and referrer_id != tg.id:
        ref = await session.scalar(select(User.id).where(User.id == referrer_id))
    stmt = pg_insert(User).values(
        id=tg.id,
        username=tg.username,
        first_name=(tg.first_name or "")[:128],
        referrer_id=ref,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.id],
        set_={"username": stmt.excluded.username, "first_name": stmt.excluded.first_name},
    )
    await session.execute(stmt)


async def get_dashboard_data(session: AsyncSession, user_id: int):
    expires_at = await session.scalar(select(Subscription.expires_at).where(Subscription.user_id == user_id))
    account = await session.get(SelfAccount, user_id)
    return account, expires_at


async def count_referrals(session: AsyncSession, user_id: int) -> int:
    from sqlalchemy import func

    return int(await session.scalar(select(func.count(User.id)).where(User.referrer_id == user_id)) or 0)
