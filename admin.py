from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import func, select

from .. import texts as T
from ..config import Settings
from ..db.models import Payment, Subscription, User
from ..keyboards import AdmPay
from ..services.payments import approve_payment, reject_payment
from ..utils import esc, utcnow

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """فقط آیدی‌های ADMIN_IDS رد می‌شن. برای بقیه ربات هیچ واکنشی نشون نمی‌ده (پنل مخفیه)."""

    async def __call__(self, event: TelegramObject, settings: Settings) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and user.id in settings.admin_id_set)


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def admin_panel(message: Message, db) -> None:
    now = utcnow()
    async with db.begin() as s:
        users = await s.scalar(select(func.count(User.id)))
        active = await s.scalar(select(func.count(Subscription.user_id)).where(Subscription.expires_at > now))
        review = await s.scalar(select(func.count(Payment.id)).where(Payment.status == "in_review"))
    await message.answer(
        "🛠 <b>پنل مدیریت</b>\n\n"
        f"👥 <b>کل کاربران:</b> {users}\n"
        f"⭐ <b>اشتراک‌های فعال:</b> {active}\n"
        f"🧾 <b>رسیدهای منتظر بررسی:</b> {review}"
    )


async def _finish(cb: CallbackQuery, line: str) -> None:
    """زیر عکس رسید نتیجه رو می‌نویسه و دکمه‌ها رو برمی‌داره."""
    msg = cb.message
    if isinstance(msg, Message):
        try:
            await msg.edit_caption(caption=f"{msg.html_text}\n\n{line}", reply_markup=None)
        except TelegramAPIError:
            pass


@router.callback_query(AdmPay.filter(F.act == "ok"))
async def approve(cb: CallbackQuery, callback_data: AdmPay, db, bot: Bot) -> None:
    now = utcnow()
    async with db.begin() as s:
        res = await approve_payment(s, callback_data.id, cb.from_user.id, now)
    if res is None:
        await cb.answer("این رسید قبلاً بررسی شده.", show_alert=True)
        await _finish(cb, "ℹ️ قبلاً بررسی شده بود.")
        return

    await cb.answer("تأیید شد ✅️")
    await _finish(cb, f"✅️ <b>تأیید شد</b> توسط {esc(cb.from_user.full_name)}")
    try:
        await bot.send_message(res.payment.user_id, T.user_approved(res.payment.plan_months, res.expires_at, now))
    except TelegramAPIError:
        log.warning("could not notify user %s", res.payment.user_id)
    if res.referrer_id and res.commission:
        try:
            await bot.send_message(res.referrer_id, T.commission_received(res.commission))
        except TelegramAPIError:
            pass


@router.callback_query(AdmPay.filter(F.act == "no"))
async def reject(cb: CallbackQuery, callback_data: AdmPay, db, bot: Bot) -> None:
    async with db.begin() as s:
        p = await reject_payment(s, callback_data.id, cb.from_user.id, utcnow())
    if p is None:
        await cb.answer("این رسید قبلاً بررسی شده.", show_alert=True)
        await _finish(cb, "ℹ️ قبلاً بررسی شده بود.")
        return

    await cb.answer("رد شد")
    await _finish(cb, f"❌️ <b>رد شد</b> توسط {esc(cb.from_user.full_name)}")
    try:
        await bot.send_message(p.user_id, T.user_rejected(p.ref))
    except TelegramAPIError:
        log.warning("could not notify user %s", p.user_id)
