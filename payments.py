from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import (
    COMMISSION_ON_GIFT_BALANCE_PURCHASES,
    COMMISSION_PERCENT,
    PAYMENT_TTL_MINUTES,
    RECEIPT_TTL_MINUTES,
)
from ..db.models import Payment, Plan, User
from .subscriptions import extend_subscription
from .wallet import add_entry, balance, lock_user


class NoAmountAvailable(Exception):
    pass


class InsufficientBalance(Exception):
    pass


@dataclass
class Approved:
    payment: Payment
    expires_at: datetime
    commission: int
    referrer_id: int | None


@dataclass
class Expired:
    chat_id: int | None
    message_id: int | None
    was: str
    payment: Payment


# ---------------------------------------------------------------- پلن‌ها
async def list_plans(session: AsyncSession) -> list[Plan]:
    rows = await session.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.months))
    return list(rows)


async def get_plan(session: AsyncSession, months: int) -> Plan | None:
    return await session.scalar(select(Plan).where(Plan.months == months, Plan.is_active.is_(True)))


def _new_ref() -> str:
    return str(10_000_000 + secrets.randbelow(90_000_000))


# ---------------------------------------------------------------- کارت‌به‌کارت
async def create_card_payment(
    session: AsyncSession,
    user_id: int,
    plan: Plan,
    chat_id: int,
    message_id: int,
    now: datetime,
) -> tuple[Payment, list[tuple[int, int]]]:
    """یک پرداخت جدید با مبلغ دقیقِ یکتا می‌سازه.
    پرداخت‌های «در انتظار»ِ قبلیِ همین کاربر لغو می‌شن. خروجی دوم: پیام‌های قدیمی که باید ویرایش بشن."""
    await lock_user(session, user_id)

    old = (
        (
            await session.execute(
                select(Payment).where(Payment.user_id == user_id, Payment.status == "pending").with_for_update()
            )
        )
        .scalars()
        .all()
    )
    stale: list[tuple[int, int]] = []
    for p in old:
        p.status = "cancelled"
        if p.chat_id and p.message_id and p.message_id != message_id:
            stale.append((p.chat_id, p.message_id))
    await session.flush()  # مبلغ‌های قبلی آزاد می‌شن

    # مبلغ‌های «مرتب» (مضرب 50) اول، بعد مضرب 10
    coarse = list(range(1000, 2001, 50))
    fine = [x for x in range(1000, 2001, 10) if x not in set(coarse)]
    random.shuffle(coarse)
    random.shuffle(fine)

    for extra in coarse + fine:
        payment = Payment(
            ref=_new_ref(),
            user_id=user_id,
            plan_months=plan.months,
            base_amount=plan.price,
            unique_amount=plan.price + extra,
            method="card",
            status="pending",
            expires_at=now + timedelta(minutes=PAYMENT_TTL_MINUTES),
            chat_id=chat_id,
            message_id=message_id,
        )
        try:
            async with session.begin_nested():
                session.add(payment)
                await session.flush()
            return payment, stale
        except IntegrityError:
            continue  # مبلغ (یا کد پیگیری) تکراری بود؛ یکی دیگه رو امتحان کن
    raise NoAmountAvailable


async def mark_paid_clicked(session: AsyncSession, payment_id: int, user_id: int, now: datetime) -> Payment | None:
    """کاربر «پرداخت کردم» رو زد. فقط صاحب پرداخت، فقط یک‌بار و فقط قبل از انقضا."""
    p = (
        await session.execute(
            select(Payment)
            .where(
                Payment.id == payment_id,
                Payment.user_id == user_id,
                Payment.status == "pending",
                Payment.expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if p is None:
        return None
    p.status = "awaiting_receipt"
    p.expires_at = now + timedelta(minutes=RECEIPT_TTL_MINUTES)
    return p


async def has_awaiting_receipt(session: AsyncSession, user_id: int, now: datetime) -> bool:
    return (
        await session.scalar(
            select(Payment.id).where(
                Payment.user_id == user_id, Payment.status == "awaiting_receipt", Payment.expires_at > now
            )
        )
    ) is not None


async def attach_receipt(session: AsyncSession, user_id: int, file_id: str, now: datetime) -> Payment | None:
    p = (
        await session.execute(
            select(Payment)
            .where(Payment.user_id == user_id, Payment.status == "awaiting_receipt", Payment.expires_at > now)
            .order_by(Payment.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if p is None:
        return None
    p.status = "in_review"
    p.receipt_file_id = file_id
    p.expires_at = None
    return p


# ---------------------------------------------------------------- تصمیم ادمین
async def approve_payment(session: AsyncSession, payment_id: int, admin_id: int, now: datetime) -> Approved | None:
    """تأیید فقط یک‌بار اثر می‌کنه: ردیف قفل می‌شه و وضعیت باید دقیقاً in_review باشه.
    فعال‌سازی اشتراک و پورسانت توی همین تراکنش ثبت می‌شن؛ یا هر دو انجام می‌شن یا هیچ‌کدوم."""
    p = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.status == "in_review").with_for_update()
        )
    ).scalar_one_or_none()
    if p is None:
        return None

    p.status = "approved"
    p.reviewed_by = admin_id
    p.reviewed_at = now
    expires_at = await extend_subscription(session, p.user_id, p.plan_months, now)

    referrer_id = await session.scalar(select(User.referrer_id).where(User.id == p.user_id))
    commission = 0
    if referrer_id:
        commission = p.base_amount * COMMISSION_PERCENT // 100
        if commission > 0:
            await add_entry(session, referrer_id, commission, "referral_commission", f"pay:{p.id}:commission", p.id)
    return Approved(p, expires_at, commission, referrer_id)


async def reject_payment(session: AsyncSession, payment_id: int, admin_id: int, now: datetime) -> Payment | None:
    p = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.status == "in_review").with_for_update()
        )
    ).scalar_one_or_none()
    if p is None:
        return None
    p.status = "rejected"
    p.reviewed_by = admin_id
    p.reviewed_at = now
    return p


# ---------------------------------------------------------------- موجودی هدیه
async def buy_with_balance(session: AsyncSession, user_id: int, plan: Plan, now: datetime) -> tuple[datetime, int]:
    """خرید با موجودی هدیه. کاربر قفل می‌شه، پس دو خرید هم‌زمان نمی‌تونن موجودی رو دوبار خرج کنن."""
    await lock_user(session, user_id)
    current = await balance(session, user_id)
    if current < plan.price:
        raise InsufficientBalance

    p = Payment(
        ref=_new_ref(),
        user_id=user_id,
        plan_months=plan.months,
        base_amount=plan.price,
        unique_amount=None,
        method="gift",
        status="approved",
        reviewed_at=now,
    )
    session.add(p)
    await session.flush()
    await add_entry(session, user_id, -plan.price, "subscription_purchase", f"pay:{p.id}:debit", p.id)
    expires_at = await extend_subscription(session, user_id, plan.months, now)

    commission = 0
    if COMMISSION_ON_GIFT_BALANCE_PURCHASES:
        referrer_id = await session.scalar(select(User.referrer_id).where(User.id == user_id))
        if referrer_id:
            commission = plan.price * COMMISSION_PERCENT // 100
            await add_entry(session, referrer_id, commission, "referral_commission", f"pay:{p.id}:commission", p.id)
    return expires_at, current - plan.price


# ---------------------------------------------------------------- انقضا
async def expire_due_payments(session: AsyncSession, now: datetime, limit: int = 100) -> list[Expired]:
    rows = (
        (
            await session.execute(
                select(Payment)
                .where(Payment.status.in_(("pending", "awaiting_receipt")), Payment.expires_at <= now)
                .order_by(Payment.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    out: list[Expired] = []
    for p in rows:
        out.append(Expired(p.chat_id, p.message_id, p.status, p))
        p.status = "expired"
    return out
