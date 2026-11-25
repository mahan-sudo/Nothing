"""دسترسی به دیتابیس برای موتور تبچی. همه‌چیز اینجا کوتاه و تراکنشیه."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.models import BackupChannel, Banner, SelfAccount, Subscription


async def runnable_accounts(db, now: datetime) -> dict[int, str]:
    """حساب‌هایی که باید الان روشن باشن: متصل + سلف روشن + اشتراک فعال."""
    async with db.begin() as s:
        rows = await s.execute(
            select(SelfAccount.user_id, SelfAccount.session_enc)
            .join(Subscription, Subscription.user_id == SelfAccount.user_id)
            .where(
                SelfAccount.is_connected.is_(True),
                SelfAccount.self_enabled.is_(True),
                SelfAccount.session_enc.is_not(None),
                Subscription.expires_at > now,
            )
        )
        return {uid: enc for uid, enc in rows.all()}


async def mark_account_dead(db, user_id: int) -> None:
    async with db.begin() as s:
        await s.execute(
            update(SelfAccount)
            .where(SelfAccount.user_id == user_id)
            .values(is_connected=False, self_enabled=False, session_enc=None, phone_enc=None)
        )


# ------------------------------------------------------------ پشتیبان
async def get_backup(db, user_id: int) -> BackupChannel | None:
    async with db.begin() as s:
        return await s.get(BackupChannel, user_id)


async def set_backup(db, user_id: int, channel_id: int, access_hash: int | None, title: str | None) -> None:
    values = dict(channel_id=channel_id, access_hash=access_hash, title=(title or "")[:256])
    async with db.begin() as s:
        stmt = pg_insert(BackupChannel).values(user_id=user_id, **values)
        await s.execute(stmt.on_conflict_do_update(index_elements=[BackupChannel.user_id], set_=values))


# ------------------------------------------------------------ بنرها
async def get_banner(db, user_id: int, chat_id: int) -> Banner | None:
    async with db.begin() as s:
        return await s.scalar(select(Banner).where(Banner.user_id == user_id, Banner.chat_id == chat_id))


async def get_banner_by_id(db, banner_id: int) -> Banner | None:
    async with db.begin() as s:
        return await s.get(Banner, banner_id)


async def list_enabled(db, user_id: int) -> list[Banner]:
    async with db.begin() as s:
        rows = await s.scalars(select(Banner).where(Banner.user_id == user_id, Banner.enabled.is_(True)))
        return list(rows)


async def count_enabled(db, user_id: int) -> int:
    async with db.begin() as s:
        return int(
            await s.scalar(select(func.count(Banner.id)).where(Banner.user_id == user_id, Banner.enabled.is_(True)))
            or 0
        )


async def upsert_banner(
    db,
    user_id: int,
    chat_id: int,
    chat_access_hash: int | None,
    chat_title: str | None,
    backup_channel_id: int,
    backup_access_hash: int | None,
    backup_msg_id: int,
) -> Banner:
    """بنر جدید ذخیره می‌شه. اگه برای این گروه قبلاً بنری بوده، فقط محتواش عوض می‌شه
    (بازه و روشن/خاموش بودن سر جاشون می‌مونن)."""
    async with db.begin() as s:
        stmt = pg_insert(Banner).values(
            user_id=user_id,
            chat_id=chat_id,
            chat_access_hash=chat_access_hash,
            chat_title=(chat_title or "")[:256],
            backup_channel_id=backup_channel_id,
            backup_access_hash=backup_access_hash,
            backup_msg_id=backup_msg_id,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_banners_user_chat",
            set_=dict(
                chat_access_hash=chat_access_hash,
                chat_title=(chat_title or "")[:256],
                backup_channel_id=backup_channel_id,
                backup_access_hash=backup_access_hash,
                backup_msg_id=backup_msg_id,
                fail_streak=0,
            ),
        ).returning(Banner)
        return (await s.execute(stmt)).scalar_one()


async def set_interval(db, banner_id: int, seconds: int, next_run_at: datetime | None) -> None:
    async with db.begin() as s:
        vals = {"interval_seconds": seconds}
        if next_run_at is not None:
            vals["next_run_at"] = next_run_at
        await s.execute(update(Banner).where(Banner.id == banner_id).values(**vals))


async def set_enabled(db, banner_id: int, enabled: bool, next_run_at: datetime | None = None) -> None:
    async with db.begin() as s:
        vals = {"enabled": enabled, "fail_streak": 0}
        if enabled:
            vals["next_run_at"] = next_run_at
        await s.execute(update(Banner).where(Banner.id == banner_id).values(**vals))


async def set_info_msg(db, banner_id: int, msg_id: int) -> None:
    async with db.begin() as s:
        await s.execute(update(Banner).where(Banner.id == banner_id).values(info_msg_id=msg_id))


async def mark_sent(db, banner_id: int, now: datetime, next_run_at: datetime) -> None:
    async with db.begin() as s:
        await s.execute(
            update(Banner)
            .where(Banner.id == banner_id)
            .values(last_sent_at=now, next_run_at=next_run_at, send_count=Banner.send_count + 1, fail_streak=0)
        )


async def set_next_run(db, banner_id: int, next_run_at: datetime) -> None:
    async with db.begin() as s:
        await s.execute(update(Banner).where(Banner.id == banner_id).values(next_run_at=next_run_at))


async def bump_fail(db, banner_id: int, next_run_at: datetime) -> int:
    async with db.begin() as s:
        row = await s.execute(
            update(Banner)
            .where(Banner.id == banner_id)
            .values(fail_streak=Banner.fail_streak + 1, next_run_at=next_run_at)
            .returning(Banner.fail_streak)
        )
        return int(row.scalar_one_or_none() or 0)


async def delete_banner(db, banner_id: int) -> None:
    async with db.begin() as s:
        await s.execute(delete(Banner).where(Banner.id == banner_id))
