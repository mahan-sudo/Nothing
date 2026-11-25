from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import User, WalletEntry


async def lock_user(session: AsyncSession, user_id: int) -> None:
    """ردیف کاربر رو قفل می‌کنه تا عملیات‌های مالی یک کاربر پشت‌سرهم اجرا بشن (ضد ریس‌کاندیشن)."""
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def balance(session: AsyncSession, user_id: int) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(WalletEntry.amount), 0)).where(WalletEntry.user_id == user_id)
    )
    return int(total or 0)


async def add_entry(
    session: AsyncSession,
    user_id: int,
    amount: int,
    kind: str,
    key: str,
    payment_id: int | None = None,
) -> bool:
    """یک ردیف به دفتر حساب اضافه می‌کنه. اگه همین key قبلاً ثبت شده باشه، چیزی اضافه نمی‌شه."""
    stmt = (
        pg_insert(WalletEntry)
        .values(user_id=user_id, amount=amount, kind=kind, idempotency_key=key, payment_id=payment_id)
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(WalletEntry.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
