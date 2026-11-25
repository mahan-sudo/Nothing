from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DAYS_PER_MONTH
from ..db.models import Subscription


async def get_expires_at(session: AsyncSession, user_id: int) -> datetime | None:
    return await session.scalar(select(Subscription.expires_at).where(Subscription.user_id == user_id))


async def extend_subscription(session: AsyncSession, user_id: int, months: int, now: datetime) -> datetime:
    """اشتراک رو تمدید می‌کنه. اگه هنوز فعاله از روز پایانش ادامه می‌ده، وگرنه از الان.
    ردیف قفل می‌شه تا دو تمدید هم‌زمان همدیگه رو خراب نکنن."""
    await session.execute(
        pg_insert(Subscription).values(user_id=user_id, expires_at=now).on_conflict_do_nothing()
    )
    sub = (
        await session.execute(select(Subscription).where(Subscription.user_id == user_id).with_for_update())
    ).scalar_one()
    base = max(sub.expires_at, now)
    sub.expires_at = base + timedelta(days=DAYS_PER_MONTH * months)
    return sub.expires_at
