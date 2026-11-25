from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import Vault
from ..db.models import SelfAccount
from ..utils import mask_phone
from .subscriptions import get_expires_at


async def save_account(
    session: AsyncSession, user_id: int, phone: str, session_string: str, vault: Vault, now: datetime
) -> bool:
    """حساب متصل‌شده رو ذخیره می‌کنه. شماره و سشن فقط رمزنگاری‌شده وارد دیتابیس می‌شن.
    اگه اشتراک وسط کار تموم شده باشه، ذخیره نمی‌شه."""
    exp = await get_expires_at(session, user_id)
    if not exp or exp <= now:
        return False
    values = dict(
        phone_masked=mask_phone(phone),
        phone_enc=vault.encrypt(phone),
        session_enc=vault.encrypt(session_string),
        is_connected=True,
        self_enabled=True,
    )
    stmt = pg_insert(SelfAccount).values(user_id=user_id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[SelfAccount.user_id], set_=values)
    await session.execute(stmt)
    return True


async def toggle_self(session: AsyncSession, user_id: int, now: datetime) -> tuple[str, bool]:
    """خروجی: (وضعیت, حالت جدید). وضعیت: ok | no_account | no_sub"""
    acct = (
        await session.execute(select(SelfAccount).where(SelfAccount.user_id == user_id).with_for_update())
    ).scalar_one_or_none()
    if acct is None or not acct.is_connected:
        return "no_account", False
    if acct.self_enabled:
        acct.self_enabled = False
        return "ok", False
    exp = await get_expires_at(session, user_id)
    if not exp or exp <= now:
        return "no_sub", False
    acct.self_enabled = True
    return "ok", True
