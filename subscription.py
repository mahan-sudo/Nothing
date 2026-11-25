from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from .. import keyboards as K
from .. import texts as T
from ..cache import hit, try_lock
from ..config import Settings
from ..keyboards import GiftConfirm, Nav, PayAction, PlanPick
from ..services.payments import (
    InsufficientBalance,
    NoAmountAvailable,
    attach_receipt,
    buy_with_balance,
    create_card_payment,
    get_plan,
    list_plans,
    mark_paid_clicked,
)
from ..services.subscriptions import get_expires_at
from ..services.wallet import balance
from ..utils import utcnow
from .common import cb_message, safe_edit

log = logging.getLogger(__name__)
router = Router(name="subscription")


# ------------------------------------------------------------ صفحهٔ اصلی اشتراک
@router.message(F.text == K.BTN_SUB)
async def open_sub(message: Message, db) -> None:
    async with db.begin() as s:
        plans = await list_plans(s)
        exp = await get_expires_at(s, message.from_user.id)
    await message.answer(T.sub_main(plans, exp, utcnow()), reply_markup=K.sub_methods())


@router.callback_query(Nav.filter(F.to == "sub"))
async def cb_sub(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as s:
        plans = await list_plans(s)
        exp = await get_expires_at(s, cb.from_user.id)
    await safe_edit(msg, T.sub_main(plans, exp, utcnow()), K.sub_methods())
    await cb.answer()


# ------------------------------------------------------------ کارت‌به‌کارت
@router.callback_query(Nav.filter(F.to == "card"))
async def cb_card(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as s:
        plans = await list_plans(s)
    await safe_edit(msg, T.card_plans(plans), K.plans("card", plans))
    await cb.answer()


@router.callback_query(PlanPick.filter(F.method == "card"))
async def cb_card_plan(cb: CallbackQuery, callback_data: PlanPick, db, redis, bot: Bot, settings: Settings) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    uid = cb.from_user.id
    if not await hit(redis, f"pc:{uid}", limit=8, window=3600):
        await cb.answer(T.TOO_MANY_PAYMENTS, show_alert=True)
        return

    now = utcnow()
    try:
        async with db.begin() as s:
            plan = await get_plan(s, callback_data.months)
            if plan is None:
                await cb.answer("این پلن الان فعال نیست.", show_alert=True)
                return
            payment, stale = await create_card_payment(s, uid, plan, msg.chat.id, msg.message_id, now)
    except NoAmountAvailable:
        await cb.answer(T.NO_AMOUNT, show_alert=True)
        return

    await safe_edit(
        msg,
        T.payment_details(payment, settings.card_number, settings.card_holder),
        K.payment(payment.id, payment.unique_amount, settings.card_number),
    )
    await cb.answer()

    # پرداخت‌های قدیمیِ لغوشده رو هم ویرایش کن (اگه نشد، مهم نیست)
    for chat_id, message_id in stale:
        try:
            await bot.edit_message_text(
                "این پرداخت لغو شده لطفاً واریز نکنید!", chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except TelegramAPIError:
            pass


@router.callback_query(PayAction.filter(F.act == "paid"))
async def cb_paid(cb: CallbackQuery, callback_data: PayAction, db) -> None:
    msg = cb_message(cb)
    async with db.begin() as s:
        p = await mark_paid_clicked(s, callback_data.id, cb.from_user.id, utcnow())
    if p is None:
        await cb.answer(T.PAYMENT_INVALID, show_alert=True)
        return
    if msg is not None:
        await safe_edit(msg, T.RECEIPT_PROMPT, None)
    await cb.answer()


# ------------------------------------------------------------ موجودی هدیه
@router.callback_query(Nav.filter(F.to == "gift"))
async def cb_gift(cb: CallbackQuery, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as s:
        plans = await list_plans(s)
        bal = await balance(s, cb.from_user.id)
    await safe_edit(msg, T.gift_plans(plans, bal), K.plans("gift", plans))
    await cb.answer()


@router.callback_query(PlanPick.filter(F.method == "gift"))
async def cb_gift_plan(cb: CallbackQuery, callback_data: PlanPick, db) -> None:
    msg = cb_message(cb)
    if msg is None:
        await cb.answer()
        return
    async with db.begin() as s:
        plan = await get_plan(s, callback_data.months)
        bal = await balance(s, cb.from_user.id)
    if plan is None:
        await cb.answer("این پلن الان فعال نیست.", show_alert=True)
        return
    if bal < plan.price:
        await cb.answer(T.GIFT_INSUFFICIENT, show_alert=True)
        return
    await safe_edit(msg, T.gift_confirm(plan, bal), K.gift_confirm(plan.months))
    await cb.answer()


@router.callback_query(GiftConfirm.filter())
async def cb_gift_confirm(cb: CallbackQuery, callback_data: GiftConfirm, db, redis) -> None:
    msg = cb_message(cb)
    uid = cb.from_user.id
    # قفل کوتاه برای دوبار‌کلیک. امنیت اصلی با قفل ردیف کاربر توی دیتابیسه.
    if not await try_lock(redis, f"lock:gift:{uid}", 5):
        await cb.answer("یک لحظه صبر کن 🌱")
        return
    now = utcnow()
    try:
        async with db.begin() as s:
            plan = await get_plan(s, callback_data.months)
            if plan is None:
                await cb.answer("این پلن الان فعال نیست.", show_alert=True)
                return
            expires_at, new_balance = await buy_with_balance(s, uid, plan, now)
    except InsufficientBalance:
        await cb.answer(T.GIFT_INSUFFICIENT, show_alert=True)
        return
    if msg is not None:
        await safe_edit(msg, T.gift_success(plan, expires_at, now, new_balance), None)
    await cb.answer("اشتراکت فعال شد 🎉")


# ------------------------------------------------------------ عکس رسید
@router.message(F.photo)
async def on_receipt(message: Message, db, bot: Bot, settings: Settings) -> None:
    uid = message.from_user.id
    file_id = message.photo[-1].file_id
    async with db.begin() as s:
        p = await attach_receipt(s, uid, file_id, utcnow())
    if p is None:
        await message.answer(T.NO_PENDING_RECEIPT)
        return

    caption = T.admin_caption(p, message.from_user)
    delivered = 0
    for admin_id in settings.admin_id_set:
        try:
            await bot.send_photo(admin_id, file_id, caption=caption, reply_markup=K.admin_review(p.id))
            delivered += 1
        except TelegramAPIError:
            log.warning("could not send receipt to admin %s (has the admin pressed /start?)", admin_id)
    if delivered == 0:
        log.error("receipt for payment %s reached NO admin", p.id)
    await message.answer(T.RECEIPT_RECEIVED)
